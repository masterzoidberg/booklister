"""
Create minimal test fixtures for OCR testing.
"""

import os
import sys

# Add parent directory to path to import backend modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def create_test_images():
    """Create minimal test images for OCR testing."""
    try:
        import numpy as np
        import cv2
        
        fixtures_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Create a simple 100x50 black image
        black_img = np.zeros((50, 100, 3), dtype=np.uint8)
        cv2.imwrite(os.path.join(fixtures_dir, "black_100x50.png"), black_img)
        
        # Create a simple 100x50 white image
        white_img = np.ones((50, 100, 3), dtype=np.uint8) * 255
        cv2.imwrite(os.path.join(fixtures_dir, "white_100x50.png"), white_img)
        
        # Create a simple grayscale pattern
        gray_img = np.ones((50, 100, 3), dtype=np.uint8) * 128
        cv2.imwrite(os.path.join(fixtures_dir, "gray_100x50.png"), gray_img)
        
        print("Created test images successfully")
        
    except ImportError:
        print("OpenCV not available - skipping test image creation")
        # Create empty placeholder files
        fixtures_dir = os.path.dirname(os.path.abspath(__file__))
        for name in ["black_100x50.png", "white_100x50.png", "gray_100x50.png"]:
            with open(os.path.join(fixtures_dir, name), 'wb') as f:
                f.write(b"")

if __name__ == "__main__":
    create_test_images()
