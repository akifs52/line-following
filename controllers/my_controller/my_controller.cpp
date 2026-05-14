#ifndef NOMINMAX
#define NOMINMAX
#endif

#include <webots/camera.h>
#include <webots/motor.h>
#include <webots/robot.h>

#include <ncnn/net.h>

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <sstream>
#include <utility>
#include <vector>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#pragma comment(lib, "Ws2_32.lib")
#endif

namespace {

constexpr const char *kCameraName = "camera";
constexpr const char *kLeftMotorName = "left_motor";
constexpr const char *kRightMotorName = "right_motor";

constexpr double kLeftMotorSign = 1.0;
constexpr double kRightMotorSign = 1.0;

constexpr double kRoiTopRatio = 0.35;
constexpr int kMinLinePixels = 15;

constexpr int kInputSize = 640;
constexpr float kNmsThreshold = 0.45f;
constexpr float kMaskThreshold = 0.50f;
constexpr float kNormVals[3] = {1.0f / 255.0f, 1.0f / 255.0f, 1.0f / 255.0f};

// RaspiControlClient.cpp constants.
constexpr double kWallTargetCm = 13.5;
constexpr double kDangerZoneCm = 5.0;
constexpr double kBaseSpeed = 50.0;
constexpr double kMinPwm = 25.0;
constexpr double kMaxPwm = 100.0;
constexpr double kSteerGain = 0.12;
constexpr int kNoLineTimeoutMs = 500;
constexpr double kSearchTurnSpeed = 35.0;

constexpr int kStatusIntervalMs = 250;
constexpr int kFrameStreamIntervalMs = 33;
constexpr int kExternalCommandTimeoutMs = 500;
constexpr const char kRawFrameMagic[4] = {'W', 'B', 'F', 'R'};

double clamp(double value, double minimum, double maximum) {
  return std::max(minimum, std::min(maximum, value));
}

float sigmoid(float value) {
  return 1.0f / (1.0f + std::exp(-value));
}

double envDouble(const char *name, double fallback) {
  const char *raw = std::getenv(name);
  if (!raw || !*raw)
    return fallback;

  char *end = nullptr;
  const double value = std::strtod(raw, &end);
  if (end == raw)
    return fallback;
  return value;
}

bool envFlag(const char *name, bool fallback) {
  const char *raw = std::getenv(name);
  if (!raw || !*raw)
    return fallback;
  const std::string value(raw);
  return value == "1" || value == "true" || value == "TRUE" || value == "on" || value == "ON";
}

std::filesystem::path executableDir() {
#ifdef _WIN32
  char buffer[MAX_PATH] = {};
  const DWORD size = GetModuleFileNameA(nullptr, buffer, static_cast<DWORD>(std::size(buffer)));
  if (size > 0)
    return std::filesystem::path(buffer).parent_path();
#endif
  return std::filesystem::current_path();
}

struct LaneMeasurement {
  bool valid = false;
  double lineX = -1.0;
  bool lineIsLeft = false;
  double score = 0.0;
  int pixelCount = 0;
  int clusterCount = 0;
  std::string source = "none";
};

struct MotorCommand {
  double left = 0.0;
  double right = 0.0;
  std::string mode = "STOP";
  double distanceCm = 0.0;
  double errorCm = 0.0;
  double turn = 0.0;
  double baseSpeed = 0.0;
  double lineX = -1.0;
  char lineSide = '?';
};

void appendUint32Le(std::vector<char> &buffer, uint32_t value) {
  buffer.push_back(static_cast<char>(value & 0xffu));
  buffer.push_back(static_cast<char>((value >> 8u) & 0xffu));
  buffer.push_back(static_cast<char>((value >> 16u) & 0xffu));
  buffer.push_back(static_cast<char>((value >> 24u) & 0xffu));
}

#ifdef _WIN32
class WsaSession {
public:
  WsaSession() {
    WSADATA data;
    m_ok = WSAStartup(MAKEWORD(2, 2), &data) == 0;
  }

  ~WsaSession() {
    if (m_ok)
      WSACleanup();
  }

  bool ok() const { return m_ok; }

private:
  bool m_ok = false;
};

bool setNonBlocking(SOCKET socketHandle) {
  u_long nonBlocking = 1;
  return ioctlsocket(socketHandle, FIONBIO, &nonBlocking) == 0;
}

class CameraStreamServer {
public:
  explicit CameraStreamServer(int port) : m_port(port) {
    m_listenSocket = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (m_listenSocket == INVALID_SOCKET) {
      m_status = "socket() failed";
      return;
    }

    setNonBlocking(m_listenSocket);
    BOOL reuse = TRUE;
    setsockopt(m_listenSocket, SOL_SOCKET, SO_REUSEADDR, reinterpret_cast<const char *>(&reuse), sizeof(reuse));

    sockaddr_in address = {};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_ANY);
    address.sin_port = htons(static_cast<u_short>(m_port));
    if (bind(m_listenSocket, reinterpret_cast<sockaddr *>(&address), sizeof(address)) == SOCKET_ERROR ||
        listen(m_listenSocket, 1) == SOCKET_ERROR) {
      m_status = "bind/listen failed on port " + std::to_string(m_port);
      closesocket(m_listenSocket);
      m_listenSocket = INVALID_SOCKET;
      return;
    }

