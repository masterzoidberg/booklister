# Strategy B: eBay Media API Upload - Implementation Guide

## Overview

**Strategy B: eBay Media API Upload** is the production-ready solution that uploads images directly to eBay Picture Services (EPS), eliminating the need for public hosting. Images are stored on eBay's servers and URLs are provided for use in inventory items.

---

## Key Benefits

✅ **No Public Hosting Required**  
- Images uploaded directly to eBay's servers
- No need for external hosting or CDN
- Works with local-first architecture

✅ **Reliable & Permanent**  
- Images hosted by eBay Picture Services (EPS)
- Permanent URLs that don't expire (or expire far in future)
- Automatic optimization and CDN distribution

✅ **Production-Ready**  
- Works in production without tunnels
- No external dependencies
- Simplified deployment

---

## eBay Media API Endpoints

### Base URL
- **Production:** `https://api.ebay.com/commerce/media/v1_beta`
- **Sandbox:** `https://api.sandbox.ebay.com/commerce/media/v1_beta`

### Endpoints

#### 1. Upload Image from File
**Endpoint:** `POST /commerce/media/v1_beta/image`

**Method:** `createImageFromFile`

**Request:**
- **Method:** POST
- **Content-Type:** `multipart/form-data`
- **Headers:**
  - `Authorization: Bearer {access_token}`
  - `Content-Type: multipart/form-data`
- **Body:** File upload in multipart form

**Response:**
- **Status:** `201 Created`
- **Headers:**
  - `Location: /commerce/media/v1_beta/image/{image_id}` (contains image_id)
- **Body:** Image details including URL

**Example Response:**
```json
{
  "imageId": "v1|1234567890|0",
  "imageUrl": "https://i.ebayimg.com/images/g/ABC123/image.jpg",
  "expirationDate": "2025-12-31T23:59:59Z"
}
```

#### 2. Upload Image from URL
**Endpoint:** `POST /commerce/media/v1_beta/image?source=URL`

**Method:** `createImageFromUrl`

**Request:**
- **Method:** POST
- **Content-Type:** `application/json`
- **Headers:**
  - `Authorization: Bearer {access_token}`
  - `Content-Type: application/json`
- **Body:**
```json
{
  "imageUrl": "https://your-source-url.com/image.jpg"
}
```

**Response:** Same as file upload

#### 3. Get Image Details
**Endpoint:** `GET /commerce/media/v1_beta/image/{image_id}`

**Method:** `getImage`

**Request:**
- **Method:** GET
- **Headers:**
  - `Authorization: Bearer {access_token}`

**Response:**
```json
{
  "imageId": "v1|1234567890|0",
  "imageUrl": "https://i.ebayimg.com/images/g/ABC123/image.jpg",
  "expirationDate": "2025-12-31T23:59:59Z"
}
```

---

## Authentication

**Required Scopes:**
- OAuth token from user authorization (same as Inventory API)
- Uses same token as `sell.inventory` scope

**Headers:**
```
Authorization: Bearer {access_token}
```

**Token Source:**
- Use same token from `token_store.refresh_if_needed()`
- Same token works for Media API and Inventory API

---

## Implementation for BookLister AI

### Module Structure

**New Module:** `integrations/ebay/media.py`

**Purpose:** Handle image uploads to eBay Picture Services

### Functions

#### 1. Upload Single Image

```python
from typing import Optional
from pathlib import Path
import httpx
import logging

logger = logging.getLogger(__name__)

async def upload_image_to_ebay(
    image_path: str,
    token: str,
    base_url: str = "https://api.ebay.com"
) -> dict:
    """
    Upload image to eBay Picture Services (EPS) and return image details.
    
    Args:
        image_path: Local file path to image
        token: OAuth access token
        base_url: eBay API base URL (production or sandbox)
    
    Returns:
        Dict with image_id, imageUrl, expirationDate
    
    Raises:
        HTTPException: If upload fails
    """
    media_api_url = f"{base_url}/commerce/media/v1_beta/image"
    
    # Open image file
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    
    with open(path, 'rb') as f:
        files = {'image': (path.name, f, 'image/jpeg')}  # Adjust MIME type as needed
        
        headers = {
            'Authorization': f'Bearer {token}'
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                media_api_url,
                files=files,
                headers=headers,
                timeout=30.0
            )
            
            if response.status_code == 201:
                # Extract image_id from Location header
                location = response.headers.get('Location', '')
                image_id = location.split('/')[-1] if location else None
                
                # Get image details from response body or Location header
                image_data = response.json() if response.content else {}
                
                return {
                    'image_id': image_id,
                    'image_url': image_data.get('imageUrl', ''),
                    'expiration_date': image_data.get('expirationDate', '')
                }
            else:
                error_data = response.json() if response.content else {}
                logger.error(f"eBay Media API upload failed: {response.status_code} - {error_data}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Image upload failed: {error_data.get('errors', [{}])[0].get('message', 'Unknown error')}"
                )
```

