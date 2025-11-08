"""
eBay Media API client for image uploads
"""
import asyncio
import logging
from pathlib import Path
from typing import List, Optional
import httpx
from settings import ebay_settings

logger = logging.getLogger(__name__)

# eBay Media API endpoint
# Note: Uses v1_beta endpoint with create_image_from_file method
MEDIA_API_ENDPOINT = "/commerce/media/v1_beta/image/create_image_from_file"

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0  # seconds


class MediaAPIError(Exception):
    """Base exception for Media API errors"""
    def __init__(self, message: str, request_id: Optional[str] = None):
        super().__init__(message)
        self.request_id = request_id


class MediaAPIAuthenticationError(MediaAPIError):
    """Authentication error (401)"""
    pass


class MediaAPIRateLimitError(MediaAPIError):
    """Rate limit error (429)"""
    pass


class MediaAPIValidationError(MediaAPIError):
    """Validation error (400)"""
    pass


class EbayMediaUploadError(MediaAPIError):
    """Rich Media API upload error with full context"""
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        request_id: Optional[str] = None,
        filename: Optional[str] = None
    ):
        super().__init__(message, request_id)
        self.status_code = status_code
        self.response_body = response_body
        self.filename = filename
    
    def __str__(self) -> str:
        parts = [self.args[0]]
        if self.status_code:
            parts.append(f"status={self.status_code}")
        if self.request_id:
            parts.append(f"request_id={self.request_id}")
        if self.filename:
            parts.append(f"file={self.filename}")
        if self.response_body:
            parts.append(f"response={self.response_body[:200]}")
        return " | ".join(parts)