    m_status = "listening on port " + std::to_string(m_port);
  }

  ~CameraStreamServer() {
    closeClient();
    if (m_listenSocket != INVALID_SOCKET)
      closesocket(m_listenSocket);
  }

  const std::string &status() const { return m_status; }
  bool connected() const { return m_clientSocket != INVALID_SOCKET; }

  void update(const unsigned char *image, int width, int height, int simTimeMs) {
    acceptClient();
    pumpSend();

    if (!connected() || !image || width <= 0 || height <= 0)
      return;

    if (simTimeMs - m_lastFrameMs < kFrameStreamIntervalMs)
      return;

    const uint32_t payloadSize = static_cast<uint32_t>(width * height * 4);
    if (!m_sendBuffer.empty() && m_sendBuffer.size() - m_sendOffset > payloadSize * 2u)
      return;

    m_lastFrameMs = simTimeMs;
    if (m_sendOffset >= m_sendBuffer.size()) {
      m_sendBuffer.clear();
      m_sendOffset = 0;
    }

    m_sendBuffer.insert(m_sendBuffer.end(), kRawFrameMagic, kRawFrameMagic + 4);
    appendUint32Le(m_sendBuffer, static_cast<uint32_t>(width));
    appendUint32Le(m_sendBuffer, static_cast<uint32_t>(height));
    appendUint32Le(m_sendBuffer, 1u);  // 1 = BGRA/Qt ARGB32-compatible bytes.
    appendUint32Le(m_sendBuffer, payloadSize);
    m_sendBuffer.insert(m_sendBuffer.end(), reinterpret_cast<const char *>(image),
                        reinterpret_cast<const char *>(image) + payloadSize);

    pumpSend();
  }

private:
  void acceptClient() {
    if (m_listenSocket == INVALID_SOCKET)
      return;

    SOCKET accepted = accept(m_listenSocket, nullptr, nullptr);
    if (accepted == INVALID_SOCKET)
      return;

    closeClient();
    m_clientSocket = accepted;
    setNonBlocking(m_clientSocket);
    int sendBufferSize = 2 * 1024 * 1024;
    setsockopt(m_clientSocket, SOL_SOCKET, SO_SNDBUF, reinterpret_cast<const char *>(&sendBufferSize), sizeof(sendBufferSize));
    m_sendBuffer.clear();
    m_sendOffset = 0;
    m_status = "client connected on port " + std::to_string(m_port);
  }

  void pumpSend() {
    if (!connected() || m_sendOffset >= m_sendBuffer.size())
      return;

    while (m_sendOffset < m_sendBuffer.size()) {
      const int remaining = static_cast<int>(std::min<size_t>(m_sendBuffer.size() - m_sendOffset, 64 * 1024));
      const int sent = send(m_clientSocket, m_sendBuffer.data() + m_sendOffset, remaining, 0);
      if (sent > 0) {
        m_sendOffset += static_cast<size_t>(sent);
        continue;
      }

      const int err = WSAGetLastError();
      if (err == WSAEWOULDBLOCK)
        break;

      closeClient();
      break;
    }

    if (m_sendOffset >= m_sendBuffer.size()) {
      m_sendBuffer.clear();
      m_sendOffset = 0;
    }
  }

  void closeClient() {
    if (m_clientSocket != INVALID_SOCKET) {
      closesocket(m_clientSocket);
      m_clientSocket = INVALID_SOCKET;
    }
    m_sendBuffer.clear();
    m_sendOffset = 0;
  }

  int m_port = 8554;
  SOCKET m_listenSocket = INVALID_SOCKET;
  SOCKET m_clientSocket = INVALID_SOCKET;
  std::vector<char> m_sendBuffer;
  size_t m_sendOffset = 0;
  int m_lastFrameMs = 0;
  std::string m_status;
};

class ControlCommandServer {
public:
  explicit ControlCommandServer(int port) : m_port(port) {
    m_listenSocket = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (m_listenSocket == INVALID_SOCKET) {
      m_status = "socket() failed";
      return;
    }

    setNonBlocking(m_listenSocket);
    BOOL reuse = TRUE;
    setsockopt(m_listenSocket, SOL_SOCKET, SO_REUSEADDR, reinterpret_cast<const char *>(&reuse), sizeof(reuse));

    sockaddr_in address = {};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_ANY);
    address.sin_port = htons(static_cast<u_short>(m_port));
    if (bind(m_listenSocket, reinterpret_cast<sockaddr *>(&address), sizeof(address)) == SOCKET_ERROR ||
        listen(m_listenSocket, 1) == SOCKET_ERROR) {
      m_status = "bind/listen failed on port " + std::to_string(m_port);
      closesocket(m_listenSocket);
      m_listenSocket = INVALID_SOCKET;
      return;
    }

