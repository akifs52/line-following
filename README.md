[tcpyayın.txt](https://github.com/user-attachments/files/23903675/tcpyayin.txt)


ffmpeg -f v4l2 -i /dev/video0 -c:v libx264 -preset ultrafast -b:v 2M -f mpegts tcp://192.168.109.203:2002?listen=1
ffmpeg -f v4l2 -framerate 30 -video_size 640x480 -i /dev/video0 -c:v libx264 -preset ultrafast -tune zerolatency -b:v 500k -fflags nobuffer -flags low_delay -an -f mpegts tcp://192.168.109.203:2002?listen=1
v4l2-ctl --list-devices
ffmpeg -f v4l2 -t 5 -i /dev/video0 -c:v libx264 -preset ultrafast -tune zerolatency -b:v 500k -an output.mp4


"http://192.168.109.70:8080?action=stream"




git clone https://github.com/jacksonliam/mjpg-streamer.git



cd mjpg-streamer/mjpg-streamer-experimental
make
sudo make install


mjpg_streamer -i "input_uvc.so -d /dev/video0 -r 640x480 -f 30" \
              -o "output_http.so -p 8080 -w ./www"
