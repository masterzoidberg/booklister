"""
Image normalization service for eBay uploads
"""
import os
from pathlib import Path
from typing import List, Optional
from PIL import Image, ExifTags
import logging

logger = logging.getLogger(__name__)


def normalize_image(
    input_path: Path,
    output_path: Path,
    long_edge: int = 1600,
    quality: float = 0.88
) -> Path:
    """
    Normalize image: resize, rotate per EXIF, strip GPS/metadata, convert to JPEG.
    
    Args:
        input_path: Source image path
        output_path: Output path (will be .jpg)
        long_edge: Target long edge in pixels (default 1600)
        quality: JPEG quality 0-1 (default 0.88)
    
    Returns:
        Output path (guaranteed .jpg)
    
    Raises:
        ValueError: If image is invalid or cannot be processed
    """
    try:
        with Image.open(input_path) as img:
            # Apply EXIF rotation
            img = _apply_exif_rotation(img)
            
            # Resize if needed (maintain aspect ratio)
            img = _resize_if_needed(img, long_edge)
            
            # Convert to RGB if needed (strip alpha, convert grayscale/P)
            if img.mode != 'RGB':
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'RGBA' or img.mode == 'LA':
                    rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                else:
                    rgb_img.paste(img)
                img = rgb_img
            
            # Ensure output path is .jpg
            output_jpg = output_path.with_suffix('.jpg')
            
            # Save as JPEG (strips EXIF/GPS metadata automatically)
            img.save(
                output_jpg,
                'JPEG',
                quality=int(quality * 100),
                optimize=True
            )
            
            logger.info(f"Normalized {input_path} -> {output_jpg} ({img.size[0]}x{img.size[1]})")
            return output_jpg
            
    except Exception as e:
        logger.error(f"Failed to normalize {input_path}: {e}")
        raise ValueError(f"Image normalization failed: {e}")


def normalize_book_images(
    book_id: str,
    image_paths: List[Path],
    base_dir: Path,
    long_edge: int = 1600,
    quality: float = 0.88
) -> List[Path]:
    """
    Normalize multiple images for a book, deduplicated and ordered.
    
    Order priority:
    1. Cover images
    2. Spine
    3. Title page
    4. Copyright page
    5. Jacket flaps
    6. Back cover
    7. Condition close-ups
    
    Args:
        book_id: Book ID
        image_paths: List of input image paths
        base_dir: Base directory for normalized images
        long_edge: Target long edge in pixels
        quality: JPEG quality
    
    Returns:
        List of normalized image paths (JPEG)
    """
    if not image_paths:
        return []
    
    # Create normalized directory
    norm_dir = base_dir / book_id / "normalized"
    norm_dir.mkdir(parents=True, exist_ok=True)
    
    # Sort images by filename (assumes naming convention)
    sorted_paths = sorted(image_paths, key=lambda p: p.name.lower())
    
    # Deduplicate by file hash (simple: use filename for now)
    seen = set()
    deduped_paths = []
    for path in sorted_paths:
        if path.name not in seen:
            seen.add(path.name)
            deduped_paths.append(path)
    
    normalized = []
    for idx, input_path in enumerate(deduped_paths):
        output_path = norm_dir / f"norm_{idx:02d}.jpg"
        try:
            norm_path = normalize_image(input_path, output_path, long_edge, quality)
            normalized.append(norm_path)
        except Exception as e:
            logger.warning(f"Skipping {input_path} due to normalization error: {e}")
    
    return normalized


def _apply_exif_rotation(img: Image.Image) -> Image.Image:
    """Apply EXIF rotation if present"""
    try:
        # Get EXIF orientation tag
        exif = img.getexif()
        orientation = exif.get(274)  # Orientation tag
        
        if orientation == 3:
            img = img.rotate(180, expand=True)
        elif orientation == 6:
            img = img.rotate(270, expand=True)
        elif orientation == 8:
            img = img.rotate(90, expand=True)
        # Other orientations are already correct or no-op
        
    except Exception:
        # No EXIF or rotation not needed
        pass
    
    return img


def _resize_if_needed(img: Image.Image, long_edge: int) -> Image.Image:
    """Resize image if long edge exceeds target, maintaining aspect ratio"""
    width, height = img.size
    long_side = max(width, height)
    
    if long_side <= long_edge:
        return img
    
    # Calculate new dimensions
    if width > height:
        new_width = long_edge
        new_height = int(height * (long_edge / width))
    else:
        new_height = long_edge
        new_width = int(width * (long_edge / height))
    
    return img.resize((new_width, new_height), Image.Resampling.LANCZOS)