    m_status = "listening on port " + std::to_string(m_port);
  }

  ~ControlCommandServer() {
    closeClient();
    if (m_listenSocket != INVALID_SOCKET)
      closesocket(m_listenSocket);
  }

  const std::string &status() const { return m_status; }
  bool connected() const { return m_clientSocket != INVALID_SOCKET; }

  void update(int simTimeMs) {
    acceptClient();
    readCommands(simTimeMs);
  }

  bool hasRecentCommand(int simTimeMs) const {
    return connected() && m_lastCommandMs > 0 && simTimeMs - m_lastCommandMs <= kExternalCommandTimeoutMs;
  }

  MotorCommand command() const {
    MotorCommand command;
    command.left = m_left;
    command.right = m_right;
    command.mode = "EXT";
    return command;
  }

private:
  void acceptClient() {
    if (m_listenSocket == INVALID_SOCKET)
      return;

    SOCKET accepted = accept(m_listenSocket, nullptr, nullptr);
    if (accepted == INVALID_SOCKET)
      return;

    closeClient();
    m_clientSocket = accepted;
    setNonBlocking(m_clientSocket);
    m_rxBuffer.clear();
    m_status = "client connected on port " + std::to_string(m_port);
  }

  void readCommands(int simTimeMs) {
    if (!connected())
      return;

    char buffer[1024];
    while (true) {
      const int received = recv(m_clientSocket, buffer, sizeof(buffer), 0);
      if (received > 0) {
        m_rxBuffer.append(buffer, received);
        consumeLines(simTimeMs);
        continue;
      }

      if (received == 0) {
        closeClient();
        return;
      }

      const int err = WSAGetLastError();
      if (err == WSAEWOULDBLOCK)
        return;
      closeClient();
      return;
    }
  }

  void consumeLines(int simTimeMs) {
    size_t pos = std::string::npos;
    while ((pos = m_rxBuffer.find('\n')) != std::string::npos) {
      std::string line = m_rxBuffer.substr(0, pos);
      m_rxBuffer.erase(0, pos + 1);
      if (!line.empty() && line.back() == '\r')
        line.pop_back();
      parseCommand(line, simTimeMs);
    }

    if (m_rxBuffer.size() > 4096)
      m_rxBuffer.clear();
  }

  void parseCommand(const std::string &line, int simTimeMs) {
    if (line.empty())
      return;

    if (line == "S" || line == "STOP") {
      m_left = 0.0;
      m_right = 0.0;
      m_lastCommandMs = simTimeMs;
      return;
    }

    if (line.rfind("DIFF,", 0) == 0) {
      std::string payload = line.substr(5);
      std::replace(payload.begin(), payload.end(), ',', ' ');
      std::istringstream stream(payload);
      double left = 0.0;
      double right = 0.0;
      if (stream >> left >> right) {
        m_left = clamp(left, -100.0, 100.0);
        m_right = clamp(right, -100.0, 100.0);
        m_lastCommandMs = simTimeMs;
      }
      return;
    }

    if (line == "SHUTDOWN")
      m_lastCommandMs = 0;
  }

  void closeClient() {
    if (m_clientSocket != INVALID_SOCKET) {
      closesocket(m_clientSocket);
      m_clientSocket = INVALID_SOCKET;
    }
    m_rxBuffer.clear();
  }

  int m_port = 5005;
  SOCKET m_listenSocket = INVALID_SOCKET;
  SOCKET m_clientSocket = INVALID_SOCKET;
  std::string m_rxBuffer;
  std::string m_status;
  double m_left = 0.0;
  double m_right = 0.0;
  int m_lastCommandMs = 0;
};
#endif

struct Rect {
  float x = 0.0f;
  float y = 0.0f;
  float w = 0.0f;
  float h = 0.0f;

  float left() const { return x; }
  float top() const { return y; }
  float right() const { return x + w; }
  float bottom() const { return y + h; }
  float area() const { return std::max(0.0f, w) * std::max(0.0f, h); }
  float centerX() const { return x + w * 0.5f; }
};

struct Detection {
  Rect rect;
  float score = 0.0f;
  float lineCenterX = -1.0f;
  float laneLeftX = -1.0f;
  float laneRightX = -1.0f;
  int frameWidth = 0;
  int frameHeight = 0;
};

float intersectionArea(const Detection &a, const Detection &b) {
  const float x1 = std::max(a.rect.left(), b.rect.left());
  const float y1 = std::max(a.rect.top(), b.rect.top());
  const float x2 = std::min(a.rect.right(), b.rect.right());
  const float y2 = std::min(a.rect.bottom(), b.rect.bottom());
  return std::max(0.0f, x2 - x1) * std::max(0.0f, y2 - y1);
}