async def upload_from_file(
    image_path: Path,
    token: str,
    base_url: Optional[str] = None
) -> str:
    """
    Upload image file to eBay Media API and return EPS URL.
    
    Args:
        image_path: Path to local image file
        token: OAuth bearer token
        base_url: eBay Media API base URL (defaults from settings, uses correct sandbox URL)
    
    Returns:
        EPS URL (e.g., https://i.ebayimg.com/images/...)
    
    Raises:
        EbayMediaUploadError: On upload failure with full context
        ValueError: On invalid input
    """
    base_url = base_url or ebay_settings.get_media_api_base_url()
    url = f"{base_url}{MEDIA_API_ENDPOINT}"
    
    # Validate file exists and is readable
    if not image_path.exists():
        raise ValueError(f"Image not found: {image_path}")
    
    if not image_path.is_file():
        raise ValueError(f"Path is not a file: {image_path}")
    
    # Validate image type and size
    _validate_image_file(image_path)
    
    # Determine content type from file extension
    ext = image_path.suffix.lower()
    content_type_map = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
        '.tiff': 'image/tiff',
        '.webp': 'image/webp'
    }
    content_type = content_type_map.get(ext, 'image/jpeg')

    # Prepare headers with token and marketplace ID
    # Note: Media API accepts binary data with Content-Type: image/*
    headers = _headers(token, content_type)

    # Retry wrapper
    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"Upload attempt {attempt + 1}/{MAX_RETRIES} for {image_path.name}")

                # eBay Media API requires multipart/form-data for file uploads
                # Remove Content-Type from headers (httpx will set it with boundary for multipart)
                upload_headers = {
                    'Authorization': headers['Authorization'],
                    'X-EBAY-C-MARKETPLACE-ID': headers['X-EBAY-C-MARKETPLACE-ID'],
                    'Accept': headers['Accept']
                }
                
                # Open file and send as multipart form data
                with open(image_path, 'rb') as f:
                    files = {
                        'image': (image_path.name, f, content_type)
                    }
                    response = await client.post(
                        url,
                        files=files,
                        headers=upload_headers
                    )
                
                # Validate HTTP response
                if response.status_code != 201:
                    response.raise_for_status()
                
                # Parse response to get imageId and EPS URL
                data = response.json()
                request_id = _get_request_id(response)
                image_id = data.get('imageId')
                eps_url = data.get('imageUrl', '')
                
                # If imageUrl is not in response but imageId is, we can construct URL
                # or fetch it separately. For now, require imageUrl.
                if not eps_url:
                    if image_id:
                        # Try to get URL from Location header or fetch separately
                        location = response.headers.get('Location', '')
                        if location:
                            logger.warning(
                                f"Response has imageId={image_id} but no imageUrl. Location: {location}",
                                extra={"request_id": request_id}
                            )
                        raise EbayMediaUploadError(
                            f"No imageUrl in response (imageId={image_id})",
                            status_code=response.status_code,
                            response_body=response.text,
                            request_id=request_id,
                            filename=image_path.name
                        )
                    else:
                        raise EbayMediaUploadError(
                            f"No imageId or imageUrl in response: {data}",
                            status_code=response.status_code,
                            response_body=response.text,
                            request_id=request_id,
                            filename=image_path.name
                        )
                
                # Validate EPS URL is HTTPS
                if not eps_url.startswith('https://'):
                    raise EbayMediaUploadError(
                        f"Invalid EPS URL format (must be HTTPS): {eps_url}",
                        status_code=response.status_code,
                        response_body=response.text,
                        request_id=request_id,
                        filename=image_path.name
                    )
                
                logger.info(
                    f"Uploaded {image_path.name} -> imageId={image_id}, URL={eps_url}",
                    extra={"request_id": request_id, "image_id": image_id}
                )
                logger.debug(f"Upload successful for {image_path.name}")
                return eps_url
                
            except httpx.HTTPStatusError as e:
                response = e.response
                request_id = _get_request_id(response) if response else None
                status_code = response.status_code if response else None
                
                # Extract full error details
                try:
                    error_body = response.json() if response else {}
                    error_detail = error_body.get('errors', [{}])
                    if error_detail and isinstance(error_detail, list) and len(error_detail) > 0:
                        error_msg_text = error_detail[0].get('message', '')
                        if not error_msg_text:
                            error_msg_text = str(error_body)
                    else:
                        error_msg_text = str(error_body) if error_body else ''
                except:
                    error_msg_text = response.text if response else str(e)
                
                # Log full response details for debugging
                response_headers = dict(response.headers) if response else {}
                logger.error(
                    f"Media API upload failed for {image_path.name}: "
                    f"status={status_code}, "
                    f"url={url}, "
                    f"request_id={request_id}, "
                    f"response_body={error_msg_text[:500]}, "
                    f"headers={response_headers.get('X-EBAY-C-REQUEST-ID', 'N/A')}",
                    extra={"request_id": request_id, "status_code": status_code}
                )
                
                # Retry logic for specific status codes
                if attempt < MAX_RETRIES - 1 and response:
                    if status_code == 429:
                        retry_after = int(response.headers.get('Retry-After', '0'))
                        wait_time = max(retry_after, _backoff_time(attempt))
                        logger.warning(
                            f"Rate limited (429), waiting {wait_time}s before retry",
                            extra={"request_id": request_id}
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    elif status_code and status_code >= 500:
                        wait_time = _backoff_time(attempt)
                        logger.warning(
                            f"Server error {status_code}, waiting {wait_time}s before retry",
                            extra={"request_id": request_id}
                        )
                        await _backoff(attempt)
                        continue
                
                # Final error - raise exception with full context
                error_msg = f"Media API upload failed: {status_code} - {error_msg_text}"
                raise EbayMediaUploadError(
                    error_msg,
                    status_code=status_code,
                    response_body=error_msg_text,
                    request_id=request_id,
                    filename=image_path.name
                ) from e
                
            except httpx.RequestError as e:
                error_msg = f"Media API request error: {e}"
                if attempt < MAX_RETRIES - 1:
                    logger.warning(
                        f"Network error on attempt {attempt + 1}: {e}, retrying...",
                        extra={"request_id": None}
                    )
                    await _backoff(attempt)
                    continue
                raise EbayMediaUploadError(
                    error_msg,
                    filename=image_path.name
                ) from e
                
            except (EbayMediaUploadError, MediaAPIError, ValueError) as e:
                # Don't retry validation or business logic errors
                raise
                
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(
                        f"Upload attempt {attempt + 1} failed: {e}, retrying...",
                        extra={"request_id": None}
                    )
                    await _backoff(attempt)
                    continue
                raise EbayMediaUploadError(
                    f"Upload failed after {MAX_RETRIES} attempts: {e}",
                    filename=image_path.name
                ) from e
        
        # Should not reach here
        raise EbayMediaUploadError(
            f"Upload failed after {MAX_RETRIES} attempts",
            filename=image_path.name
        )


async def upload_many(
    image_paths: List[Path],
    token: str,
    base_url: Optional[str] = None,
    skip_health_check: bool = False
) -> List[str]:
    """
    Upload multiple images sequentially, returning EPS URLs.
    
    Args:
        image_paths: List of image file paths
        token: OAuth bearer token
        base_url: eBay Media API base URL (defaults from settings)
        skip_health_check: Skip health check before batch upload (default: False)
    
    Returns:
        List of EPS URLs in same order as input
    
    Raises:
        EbayMediaUploadError: On upload failure
        ValueError: On invalid input (empty list, too many images)
    """
    if not image_paths:
        raise ValueError("Empty image list")
    
    max_images = ebay_settings.media_max_images
    if len(image_paths) > max_images:
        raise ValueError(f"Too many images: {len(image_paths)} > {max_images}")
    
    # Perform health check before batch upload
    if not skip_health_check:
        logger.info("Performing Media API health check before batch upload...")
        if not await health_check(token, base_url):
            raise EbayMediaUploadError(
                "Media API health check failed. Verify endpoint URL and OAuth token."
            )
        logger.info("Media API health check passed")
    
    eps_urls = []
    errors = []
    
    for idx, path in enumerate(image_paths):
        try:
            eps_url = await upload_from_file(path, token, base_url)
            eps_urls.append(eps_url)
            logger.info(f"Uploaded image {idx + 1}/{len(image_paths)}: {path.name}")
        except Exception as e:
            error_msg = f"Failed to upload {path.name}: {e}"
            request_id = getattr(e, 'request_id', None)
            status_code = getattr(e, 'status_code', None)
            logger.error(
                error_msg,
                extra={"request_id": request_id, "status_code": status_code}
            )
            errors.append(error_msg)
            # Continue with other images
    
    if not eps_urls:
        raise EbayMediaUploadError(f"All uploads failed: {errors}")
    
    if errors:
        logger.warning(f"Some uploads failed: {errors}")
    
    return eps_urls


def _headers(token: str, content_type: str = 'image/jpeg') -> dict:
    """Build request headers with bearer token and marketplace ID"""
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': content_type,
        'X-EBAY-C-MARKETPLACE-ID': ebay_settings.ebay_marketplace_id,
        'Accept': 'application/json'
    }


