"""
Filesystem service for safe file operations
"""
import os
import uuid
import shutil
from pathlib import Path
from typing import List, Tuple, Optional
from fastapi import UploadFile, HTTPException
from PIL import Image as PILImage
import logging

logger = logging.getLogger(__name__)

# Configuration
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.tiff', '.tif'}
ALLOWED_MIME_TYPES = {
    'image/jpeg', 'image/png', 'image/webp', 'image/tiff'
}

class FilesystemService:
    """Handles safe file operations for book images"""
    
    def __init__(self, base_dir: str = "data/images"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def validate_file(self, file: UploadFile) -> None:
        """Validate file size and type"""
        if file.size and file.size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413, 
                detail=f"File too large: {file.filename} (max 10MB)"
            )
        
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")
        
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {file_ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        
        if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid MIME type: {file.content_type}"
            )
    
    def get_image_dimensions(self, file_path: Path) -> Tuple[int, int]:
        """Get image dimensions safely"""
        try:
            with PILImage.open(file_path) as img:
                return img.size
        except Exception as e:
            logger.warning(f"Could not read image dimensions for {file_path}: {e}")
            return (0, 0)
    
    def create_book_directory(self, book_id: str) -> Path:
        """Create directory for a book's images"""
        book_dir = self.base_dir / book_id
        book_dir.mkdir(parents=True, exist_ok=True)
        return book_dir
    
    def save_file(self, file: UploadFile, book_id: str) -> Tuple[str, int, int]:
        """Save a file and return (filename, width, height)"""
        self.validate_file(file)
        
        book_dir = self.create_book_directory(book_id)
        
        # Generate unique filename
        file_ext = Path(file.filename).suffix.lower()
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = book_dir / unique_filename
        
        try:
            # Save file
            with open(file_path, "wb") as buffer:
                content = file.file.read()
                if len(content) > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large: {file.filename} (max 10MB)"
                    )
                buffer.write(content)
            
            # Get dimensions
            width, height = self.get_image_dimensions(file_path)
            
            logger.info(f"Saved file: {file_path} ({width}x{height})")
            return str(unique_filename), width, height
            
        except Exception as e:
            # Clean up on failure
            if file_path.exists():
                file_path.unlink()
            logger.error(f"Failed to save file {file.filename}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save file: {str(e)}"
            )
        finally:
            file.file.close()
    
    def delete_book_directory(self, book_id: str) -> bool:
        """Delete a book's entire image directory"""
        book_dir = self.base_dir / book_id
        try:
            if book_dir.exists():
                shutil.rmtree(book_dir)
                logger.info(f"Deleted book directory: {book_dir}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete book directory {book_id}: {e}")
            return False
    
    def get_file_path(self, book_id: str, filename: str) -> Path:
        """Get full path to a file"""
        return self.base_dir / book_id / filename
    
    def file_exists(self, book_id: str, filename: str) -> bool:
        """Check if file exists"""
        return self.get_file_path(book_id, filename).exists()

# Global instance
fs_service = FilesystemService()