void nmsSortedBboxes(const std::vector<Detection> &detections, std::vector<int> &picked, float nmsThreshold) {
  picked.clear();
  std::vector<float> areas;
  areas.reserve(detections.size());
  for (const Detection &det : detections)
    areas.push_back(det.rect.area());

  for (int i = 0; i < static_cast<int>(detections.size()); ++i) {
    bool keep = true;
    for (int pickedIndex : picked) {
      const float inter = intersectionArea(detections[i], detections[pickedIndex]);
      const float uni = areas[i] + areas[pickedIndex] - inter;
      const float iou = uni > 0.0f ? inter / uni : 0.0f;
      if (iou > nmsThreshold) {
        keep = false;
        break;
      }
    }
    if (keep)
      picked.push_back(i);
  }
}

void populateMaskGeometry(Detection &det,
                          const std::vector<float> &maskCoeffs,
                          const ncnn::Mat &prototypes,
                          int srcW,
                          int srcH,
                          int padLeft,
                          int padTop,
                          float scale) {
  det.frameWidth = srcW;
  det.frameHeight = srcH;

  if (maskCoeffs.empty() || prototypes.dims != 3 || prototypes.c <= 0 || prototypes.w <= 0 || prototypes.h <= 0)
    return;

  const int protoW = prototypes.w;
  const int protoH = prototypes.h;
  const int coeffCount = std::min(static_cast<int>(maskCoeffs.size()), prototypes.c);
  if (coeffCount <= 0)
    return;

  std::vector<float> logits(protoW * protoH, 0.0f);
  for (int c = 0; c < coeffCount; ++c) {
    const float coeff = maskCoeffs[c];
    const ncnn::Mat channel = prototypes.channel(c);
    for (int y = 0; y < protoH; ++y) {
      const float *srcRow = channel.row(y);
      float *dstRow = logits.data() + y * protoW;
      for (int x = 0; x < protoW; ++x)
        dstRow[x] += coeff * srcRow[x];
    }
  }

  const double roiTopPx = static_cast<double>(srcH) * kRoiTopRatio;
  const double boxLeft = std::max(0.0f, det.rect.left() - 4.0f);
  const double boxTop = std::max(0.0f, det.rect.top() - 4.0f);
  const double boxRight = std::min(static_cast<float>(srcW - 1), det.rect.right() + 4.0f);
  const double boxBottom = std::min(static_cast<float>(srcH - 1), det.rect.bottom() + 4.0f);

  double sumX = 0.0;
  int fitCount = 0;
  for (int y = 0; y < protoH; ++y) {
    for (int x = 0; x < protoW; ++x) {
      const float probability = sigmoid(logits[y * protoW + x]);
      if (probability < kMaskThreshold)
        continue;

      const double inputX = (static_cast<double>(x) + 0.5) * static_cast<double>(kInputSize) / protoW;
      const double inputY = (static_cast<double>(y) + 0.5) * static_cast<double>(kInputSize) / protoH;
      const double srcX = (inputX - padLeft) / scale;
      const double srcY = (inputY - padTop) / scale;

      if (srcX < 0.0 || srcY < 0.0 || srcX >= srcW || srcY >= srcH)
        continue;
      if (srcX < boxLeft || srcX > boxRight || srcY < boxTop || srcY > boxBottom)
        continue;
      if (srcY < roiTopPx)
        continue;

      sumX += srcX;
      ++fitCount;
    }
  }

  if (fitCount > 0)
    det.lineCenterX = static_cast<float>((sumX / fitCount) / srcW);
  else if (srcW > 0)
    det.lineCenterX = det.rect.centerX() / static_cast<float>(srcW);
}

float detectionCenterX(const Detection &det) {
  if (std::isfinite(det.lineCenterX) && det.lineCenterX > 0.0f && det.lineCenterX < 1.0f)
    return det.lineCenterX;
  if (det.frameWidth > 0)
    return det.rect.centerX() / static_cast<float>(det.frameWidth);
  return -1.0f;
}

class NcnnLaneDetector {
public:
  explicit NcnnLaneDetector(const std::filesystem::path &controllerDir)
      : m_scoreThreshold(static_cast<float>(envDouble("WEBOTS_NCNN_SCORE", 0.30))) {
    load(controllerDir);
  }

  bool loaded() const { return m_loaded; }
  const std::string &status() const { return m_status; }