#### 2. Upload Multiple Images

```python
async def upload_book_images_to_ebay(
    book: "Book",
    token: str,
    base_url: str = "https://api.ebay.com",
    base_image_path: str = "data/images"
) -> list[str]:
    """
    Upload all book images to eBay and return list of eBay-hosted URLs.
    
    Args:
        book: Book model with images relationship
        token: OAuth access token
        base_url: eBay API base URL
        base_image_path: Base directory for local images
    
    Returns:
        List of eBay-hosted image URLs
    """
    if not book.images:
        return []
    
    image_urls = []
    for img in book.images:
        # Build local file path
        filename = img.path.split('/')[-1]
        local_path = f"{base_image_path}/{book.id}/{filename}"
        
        try:
            # Upload to eBay
            result = await upload_image_to_ebay(local_path, token, base_url)
            image_urls.append(result['image_url'])
            logger.info(f"Uploaded image to eBay: {filename} -> {result['image_url']}")
        except Exception as e:
            logger.error(f"Failed to upload image {filename}: {e}")
            raise  # Or continue to next image, depending on requirements
    
    return image_urls
```

#### 3. Get Image Details (Optional)

```python
async def get_ebay_image_details(
    image_id: str,
    token: str,
    base_url: str = "https://api.ebay.com"
) -> dict:
    """
    Get details of an uploaded eBay image.
    
    Args:
        image_id: eBay image ID
        token: OAuth access token
        base_url: eBay API base URL
    
    Returns:
        Dict with image details
    """
    api_url = f"{base_url}/commerce/media/v1_beta/image/{image_id}"
    
    headers = {
        'Authorization': f'Bearer {token}'
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(api_url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            error_data = response.json() if response.content else {}
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to get image details: {error_data}"
            )
```

---

## Integration with Publish Pipeline

### Updated Publish Flow

**Modified:** `integrations/ebay/publish.py`

```python
async def upsert_and_publish(
    book_id: str,
    session: Session
) -> Dict[str, Any]:
    """
    Orchestrates full publish flow with eBay Media API image upload.
    """
    # 1. Get token (refresh if needed)
    token = await token_store.refresh_if_needed("ebay", session)
    if not token:
        raise HTTPException(status_code=401, detail="No eBay token available")
    
    # 2. Get book with images
    book = session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    # 3. Upload images to eBay Media API
    from integrations.ebay.media import upload_book_images_to_ebay
    from integrations.ebay.config import get_api_base_url
    
    api_base_url = get_api_base_url()
    ebay_image_urls = await upload_book_images_to_ebay(
        book=book,
        token=token.access_token,
        base_url=api_base_url
    )
    
    if not ebay_image_urls:
        raise HTTPException(
            status_code=400,
            detail="No images uploaded to eBay"
        )
    
    # 4. Build inventory item with eBay-hosted image URLs
    inventory_item = build_inventory_item(
        book=book,
        image_urls=ebay_image_urls  # Use eBay-hosted URLs instead of local URLs
    )
    
    # 5. Create/replace inventory item
    # ... rest of publish flow
```

### Updated Inventory Item Building

```python
def build_inventory_item(
    book: Book,
    image_urls: List[str],  # Already eBay-hosted URLs
    condition_id: int
) -> Dict[str, Any]:
    """
    Build inventory item payload with eBay-hosted image URLs.
    
    Args:
        book: Book model
        image_urls: List of eBay-hosted image URLs (from Media API)
        condition_id: eBay condition ID
    """
    return {
        "sku": book.sku or book.id,
        "product": {
            "title": (book.title_ai or book.title or "")[:80],
            "description": book.description_ai or "",
            "imageUrls": image_urls,  # eBay-hosted URLs
            "aspects": _build_aspects(book),
            "condition": str(condition_id),
            "brand": book.publisher or None
        }
    }
```

---

## Error Handling

### Common Errors

| Status Code | Error | Solution |
|-------------|-------|----------|
| 401 | Unauthorized | Token expired, refresh and retry |
| 400 | Bad Request | Invalid image format/size, validate before upload |
| 413 | Payload Too Large | Image too large, resize or compress |
| 429 | Rate Limited | Implement exponential backoff |

### Retry Logic

```python
async def upload_image_with_retry(
    image_path: str,
    token: str,
    max_retries: int = 3,
    base_url: str = "https://api.ebay.com"
) -> dict:
    """Upload image with retry logic."""
    for attempt in range(max_retries):
        try:
            return await upload_image_to_ebay(image_path, token, base_url)
        except HTTPException as e:
            if e.status_code == 429:  # Rate limited
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    await asyncio.sleep(wait_time)
                    continue
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue
            raise
```

---

## Image Requirements

### Format Requirements
- **Supported:** JPG, GIF, PNG, BMP, TIFF, AVIF, HEIC, WEBP
- **Current BookLister AI:** JPG, PNG, WEBP, TIFF ✅ (compatible)

