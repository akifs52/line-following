import cv2
import numpy as np
import math

class PathAngleDetector:
    def __init__(self):
        self.angle = 0
        self.path_center = None
        self.path_direction = None
    
    def preprocess_image(self, image):
        """Preprocess image to detect black path"""
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # For track with white/yellow lines on dark background, use different approach
        # First try to detect the lines (they should be brighter than background)
        _, binary = cv2.threshold(blurred, 127, 255, cv2.THRESH_BINARY)
        
        # If this doesn't work well, try adaptive thresholding
        if np.sum(binary) > binary.size * 0.5:  # If more than half is white, invert
            binary = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                         cv2.THRESH_BINARY, 11, 2)
            # Invert to make lines white
            binary = cv2.bitwise_not(binary)
        
        # Morphological operations to clean up
        kernel = np.ones((3, 3), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        
        return binary
    
    def find_path_contour(self, binary_image):
        """Find the largest contour which should be the path"""
        contours, _ = cv2.findContours(binary_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
        
        # Find the largest contour (assuming it's the path)
        largest_contour = max(contours, key=cv2.contourArea)
        
        # Filter out very small contours
        if cv2.contourArea(largest_contour) < 100:
            return None
            
        return largest_contour
    
    def calculate_angle_from_contour(self, contour, image_shape):
        """Calculate angle from contour using PCA or fitting"""
        if contour is None or len(contour) < 5:
            return None, None, None
        
        # Get contour points
        points = contour.reshape(-1, 2)
        
        # Method 1: PCA (Principal Component Analysis)
        mean = np.mean(points, axis=0)
        centered_points = points - mean
        
        # Calculate covariance matrix and eigenvectors
        cov_matrix = np.cov(centered_points.T)
        eigenvalues, eigenvectors = np.linalg.eig(cov_matrix)
        
        # Get the principal direction (largest eigenvalue)
        principal_idx = np.argmax(eigenvalues)
        direction_vector = eigenvectors[:, principal_idx]
        
        # Calculate angle from vertical axis
        angle_rad = math.atan2(direction_vector[1], direction_vector[0])
        angle_deg = math.degrees(angle_rad)
        
        # Adjust angle to be from vertical (0° = vertical, positive = clockwise)
        angle_from_vertical = angle_deg - 90
        if angle_from_vertical < -180:
            angle_from_vertical += 360
        elif angle_from_vertical > 180:
            angle_from_vertical -= 360
            
        return angle_from_vertical, tuple(mean.astype(int)), direction_vector
    
    def calculate_angle_with_hough_lines(self, binary_image):
        """Alternative method using Hough Line Transform"""
        # Edge detection
        edges = cv2.Canny(binary_image, 50, 150)
        
        # Hough Line Transform
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=50, 
                               minLineLength=50, maxLineGap=10)
        
        if lines is None:
            return None, None, None
        
        # Calculate average angle from all detected lines
        angles = []
        center_points = []
        
        for line in lines:
            x1, y1, x2, y2 = line[0]
            
            # Calculate angle
            angle_rad = math.atan2(y2 - y1, x2 - x1)
            angle_deg = math.degrees(angle_rad)
            
            # Adjust to be from vertical
            angle_from_vertical = angle_deg - 90
            if angle_from_vertical < -180:
                angle_from_vertical += 360
            elif angle_from_vertical > 180:
                angle_from_vertical -= 360
                
            angles.append(angle_from_vertical)
            center_points.append(((x1 + x2) // 2, (y1 + y2) // 2))
        
        # Average angle and center
        avg_angle = np.mean(angles)
        avg_center = tuple(np.mean(center_points, axis=0).astype(int))
        
        return avg_angle, avg_center, None
    
    def get_direction_text(self, angle):
        """Get human-readable direction text based on angle"""
        if angle is None:
            return "Unknown"
        
        # Normalize angle to -180 to 180 range
        if angle > 180:
            angle -= 360
        elif angle < -180:
            angle += 360
            
        # Determine direction based on angle ranges
        if -10 <= angle <= 10:
            return "İleri (Doğru)"
        elif 10 < angle <= 45:
            return "Sağ Çapraz"
        elif 45 < angle <= 90:
            return "Sağ"
        elif 90 < angle <= 135:
            return "Geri Sağ"
        elif 135 < angle <= 180 or -180 <= angle < -135:
            return "Geri"
        elif -135 <= angle < -90:
            return "Geri Sol"
        elif -90 <= angle < -45:
            return "Sol"
        elif -45 <= angle < -10:
            return "Sol Çapraz"
        else:
            return f"Açı: {angle:.1f}°"
    
    def detect_path_angle(self, image, method='pca'):
        """
        Main method to detect path angle
        
        Args:
            image: Input image (BGR format from OpenCV)
            method: 'pca' for Principal Component Analysis, 'hough' for Hough Lines
            
        Returns:
            angle: Angle in degrees from vertical axis
            center: Center point of the path
            direction: Direction vector
        """
        # Preprocess image
        binary = self.preprocess_image(image)
        
        # Find path contour
        contour = self.find_path_contour(binary)
        if contour is None:
            return None, None, None
        
        # Calculate angle based on method
        if method == 'pca':
            angle, center, direction = self.calculate_angle_from_contour(contour, image.shape)
        elif method == 'hough':
            angle, center, direction = self.calculate_angle_with_hough_lines(binary)
        else:
            raise ValueError("Method must be 'pca' or 'hough'")
        
        # Store results
        self.angle = angle
        self.path_center = center
        self.path_direction = direction
        
        return angle, center, direction
    
    def visualize_results(self, image, save_path=None):
        """Visualize the detection results"""
        if self.angle is None:
            return image
        
        result_image = image.copy()
        
        # Draw contour if we have it
        binary = self.preprocess_image(image)
        contour = self.find_path_contour(binary)
        if contour is not None:
            cv2.drawContours(result_image, [contour], -1, (0, 255, 0), 2)
        
        # Draw center point
        if self.path_center is not None:
            cv2.drawMarker(result_image, self.path_center, (0, 0, 255), 
                          cv2.MARKER_CROSS, 20, 2)
        
        # Draw direction line
        if self.path_center is not None and self.path_direction is not None:
            # Extend direction vector for visualization
            line_length = 100
            end_point = (
                int(self.path_center[0] + line_length * self.path_direction[0]),
                int(self.path_center[1] + line_length * self.path_direction[1])
            )
            cv2.line(result_image, self.path_center, end_point, (255, 0, 0), 3)
        
        # Draw angle text
        if self.angle is not None:
            cv2.putText(result_image, f"Angle: {self.angle:.1f} degrees", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        # Draw reference vertical line
        h, w = image.shape[:2]
        center_x = w // 2
        cv2.line(result_image, (center_x, 0), (center_x, h), (0, 165, 255), 2)
        
        if save_path:
            cv2.imwrite(save_path, result_image)
        
        return result_image

# Example usage function
def test_detector(image_path, output_path=None, method='pca'):
    """Test the path angle detector with an image"""
    detector = PathAngleDetector()
    
    # Load image
    image = cv2.imread(image_path)
    if image is None:
        print(f"Error: Could not load image from {image_path}")
        return None
    
    # Detect angle
    angle, center, direction = detector.detect_path_angle(image, method)
    
    if angle is not None:
        print(f"Detected angle: {angle:.2f} degrees from vertical")
        print(f"Path center: {center}")
        
        # Visualize results
        result_image = detector.visualize_results(image, output_path)
        
        return angle, center, direction, result_image
    else:
        print("Could not detect path angle")
        return None

if __name__ == "__main__":
    # Example usage
    print("Path Angle Detector")
    print("Usage: python path_angle_detector.py <image_path>")
    
    # You can test with an image like this:
    # test_detector("path_image.jpg", "result.jpg", method='pca')