  LaneMeasurement detect(const unsigned char *image, int width, int height) const {
    LaneMeasurement measurement;
    measurement.source = "ncnn";
    if (!m_loaded || !image || width <= 0 || height <= 0)
      return measurement;

    const float scale = std::min(static_cast<float>(kInputSize) / width, static_cast<float>(kInputSize) / height);
    const int resizedW = std::max(1, static_cast<int>(std::round(width * scale)));
    const int resizedH = std::max(1, static_cast<int>(std::round(height * scale)));

    ncnn::Mat resized = ncnn::Mat::from_pixels_resize(
      image, ncnn::Mat::PIXEL_BGRA2RGB, width, height, resizedW, resizedH);

    const int wpad = kInputSize - resizedW;
    const int hpad = kInputSize - resizedH;
    const int left = wpad / 2;
    const int right = wpad - left;
    const int top = hpad / 2;
    const int bottom = hpad - top;

    ncnn::Mat input;
    ncnn::copy_make_border(resized, input, top, bottom, left, right, ncnn::BORDER_CONSTANT, 114.0f);
    input.substract_mean_normalize(nullptr, kNormVals);

    ncnn::Extractor ex = m_net.create_extractor();
    ex.set_light_mode(true);
    if (ex.input("in0", input) != 0)
      return measurement;

    ncnn::Mat out0;
    if (ex.extract("out0", out0) != 0)
      return measurement;

    ncnn::Mat out1;
    const bool hasMaskOutput = ex.extract("out1", out1) == 0;
    if (out0.dims != 2 || out0.h < 5 || out0.w <= 0)
      return measurement;

    const int maskCoeffOffset = 5;
    const int maskCoeffCount =
      (hasMaskOutput && out1.dims == 3) ? std::max(0, std::min(out1.c, out0.h - maskCoeffOffset)) : 0;

    const float *xPtr = out0.row(0);
    const float *yPtr = out0.row(1);
    const float *wPtr = out0.row(2);
    const float *hPtr = out0.row(3);
    const float *scorePtr = out0.row(4);

    struct Proposal {
      Detection detection;
      std::vector<float> maskCoeffs;
    };

    std::vector<Proposal> proposals;
    proposals.reserve(128);
    for (int i = 0; i < out0.w; ++i) {
      const float score = scorePtr[i];
      if (!std::isfinite(score) || score < m_scoreThreshold)
        continue;

      const float cx = xPtr[i];
      const float cy = yPtr[i];
      const float bw = wPtr[i];
      const float bh = hPtr[i];
      if (!std::isfinite(cx) || !std::isfinite(cy) || !std::isfinite(bw) || !std::isfinite(bh))
        continue;

      float x0 = (cx - bw * 0.5f - left) / scale;
      float y0 = (cy - bh * 0.5f - top) / scale;
      float x1 = (cx + bw * 0.5f - left) / scale;
      float y1 = (cy + bh * 0.5f - top) / scale;

      x0 = static_cast<float>(clamp(x0, 0.0, width - 1.0));
      y0 = static_cast<float>(clamp(y0, 0.0, height - 1.0));
      x1 = static_cast<float>(clamp(x1, 0.0, width - 1.0));
      y1 = static_cast<float>(clamp(y1, 0.0, height - 1.0));

      const float boxW = x1 - x0;
      const float boxH = y1 - y0;
      if (boxW < 2.0f || boxH < 2.0f)
        continue;

      Proposal proposal;
      proposal.detection.rect = Rect{x0, y0, boxW, boxH};
      proposal.detection.score = score;
      proposal.detection.frameWidth = width;
      proposal.detection.frameHeight = height;
      if (maskCoeffCount > 0) {
        proposal.maskCoeffs.reserve(maskCoeffCount);
        for (int coeffIndex = 0; coeffIndex < maskCoeffCount; ++coeffIndex)
          proposal.maskCoeffs.push_back(out0.row(maskCoeffOffset + coeffIndex)[i]);
      }
      proposals.push_back(std::move(proposal));
    }

    if (proposals.empty())
      return measurement;

    std::sort(proposals.begin(), proposals.end(), [](const Proposal &a, const Proposal &b) {
      return a.detection.score > b.detection.score;
    });

    std::vector<Detection> proposalDetections;
    proposalDetections.reserve(proposals.size());
    for (const Proposal &proposal : proposals)
      proposalDetections.push_back(proposal.detection);

    std::vector<int> picked;
    nmsSortedBboxes(proposalDetections, picked, kNmsThreshold);
    if (picked.empty())
      return measurement;

    Detection det = proposals[picked.front()].detection;
    if (maskCoeffCount > 0 && static_cast<int>(proposals[picked.front()].maskCoeffs.size()) == maskCoeffCount)
      populateMaskGeometry(det, proposals[picked.front()].maskCoeffs, out1, width, height, left, top, scale);

    const float centerX = detectionCenterX(det);
    if (!std::isfinite(centerX) || centerX <= 0.0f || centerX >= 1.0f)
      return measurement;

    measurement.valid = true;
    measurement.lineX = centerX;
    measurement.lineIsLeft = centerX < 0.5f;
    measurement.score = det.score;
    measurement.pixelCount = 0;
    measurement.clusterCount = static_cast<int>(picked.size());
    return measurement;
  }

private:
  void load(const std::filesystem::path &controllerDir) {
    const std::vector<std::filesystem::path> roots = {
      controllerDir,
      controllerDir / "assets",
      controllerDir / ".." / ".." / "QtYoloAndroid" / "assets",
    };

    for (const std::filesystem::path &root : roots) {
      const std::filesystem::path paramPath = root / "yolo11.param";
      const std::filesystem::path binPath = root / "yolo11.bin";
      if (!std::filesystem::exists(paramPath) || !std::filesystem::exists(binPath))
        continue;

      m_net.clear();
      m_net.opt.use_vulkan_compute = false;
      m_net.opt.use_fp16_packed = false;
      m_net.opt.use_fp16_storage = false;
      m_net.opt.use_fp16_arithmetic = false;
      m_net.opt.num_threads = 4;

      const std::string param = paramPath.string();
      const std::string bin = binPath.string();
      const int paramRet = m_net.load_param(param.c_str());
      const int modelRet = paramRet == 0 ? m_net.load_model(bin.c_str()) : -1;
      if (paramRet == 0 && modelRet == 0) {
        m_loaded = true;
        m_status = "loaded: " + param;
        return;
      }

      m_status = "load failed param=" + std::to_string(paramRet) + " model=" + std::to_string(modelRet) + " path=" + param;
    }

    if (m_status.empty())
      m_status = "model files not found";
  }