### Size Requirements
- **Minimum:** 500 pixels on longest side
- **Maximum:** No hard limit, but recommended < 10MB
- **Current BookLister AI:** Validates max 10MB ✅

### Quality Requirements
- Avoid "Save for Web" compression
- High-quality images preferred
- eBay will optimize automatically

---

## Configuration

### Environment Variables

```bash
# eBay Media API (uses same base URL as Inventory API)
EBAY_ENV=production
EBAY_CLIENT_ID=your_ebay_client_id
EBAY_CLIENT_SECRET=your_ebay_client_secret

# Image upload settings
EBAY_UPLOAD_IMAGES=true  # Enable Media API upload (Strategy B)
EBAY_IMAGE_BASE_PATH=data/images  # Local image storage path
```

### Feature Flag

```python
# In config.py
USE_EBAY_MEDIA_API = os.getenv("EBAY_UPLOAD_IMAGES", "true").lower() == "true"

# In publish.py
if USE_EBAY_MEDIA_API:
    # Strategy B: Upload to eBay Media API
    ebay_image_urls = await upload_book_images_to_ebay(book, token)
else:
    # Strategy A: Use public URLs (tunnel/cloud storage)
    ebay_image_urls = _build_public_urls(book, base_url)
```

---

## Workflow Summary

### Complete Flow (Strategy B)

1. **User clicks "Publish to eBay"**
2. **Upload Images to eBay Media API**
   - For each image in `book.images`:
     - Read local file: `data/images/{book_id}/{filename}`
     - POST to `/commerce/media/v1_beta/image`
     - Get eBay-hosted URL: `https://i.ebayimg.com/...`
3. **Build Inventory Item**
   - Use eBay-hosted URLs in `product.imageUrls[]`
4. **Create Inventory Item**
   - PUT `/sell/inventory/v1/inventory_item/{sku}`
5. **Create Offer**
   - POST `/sell/inventory/v1/offer`
6. **Publish Offer**
   - POST `/sell/inventory/v1/offer/{offerId}/publish`

---

## Advantages vs. Alternatives

### Strategy B (Media API) vs. Strategy A (Public URLs)

| Feature | Strategy B (Media API) | Strategy A (Public URLs) |
|---------|----------------------|------------------------|
| **Public Hosting** | ❌ Not required | ✅ Required |
| **Tunnel Needed** | ❌ No | ✅ Yes (for dev) |
| **API Calls** | ⚠️ 1 per image | ✅ 0 |
| **Reliability** | ✅ High (eBay hosted) | ⚠️ Depends on hosting |
| **URL Stability** | ✅ Permanent | ⚠️ Depends on hosting |
| **Production Ready** | ✅ Yes | ⚠️ Requires infrastructure |
| **Complexity** | ⚠️ Medium | ✅ Low |

---

## Testing

### Unit Tests

```python
async def test_upload_image_to_ebay():
    """Test image upload to eBay Media API."""
    # Mock httpx response
    # Test successful upload
    # Test error handling
    pass

async def test_upload_book_images():
    """Test uploading multiple book images."""
    # Mock book with images
    # Test upload of all images
    # Test error handling for failed uploads
    pass
```

### Integration Tests

```python
async def test_full_publish_with_media_api():
    """Test complete publish flow with Media API."""
    # 1. Create test book with images
    # 2. Upload images to eBay
    # 3. Verify eBay URLs returned
    # 4. Create inventory item with eBay URLs
    # 5. Verify listing created successfully
    pass
```

---

## Official eBay Documentation

- **Media API Overview:** https://developer.ebay.com/api-docs/commerce/media/overview.html
- **Create Image from File:** https://developer.ebay.com/api-docs/commerce/media/resources/image/methods/createImageFromFile
- **Create Image from URL:** https://developer.ebay.com/api-docs/commerce/media/resources/image/methods/createImageFromUrl
- **Get Image:** https://developer.ebay.com/api-docs/commerce/media/resources/image/methods/getImage

---

## Implementation Checklist

- [ ] Create `integrations/ebay/media.py` module
- [ ] Implement `upload_image_to_ebay()` function
- [ ] Implement `upload_book_images_to_ebay()` function
- [ ] Update `publish.py` to use Media API upload
- [ ] Add error handling and retry logic
- [ ] Add configuration for Media API usage
- [ ] Write unit tests
- [ ] Write integration tests
- [ ] Document in implementation plan

---

## Summary

**Strategy B: eBay Media API Upload** is the production-ready solution that:

✅ **Eliminates public hosting requirement**  
✅ **Uploads images directly to eBay Picture Services**  
✅ **Works with local-first architecture**  
✅ **Provides reliable, permanent image URLs**  
✅ **Production-ready without tunnels or external infrastructure**

**Context7 Status:** Context7's OAuth clients don't contain Media API documentation, but official eBay API documentation provides comprehensive Media API details.

**Recommendation:** Implement Strategy B for production use, with Strategy A (tunnel) as fallback for development/testing.

