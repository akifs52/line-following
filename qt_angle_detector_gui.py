import sys
import cv2
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QFileDialog, 
                             QComboBox, QTextEdit, QSpinBox, QCheckBox)
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt
from path_angle_detector import PathAngleDetector

class AngleDetectorGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.detector = PathAngleDetector()
        self.current_image = None
        self.processed_image = None
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("Path Angle Detector")
        self.setGeometry(100, 100, 1200, 800)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Left panel - Controls
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_panel.setLayout(left_layout)
        left_panel.setMaximumWidth(300)
        
        # File selection
        self.file_label = QLabel("No image selected")
        self.file_label.setWordWrap(True)
        left_layout.addWidget(QLabel("Image File:"))
        left_layout.addWidget(self.file_label)
        
        self.browse_button = QPushButton("Browse Image")
        self.browse_button.clicked.connect(self.browse_image)
        left_layout.addWidget(self.browse_button)
        
        # Method selection
        left_layout.addWidget(QLabel("Detection Method:"))
        self.method_combo = QComboBox()
        self.method_combo.addItems(["PCA", "Hough Lines"])
        left_layout.addWidget(self.method_combo)
        
        # Parameters
        left_layout.addWidget(QLabel("Threshold Value:"))
        self.threshold_spinbox = QSpinBox()
        self.threshold_spinbox.setRange(0, 255)
        self.threshold_spinbox.setValue(127)
        left_layout.addWidget(self.threshold_spinbox)
        
        # Options
        self.show_contour_checkbox = QCheckBox("Show Contour")
        self.show_contour_checkbox.setChecked(True)
        left_layout.addWidget(self.show_contour_checkbox)
        
        self.show_direction_checkbox = QCheckBox("Show Direction")
        self.show_direction_checkbox.setChecked(True)
        left_layout.addWidget(self.show_direction_checkbox)
        
        self.show_reference_checkbox = QCheckBox("Show Reference Line")
        self.show_reference_checkbox.setChecked(True)
        left_layout.addWidget(self.show_reference_checkbox)
        
        # Process button
        self.process_button = QPushButton("Detect Angle")
        self.process_button.clicked.connect(self.detect_angle)
        self.process_button.setEnabled(False)
        left_layout.addWidget(self.process_button)
        
        # Save button
        self.save_button = QPushButton("Save Result")
        self.save_button.clicked.connect(self.save_result)
        self.save_button.setEnabled(False)
        left_layout.addWidget(self.save_button)
        
        # Results
        left_layout.addWidget(QLabel("Results:"))
        self.results_text = QTextEdit()
        self.results_text.setMaximumHeight(150)
        self.results_text.setReadOnly(True)
        left_layout.addWidget(self.results_text)
        
        left_layout.addStretch()
        
        # Right panel - Image display
        right_panel = QWidget()
        right_layout = QVBoxLayout()
        right_panel.setLayout(right_layout)
        
        # Original image
        right_layout.addWidget(QLabel("Original Image:"))
        self.original_label = QLabel()
        self.original_label.setMinimumSize(400, 300)
        self.original_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.original_label.setStyleSheet("border: 1px solid gray;")
        right_layout.addWidget(self.original_label)
        
        # Processed image
        right_layout.addWidget(QLabel("Processed Image:"))
        self.processed_label = QLabel()
        self.processed_label.setMinimumSize(400, 300)
        self.processed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.processed_label.setStyleSheet("border: 1px solid gray;")
        right_layout.addWidget(self.processed_label)
        
        # Add panels to main layout
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)
    
    def browse_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Image File", "", 
            "Image Files (*.png *.jpg *.jpeg *.bmp *.tiff);;All Files (*)"
        )
        
        if file_path:
            self.current_image = cv2.imread(file_path)
            if self.current_image is not None:
                self.file_label.setText(file_path)
                self.process_button.setEnabled(True)
                self.display_image(self.current_image, self.original_label)
                self.results_text.clear()
                self.processed_label.clear()
                self.save_button.setEnabled(False)
            else:
                self.file_label.setText("Error: Could not load image")
    
    def detect_angle(self):
        if self.current_image is None:
            return
        
        try:
            # Get selected method
            method = "pca" if self.method_combo.currentText() == "PCA" else "hough"
            
            # Update detector threshold if needed
            threshold = self.threshold_spinbox.value()
            
            # Detect angle
            angle, center, direction = self.detector.detect_path_angle(self.current_image, method)
            
            if angle is not None:
                # Get direction text
                direction_text = self.detector.get_direction_text(angle)
                
                # Display results
                results_text = f"Method: {method.upper()}\n"
                results_text += f"Angle: {angle:.2f}° from vertical\n"
                results_text += f"Direction: {direction_text}\n"
                results_text += f"Center: ({center[0]}, {center[1]})\n"
                
                if direction is not None:
                    results_text += f"Vector: ({direction[0]:.3f}, {direction[1]:.3f})"
                
                self.results_text.setText(results_text)
                
                # Visualize results
                self.processed_image = self.detector.visualize_results(self.current_image)
                self.display_image(self.processed_image, self.processed_label)
                self.save_button.setEnabled(True)
            else:
                self.results_text.setText("Could not detect path angle")
                self.processed_label.clear()
                self.save_button.setEnabled(False)
                
        except Exception as e:
            self.results_text.setText(f"Error: {str(e)}")
            self.processed_label.clear()
    
    def display_image(self, cv_image, label):
        """Convert OpenCV image to Qt QPixmap and display"""
        try:
            # Convert BGR to RGB
            rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
            
            # Get image dimensions
            h, w, ch = rgb_image.shape
            
            # Convert to QImage
            bytes_per_line = ch * w
            qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            
            # Convert to QPixmap
            pixmap = QPixmap.fromImage(qt_image)
            
            # Scale to fit label while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            
            label.setPixmap(scaled_pixmap)
            
        except Exception as e:
            label.setText(f"Error displaying image: {str(e)}")
    
    def save_result(self):
        if self.processed_image is None:
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Result", "", 
            "Image Files (*.png *.jpg *.jpeg *.bmp);;All Files (*)"
        )
        
        if file_path:
            try:
                cv2.imwrite(file_path, self.processed_image)
                self.results_text.append(f"\nResult saved to: {file_path}")
            except Exception as e:
                self.results_text.append(f"\nError saving: {str(e)}")

def main():
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Create and show main window
    window = AngleDetectorGUI()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