  mutable ncnn::Net m_net;
  bool m_loaded = false;
  std::string m_status;
  float m_scoreThreshold = 0.30f;
};

class ColorLaneDetector {
public:
  LaneMeasurement detect(const unsigned char *image, int width, int height) const {
    LaneMeasurement measurement;
    measurement.source = "color";
    if (!image || width <= 0 || height <= 0)
      return measurement;

    const int roiTop = static_cast<int>(height * kRoiTopRatio);
    const int roiHeight = std::max(1, height - roiTop);
    std::vector<double> histogram(width, 0.0);
    int pixelCount = 0;

    for (int y = roiTop; y < height; ++y) {
      const double rowWeight = 1.0 + 1.4 * static_cast<double>(y - roiTop) / std::max(1, roiHeight - 1);
      for (int x = 0; x < width; ++x) {
        const int red = wb_camera_image_get_red(image, width, x, y);
        const int green = wb_camera_image_get_green(image, width, x, y);
        const int blue = wb_camera_image_get_blue(image, width, x, y);
        const int maxChannel = std::max(red, std::max(green, blue));
        const int minChannel = std::min(red, std::min(green, blue));
        const bool yellow = red > 120 && green > 105 && blue < 120 && (red + green) > (2 * blue + 90);
        const bool white = red > 145 && green > 145 && blue > 145 && (maxChannel - minChannel) < 80;
        if (yellow || white) {
          histogram[x] += rowWeight;
          ++pixelCount;
        }
      }
    }

    if (pixelCount < kMinLinePixels)
      return measurement;

    int kernelSize = std::max(3, width / 80);
    if (kernelSize % 2 == 0)
      ++kernelSize;
    const int radius = kernelSize / 2;
    std::vector<double> smoothed(width, 0.0);
    for (int x = 0; x < width; ++x) {
      double sum = 0.0;
      int count = 0;
      for (int k = -radius; k <= radius; ++k) {
        const int index = x + k;
        if (index < 0 || index >= width)
          continue;
        sum += histogram[index];
        ++count;
      }
      smoothed[x] = count > 0 ? sum / count : histogram[x];
    }

    const double peak = *std::max_element(smoothed.begin(), smoothed.end());
    if (peak <= 0.0)
      return measurement;

    const double threshold = std::max(peak * 0.32, 2.0);
    std::vector<std::pair<double, double>> clusters;
    int start = -1;
    for (int i = 0; i < width; ++i) {
      const bool active = smoothed[i] > threshold;
      if (active && start < 0) {
        start = i;
      } else if (!active && start >= 0) {
        appendCluster(smoothed, start, i - 1, clusters);
        start = -1;
      }
    }
    if (start >= 0)
      appendCluster(smoothed, start, width - 1, clusters);
    if (clusters.empty())
      return measurement;

    const double imageCenter = width * 0.5;
    const auto selected = *std::min_element(clusters.begin(), clusters.end(), [imageCenter](const auto &a, const auto &b) {
      return std::abs(a.first - imageCenter) < std::abs(b.first - imageCenter);
    });

    const double normalizedX = clamp(selected.first / std::max(1.0, static_cast<double>(width)), 0.0, 1.0);
    measurement.valid = true;
    measurement.lineX = normalizedX;
    measurement.lineIsLeft = normalizedX < 0.5;
    measurement.score = selected.second;
    measurement.pixelCount = pixelCount;
    measurement.clusterCount = static_cast<int>(clusters.size());
    return measurement;
  }

private:
  static void appendCluster(const std::vector<double> &histogram,
                            int start,
                            int end,
                            std::vector<std::pair<double, double>> &clusters) {
    double score = 0.0;
    double weightedX = 0.0;
    for (int x = start; x <= end; ++x) {
      score += histogram[x];
      weightedX += histogram[x] * x;
    }
    if (score > 0.0)
      clusters.emplace_back(weightedX / score, score);
  }
};