def _validate_image_file(path: Path) -> None:
    """Validate image file before upload"""
    # Check file size (10MB limit)
    file_size = path.stat().st_size
    max_size = 10 * 1024 * 1024  # 10MB
    
    if file_size > max_size:
        raise ValueError(f"Image too large: {file_size} bytes > {max_size} bytes")
    
    # Check extension
    ext = path.suffix.lower()
    allowed_exts = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
    
    if ext not in allowed_exts:
        raise ValueError(f"Invalid image format: {ext}, allowed: {allowed_exts}")
    
    # Check minimum size (long edge)
    try:
        from PIL import Image
        with Image.open(path) as img:
            width, height = img.size
            long_edge = max(width, height)
            min_long_edge = ebay_settings.media_min_long_edge
            
            if long_edge < min_long_edge:
                raise ValueError(
                    f"Image too small: {long_edge}px < {min_long_edge}px (long edge)"
                )
    except Exception as e:
        raise ValueError(f"Cannot validate image: {e}")


def _raise_error_from_response(response: httpx.Response, request_id: Optional[str]) -> None:
    """Raise appropriate exception from error response"""
    status_code = response.status_code
    
    if request_id is None:
        request_id = _get_request_id(response)
    
    if status_code == 401:
        raise MediaAPIAuthenticationError(
            "Authentication failed - token may be expired",
            request_id=request_id
        )
    
    if status_code == 429:
        raise MediaAPIRateLimitError(
            "Rate limit exceeded",
            request_id=request_id
        )
    
    if status_code == 400:
        try:
            error_data = response.json()
            error_msg = error_data.get('errors', [{}])[0].get('message', 'Bad request')
        except:
            error_msg = "Bad request"
        
        raise MediaAPIValidationError(
            f"Validation error: {error_msg}",
            request_id=request_id
        )
    
    # Other errors
    try:
        error_data = response.json()
        error_msg = error_data.get('errors', [{}])[0].get('message', f"HTTP {status_code}")
    except:
        error_msg = f"HTTP {status_code}"
    
    raise MediaAPIError(
        f"Upload failed: {error_msg}",
        request_id=request_id
    )


async def _backoff(attempt: int) -> None:
    """Wait before retry with exponential backoff"""
    wait_time = _backoff_time(attempt)
    await asyncio.sleep(wait_time)


def _backoff_time(attempt: int) -> float:
    """Calculate backoff time for attempt"""
    return INITIAL_BACKOFF * (2 ** attempt)


def _get_request_id(response: httpx.Response) -> Optional[str]:
    """Extract eBay request-id from response headers"""
    return (
        response.headers.get('X-EBAY-C-REQUEST-ID') or
        response.headers.get('X-EBAY-REQUEST-ID') or
        response.headers.get('X-Request-ID')
    )


async def health_check(token: str, base_url: Optional[str] = None) -> bool:
    """
    Verify Media API endpoint is accessible and token is valid.
    
    Note: Media API endpoint doesn't support HEAD/GET, so we skip health check
    and rely on actual upload to validate. Returns True to allow upload attempt.
    
    Args:
        token: OAuth bearer token
        base_url: eBay Media API base URL (defaults from settings)
    
    Returns:
        True (always, since health check not supported by endpoint)
    """
    # Media API endpoint doesn't support HEAD/GET requests for health checking
    # We'll validate during actual upload instead
    logger.debug("Media API health check skipped (endpoint doesn't support HEAD/GET)")
    return True

