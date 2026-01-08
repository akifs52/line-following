import cv2
import numpy as np
from path_angle_detector import PathAngleDetector

def test_with_track_image():
    """Test the detector with the uploaded track image"""
    
    # For this test, we'll need to save the uploaded image as track_image.jpg
    # Then load it and test the detector
    
    detector = PathAngleDetector()
    
    # Load the track image (you'll need to save the uploaded image first)
    image_path = "track_image.jpg"
    
    try:
        # Load image
        image = cv2.imread(image_path)
        if image is None:
            print(f"Error: Could not load image from {image_path}")
            print("Please save the uploaded track image as 'track_image.jpg' in the same directory")
            return
        
        print(f"Image loaded successfully: {image.shape}")
        
        # Test with PCA method
        print("\n--- Testing with PCA method ---")
        angle_pca, center_pca, direction_pca = detector.detect_path_angle(image, method='pca')
        
        if angle_pca is not None:
            print(f"PCA Method - Angle: {angle_pca:.2f} degrees from vertical")
            print(f"Path center: {center_pca}")
            
            # Visualize PCA results
            result_pca = detector.visualize_results(image, "result_pca.jpg")
            print("PCA result saved as 'result_pca.jpg'")
        else:
            print("PCA method could not detect path angle")
        
        # Test with Hough Lines method
        print("\n--- Testing with Hough Lines method ---")
        angle_hough, center_hough, direction_hough = detector.detect_path_angle(image, method='hough')
        
        if angle_hough is not None:
            print(f"Hough Method - Angle: {angle_hough:.2f} degrees from vertical")
            print(f"Path center: {center_hough}")
            
            # Visualize Hough results
            result_hough = detector.visualize_results(image, "result_hough.jpg")
            print("Hough result saved as 'result_hough.jpg'")
        else:
            print("Hough method could not detect path angle")
            
    except Exception as e:
        print(f"Error during testing: {e}")

def analyze_track_properties():
    """Analyze the specific properties of this track image"""
    
    # This function will help us understand what we're working with
    # The track has white and yellow lines on a dark grey background
    
    detector = PathAngleDetector()
    
    image_path = "track_image.jpg"
    
    try:
        image = cv2.imread(image_path)
        if image is None:
            print("Please save the uploaded track image as 'track_image.jpg'")
            return
        
        # Analyze color channels
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # For white lines: high value, low saturation
        lower_white = np.array([0, 0, 200])
        upper_white = np.array([180, 30, 255])
        white_mask = cv2.inRange(hsv, lower_white, upper_white)
        
        # For yellow lines: specific hue range
        lower_yellow = np.array([20, 100, 100])
        upper_yellow = np.array([30, 255, 255])
        yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
        
        # Combine masks
        combined_mask = cv2.bitwise_or(white_mask, yellow_mask)
        
        # Save analysis results
        cv2.imwrite("white_lines.jpg", white_mask)
        cv2.imwrite("yellow_lines.jpg", yellow_mask)
        cv2.imwrite("combined_lines.jpg", combined_mask)
        
        print("Color analysis complete:")
        print("- White lines saved as 'white_lines.jpg'")
        print("- Yellow lines saved as 'yellow_lines.jpg'")
        print("- Combined lines saved as 'combined_lines.jpg'")
        
        # Count white pixels
        white_pixels = cv2.countNonZero(white_mask)
        yellow_pixels = cv2.countNonZero(yellow_mask)
        total_pixels = image.shape[0] * image.shape[1]
        
        print(f"\nImage statistics:")
        print(f"- Total pixels: {total_pixels}")
        print(f"- White line pixels: {white_pixels} ({100*white_pixels/total_pixels:.2f}%)")
        print(f"- Yellow line pixels: {yellow_pixels} ({100*yellow_pixels/total_pixels:.2f}%)")
        print(f"- Total line pixels: {white_pixels + yellow_pixels} ({100*(white_pixels + yellow_pixels)/total_pixels:.2f}%)")
        
    except Exception as e:
        print(f"Error during analysis: {e}")

if __name__ == "__main__":
    print("Track Image Angle Detector Test")
    print("=" * 40)
    
    print("\nFirst, let's analyze the track properties:")
    analyze_track_properties()
    
    print("\n" + "=" * 40)
    print("\nNow testing angle detection:")
    test_with_track_image()
    
    print("\nTest complete! Check the generated image files for results.")