class RaspiReactiveLineFollower {
public:
  explicit RaspiReactiveLineFollower(int initialTimeMs)
      : m_lastLineSeenMs(initialTimeMs), m_cameraViewWidthCm(envDouble("WEBOTS_CAMERA_VIEW_CM", 20.0)) {
  }

  void reset(int frameWidth, int timeMs) {
    m_lastLineSeenMs = timeMs;
    m_lastSeenSide = Side::Unknown;
    m_pixelPerCm = std::max(1.0, static_cast<double>(frameWidth)) / m_cameraViewWidthCm;
  }

  MotorCommand update(const LaneMeasurement &measurement, int frameWidth, int timeMs) {
    if (!measurement.valid || measurement.lineX <= 0.02 || measurement.lineX >= 0.98)
      return searchMode(timeMs);

    const bool lineIsLeft = measurement.lineIsLeft;
    m_lastLineSeenMs = timeMs;
    m_lastSeenSide = lineIsLeft ? Side::Left : Side::Right;

    if (m_pixelPerCm <= 1e-6)
      m_pixelPerCm = std::max(1.0, static_cast<double>(frameWidth)) / m_cameraViewWidthCm;

    const double robotCenterPx = 0.5 * frameWidth;
    const double linePx = measurement.lineX * frameWidth;
    double distanceCm = lineIsLeft ? (robotCenterPx - linePx) / m_pixelPerCm : (linePx - robotCenterPx) / m_pixelPerCm;
    distanceCm = std::max(0.0, distanceCm);

    const double errorCm = kWallTargetCm - distanceCm;
    double steerMultiplier = 1.0;
    if (distanceCm < kDangerZoneCm)
      steerMultiplier = 1.0 + 2.0 * (1.0 - distanceCm / kDangerZoneCm);

    double turn = kSteerGain * errorCm * steerMultiplier;
    if (!lineIsLeft)
      turn = -turn;
    turn = std::tanh(turn);

    double baseSpeed = kBaseSpeed;
    if (distanceCm < kDangerZoneCm) {
      const double slowFactor = 0.75 + 0.25 * (distanceCm / kDangerZoneCm);
      baseSpeed *= slowFactor;
    }

    const double turnMagnitude = std::abs(turn);
    if (turnMagnitude > 0.3)
      baseSpeed *= 1.0 + turnMagnitude * 0.15;
    if (turnMagnitude < 0.15)
      baseSpeed *= 1.1;

    MotorCommand command;
    command.left = clamp(baseSpeed * (1.0 - turn), kMinPwm, kMaxPwm);
    command.right = clamp(baseSpeed * (1.0 + turn), kMinPwm, kMaxPwm);
    command.mode = distanceCm < kDangerZoneCm ? "DANGER" : "TRACK";
    command.distanceCm = distanceCm;
    command.errorCm = errorCm;
    command.turn = turn;
    command.baseSpeed = baseSpeed;
    command.lineX = measurement.lineX;
    command.lineSide = lineIsLeft ? 'L' : 'R';
    return command;
  }

private:
  enum class Side { Unknown, Left, Right };

  MotorCommand searchMode(int timeMs) const {
    const int elapsedMs = timeMs - m_lastLineSeenMs;

    if (elapsedMs < kNoLineTimeoutMs) {
      const double slowSpeed = kBaseSpeed * 0.7;
      MotorCommand command;
      command.left = slowSpeed;
      command.right = slowSpeed;
      command.mode = "SEARCH-FWD";
      return command;
    }

    if (elapsedMs < kNoLineTimeoutMs * 3) {
      MotorCommand command;
      if (m_lastSeenSide == Side::Left) {
        command.left = kSearchTurnSpeed;
        command.right = -kSearchTurnSpeed;
        command.mode = "SEARCH-TURN-L";
      } else {
        command.left = -kSearchTurnSpeed;
        command.right = kSearchTurnSpeed;
        command.mode = "SEARCH-TURN-R";
      }
      return command;
    }

    return MotorCommand{};
  }

  int m_lastLineSeenMs = 0;
  Side m_lastSeenSide = Side::Unknown;
  double m_pixelPerCm = 0.0;
  double m_cameraViewWidthCm = 20.0;
};

void setMotorVelocity(WbDeviceTag leftMotor, WbDeviceTag rightMotor, const MotorCommand &command) {
  wb_motor_set_velocity(leftMotor, kLeftMotorSign * command.left);
  wb_motor_set_velocity(rightMotor, kRightMotorSign * command.right);
}

void printStatus(const LaneMeasurement &measurement, const MotorCommand &command) {
  std::cout << std::fixed << std::setprecision(2);
  if (!measurement.valid) {
    std::cout << "[SIM] " << command.mode << " | L:" << command.left << " R:" << command.right << " | line:none\n";
    return;
  }

  std::cout << "[SIM] " << command.mode << "-" << command.lineSide << " | src:" << measurement.source
            << " x:" << command.lineX << " score:" << measurement.score << " hits:" << measurement.clusterCount
            << " dist:" << command.distanceCm << " err:" << command.errorCm << " turn:" << command.turn
            << " | L:" << command.left << " R:" << command.right << "\n";
}

}  // namespace

int main() {
  std::ofstream logFile("webots_controller_log.txt", std::ios::out | std::ios::trunc);
  if (logFile.is_open()) {
    std::cout.rdbuf(logFile.rdbuf());
    std::cerr.rdbuf(logFile.rdbuf());
  }

  wb_robot_init();

  try {
#ifdef _WIN32
    WsaSession wsaSession;
    if (!wsaSession.ok())
      throw std::runtime_error("WSAStartup failed");
#endif

    const int timestep = static_cast<int>(wb_robot_get_basic_time_step());

    WbDeviceTag camera = wb_robot_get_device(kCameraName);
    if (camera == 0)
      throw std::runtime_error(std::string("Camera not found: ") + kCameraName);
    wb_camera_enable(camera, timestep);

    WbDeviceTag leftMotor = wb_robot_get_device(kLeftMotorName);
    WbDeviceTag rightMotor = wb_robot_get_device(kRightMotorName);
    if (leftMotor == 0)
      throw std::runtime_error(std::string("Motor not found: ") + kLeftMotorName);
    if (rightMotor == 0)
      throw std::runtime_error(std::string("Motor not found: ") + kRightMotorName);

    wb_motor_set_position(leftMotor, std::numeric_limits<double>::infinity());
    wb_motor_set_position(rightMotor, std::numeric_limits<double>::infinity());
    wb_motor_set_velocity(leftMotor, 0.0);
    wb_motor_set_velocity(rightMotor, 0.0);

    const int width = wb_camera_get_width(camera);
    const int height = wb_camera_get_height(camera);
    const bool debugVerbose = envFlag("WEBOTS_DEBUG_VERBOSE", true);
    const bool colorFallback = envFlag("WEBOTS_NCNN_COLOR_FALLBACK", true);
    const int cameraPort = static_cast<int>(envDouble("WEBOTS_CAMERA_PORT", 8554));
    const int controlPort = static_cast<int>(envDouble("WEBOTS_CONTROL_PORT", 5005));
    const std::filesystem::path controllerDir = executableDir();

    NcnnLaneDetector ncnnDetector(controllerDir);
    ColorLaneDetector colorDetector;
    RaspiReactiveLineFollower follower(static_cast<int>(wb_robot_get_time() * 1000.0));
    follower.reset(width, static_cast<int>(wb_robot_get_time() * 1000.0));

#ifdef _WIN32
    CameraStreamServer cameraStreamServer(cameraPort);
    ControlCommandServer controlCommandServer(controlPort);
#endif

    std::cout << "[Webots] C++ NCNN controller started\n";
    std::cout << "[Webots] camera=" << width << "x" << height << " timestep=" << timestep << "ms\n";
    std::cout << "[NCNN] " << ncnnDetector.status() << "\n";
    std::cout << "[NCNN] color fallback=" << (colorFallback ? "on" : "off") << "\n";
#ifdef _WIN32
    std::cout << "[STREAM] " << cameraStreamServer.status() << "\n";
    std::cout << "[CONTROL] " << controlCommandServer.status() << "\n";
#endif

    int lastStatusMs = static_cast<int>(wb_robot_get_time() * 1000.0);
    while (wb_robot_step(timestep) != -1) {
      const int simTimeMs = static_cast<int>(wb_robot_get_time() * 1000.0);
      const unsigned char *image = wb_camera_get_image(camera);

#ifdef _WIN32
      cameraStreamServer.update(image, width, height, simTimeMs);
      controlCommandServer.update(simTimeMs);
#endif

      LaneMeasurement measurement = ncnnDetector.detect(image, width, height);
      if (!measurement.valid && colorFallback)
        measurement = colorDetector.detect(image, width, height);

      MotorCommand command = follower.update(measurement, width, simTimeMs);
#ifdef _WIN32
      if (controlCommandServer.hasRecentCommand(simTimeMs))
        command = controlCommandServer.command();
#endif
      setMotorVelocity(leftMotor, rightMotor, command);

      if (debugVerbose && simTimeMs - lastStatusMs >= kStatusIntervalMs) {
        lastStatusMs = simTimeMs;
        printStatus(measurement, command);
      }
    }
  } catch (const std::exception &error) {
    std::cerr << "[ERROR] " << error.what() << "\n";
    wb_robot_cleanup();
    return 1;
  }

  wb_robot_cleanup();
  return 0;
}
