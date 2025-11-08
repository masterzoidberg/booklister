# eBay API Image Handling Guide

## Overview

eBay's Inventory API requires publicly accessible HTTPS image URLs. Images are **not uploaded directly** to eBay via the Inventory API; instead, you provide URLs to images that are already hosted elsewhere.

---

## How eBay Inventory API Handles Images

### 1. Image URLs (Current Method)

**API Structure:** `product.imageUrls[]` (array of strings)

**How It Works:**
- eBay Inventory API expects an array of **publicly accessible HTTPS URLs**
- These URLs point to images hosted on your server or a CDN
- eBay retrieves and displays these images when listing is published
- **No direct upload to eBay** via Inventory API

**Requirements:**
- ✅ URLs must be **HTTPS** (HTTP not allowed)
- ✅ Images must be **publicly accessible** (no authentication required)
- ✅ URLs must be **permanent/stable** (don't change after listing)
- ✅ Minimum **1 image**, maximum **12 images** per listing
- ✅ Each image must be **at least 500 pixels** on longest side
- ✅ Supported formats: **JPG, GIF, PNG, BMP, TIFF, AVIF, HEIC, WEBP**

---

## 2. Alternative: eBay Media API (Optional Upload Service)

eBay also provides a **Media API** for uploading images to eBay Picture Services (EPS), but this is **optional**:

### Option A: Upload to eBay Picture Services (EPS)

**Media API Endpoints:**
- `POST /commerce/media/v1_beta/image` - Upload from file
- `POST /commerce/media/v1_beta/image?source=URL` - Upload from URL

**Process:**
1. Upload image to EPS via Media API
2. eBay returns hosted image URL
3. Use that URL in `product.imageUrls[]`

**Benefits:**
- ✅ Images hosted by eBay (reliable, permanent)
- ✅ No need for your own hosting infrastructure
- ✅ Automatic optimization and CDN distribution

**Drawbacks:**
- ⚠️ Additional API call per image
- ⚠️ Requires Media API access/scopes
- ⚠️ More complex implementation

### Option B: Use Your Own Hosting (Simpler)

**Process:**
1. Host images on your server/CDN
2. Provide public HTTPS URLs directly to Inventory API
3. eBay retrieves images from your URLs

**Benefits:**
- ✅ Simpler implementation (no upload step)
- ✅ Full control over image hosting
- ✅ No additional API calls

**Drawbacks:**
- ⚠️ Requires publicly accessible hosting
- ⚠️ URLs must remain stable/permanent

---

## Current BookLister AI Implementation

### Image Storage
- **Location:** `data/images/{book_id}/{filename}`
- **Model:** `Image` table with `path`, `width`, `height`, `hash`
- **Serving:** FastAPI static files at `/images/{book_id}/{filename}`
- **Current URL Format:** `http://127.0.0.1:8000/images/{book_id}/{filename}`

### Current Issues for eBay API

**Problem:**
- ❌ URLs are **HTTP** (eBay requires **HTTPS**)
- ❌ URLs are **localhost** (not publicly accessible)
- ❌ Images not accessible to eBay's servers

**Solution Options:**

---

## Solutions for BookLister AI

### Strategy B: eBay Media API Upload (Production-Ready, IMPLEMENTED)

**Status:** ✅ **IMPLEMENTED** - Production-ready image upload pipeline

**For Production:**
- Upload images directly to eBay Picture Services (EPS) via Media API
- eBay returns permanent HTTPS EPS URLs (e.g., `https://i.ebayimg.com/images/...`)
- No tunnel or external hosting required
- Works in production without infrastructure setup

**Implementation:**
- **Strategy Selector:** `IMAGE_STRATEGY=media` (default: `self_host`)
- **Image Normalization:** Resize to 1600px long edge, JPEG quality 0.88, EXIF rotation, GPS stripping
- **Media API Client:** `backend/integrations/ebay/media_api.py`
- **Image Resolver:** `backend/integrations/ebay/images.py`
- **Publish Integration:** `backend/integrations/ebay/publish.py`

**Configuration:**
```bash
# Enable Media API strategy (Strategy B)
IMAGE_STRATEGY=media

# Media API limits
MEDIA_MAX_IMAGES=24          # Maximum images per listing
MEDIA_MIN_LONG_EDGE=500      # Minimum long edge (recommend 1600)
```

**Process:**
1. Normalize images (resize, rotate EXIF, strip GPS, convert to JPEG)
2. Upload to eBay Media API: `POST /commerce/media/v1_beta/image`
3. Get EPS URLs from response
4. Use EPS URLs in `product.imageUrls[]` for Inventory API

**Features:**
- ✅ Retry logic with exponential backoff (429, 5xx errors)
- ✅ Request-ID logging for traceability (never logs tokens)
- ✅ Image validation (size, format, minimum dimensions)
- ✅ Automatic normalization (resize, EXIF rotation, GPS stripping)
- ✅ Error handling with clear messages

**Limits:**
- Up to 24 images per listing (eBay supports up to 24, but we limit to 12 for Inventory API)
- Minimum 500px long edge (recommend 1600px)
- Maximum 10MB per image

### Option 1: Use Tunnel for Local Development (Quick Fix) - DEPRECATED

**For Development:**
- Use ngrok/Cloudflare tunnel
- Tunnel exposes local server with HTTPS
- Use tunnel URL for image URLs

**Note:** Use Strategy B (Media API) instead - no tunnel required

**Implementation:**
```python
# In publish.py
def _build_image_urls(book: Book, base_url: str) -> List[str]:
    """Build list of image URLs from book images."""
    if not book.images:
        return []
    
    urls = []
    for img in book.images:
        filename = img.path.split('/')[-1]
        # Use tunnel URL or configured base URL
        url = f"{base_url}/images/{book.id}/{filename}"
        urls.append(url)
    
    return urls

# Usage
base_url = os.getenv("IMAGE_BASE_URL", "https://your-tunnel.ngrok.io")
image_urls = _build_image_urls(book, base_url)
```

**Pros:**
- ✅ Quick solution for development
- ✅ Works with existing local storage
- ✅ No code changes to storage logic

**Cons:**
- ❌ Tunnel must stay running
- ❌ URLs change if tunnel restarts
- ❌ Not ideal for production

---

### Option 2: Upload to eBay Media API (Recommended for Production)

**See:** `info/ebay_media_api_strategy_b.md` for detailed implementation guide

**Implementation:**
1. Before creating inventory item, upload images to EPS
2. Store returned eBay image URLs
3. Use those URLs in inventory item

**Code Structure:**
```python
# In integrations/ebay/media.py
async def upload_image_to_ebay(
    image_path: str,
    token: str,
    client: EbayClient
) -> str:
    """Upload image to eBay Picture Services and return URL."""
    with open(image_path, 'rb') as f:
        response = await client.request(
            method='POST',
            path='/commerce/media/v1_beta/image',
            files={'image': f},
            token=token
        )
        # Extract image URL from response
        return response['image']['url']

# In publish.py
async def upload_book_images(
    book: Book,
    token: str,
    client: EbayClient
) -> List[str]:
    """Upload all book images to eBay and return URLs."""
    image_urls = []
    for img in book.images:
        local_path = f"data/images/{book.id}/{img.path.split('/')[-1]}"
        ebay_url = await upload_image_to_ebay(local_path, token, client)
        image_urls.append(ebay_url)
    return image_urls
```

**Pros:**
- ✅ Images hosted by eBay (reliable, permanent)
- ✅ No tunnel required
- ✅ Works in production
- ✅ Automatic optimization

**Cons:**
- ⚠️ Additional API calls per image
- ⚠️ Requires Media API scopes
- ⚠️ Slightly more complex

---

### Option 3: Cloud Storage + CDN (Production Solution)

**For Production:**
- Upload images to cloud storage (S3, Cloudflare R2, etc.)
- Use CDN for public HTTPS URLs
- Provide those URLs to Inventory API

**Implementation:**
```python
# In integrations/ebay/storage.py (future)
async def upload_to_cloud_storage(
    image_path: str,
    book_id: str
) -> str:
    """Upload image to cloud storage and return public URL."""
    # Upload to S3/R2/etc.
    # Return public HTTPS URL
    pass
```

**Pros:**
- ✅ Permanent, stable URLs
- ✅ Production-ready
- ✅ Full control over hosting
- ✅ Can use CDN for performance

**Cons:**
- ⚠️ Requires cloud storage setup
- ⚠️ Additional infrastructure cost
- ⚠️ More complex deployment

---

## Recommended Approach for BookLister AI

### Phase 1: Development (Use Tunnel)
1. Use ngrok/Cloudflare tunnel for local development
2. Configure `IMAGE_BASE_URL` env var with tunnel URL
3. Images served via tunnel with HTTPS
4. Simple implementation, quick to test

### Phase 2: Production (Upload to eBay Media API)
1. Implement Media API image upload
2. Upload images to EPS before creating inventory item
3. Use eBay-hosted image URLs
4. No external hosting required

**Rationale:**
- Development: Quick and simple with tunnel
- Production: Reliable with eBay hosting
- No need for separate cloud storage infrastructure

---

## Image Requirements Summary

### Format Requirements
- ✅ **Formats:** JPG, GIF, PNG, BMP, TIFF, AVIF, HEIC, WEBP
- ✅ **Minimum Size:** 500 pixels on longest side
- ✅ **Protocol:** HTTPS only (no HTTP)
- ✅ **Count:** 1-12 images per listing
- ✅ **Access:** Must be publicly accessible

### Current BookLister AI Compliance
- ✅ **Formats:** Supports JPG, PNG, WEBP, TIFF (via `FilesystemService`)
- ✅ **Size:** No current validation, but images are uploaded by user
- ❌ **Protocol:** Currently HTTP localhost (needs HTTPS tunnel or upload)
- ✅ **Count:** Can have multiple images per book
- ❌ **Access:** Not publicly accessible (needs tunnel or upload)

---

## Implementation Details

### Image URL Structure in Inventory API

```json
{
  "product": {
    "imageUrls": [
      "https://i.ebayimg.com/images/g/ABC123/image1.jpg",
      "https://i.ebayimg.com/images/g/ABC123/image2.jpg",
      "https://your-tunnel.com/images/book-id/image3.jpg"
    ]
  }
}
```

### Image URL Building Function

```python
def build_image_urls(
    book: Book,
    base_url: str = "http://127.0.0.1:8000",
    use_ebay_upload: bool = False
) -> List[str]:
    """
    Build list of image URLs for eBay Inventory API.
    
    Args:
        book: Book model with images relationship
        base_url: Base URL for image serving (tunnel or cloud storage)
        use_ebay_upload: If True, upload to eBay Media API first
    
    Returns:
        List of HTTPS image URLs
    """
    if not book.images:
        return []
    
    urls = []
    for img in book.images:
        filename = img.path.split('/')[-1]
        
        if use_ebay_upload:
            # Upload to eBay Media API and get hosted URL
            ebay_url = await upload_to_ebay_media_api(img)
            urls.append(ebay_url)
        else:
            # Use provided base URL (must be HTTPS and publicly accessible)
            url = f"{base_url}/images/{book.id}/{filename}"
            if not url.startswith('https://'):
                raise ValueError("Image URLs must be HTTPS for eBay API")
            urls.append(url)
    
    return urls
```

---

## Validation Requirements

### Preflight Checks for Images

```python
def validate_images_for_ebay(book: Book) -> Dict[str, Any]:
    """Validate images meet eBay requirements."""
    errors = []
    
    if not book.images:
        errors.append("At least 1 image required")
    
    if len(book.images) > 12:
        errors.append("Maximum 12 images allowed")
    
    for img in book.images:
        if img.width < 500 or img.height < 500:
            errors.append(f"Image {img.path} below minimum size (500px)")
        
        # Check format (from file extension)
        ext = img.path.split('.')[-1].lower()
        if ext not in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp']:
            errors.append(f"Image {img.path} unsupported format")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors
    }
```

---

## Environment Configuration

### Required Environment Variables

```bash
# Option 1: Tunnel URL (Development)
IMAGE_BASE_URL=https://your-tunnel.ngrok.io

# Option 2: Cloud Storage (Production)
IMAGE_BASE_URL=https://your-cdn.example.com
IMAGE_USE_EBAY_UPLOAD=true  # Use Media API instead
```

---

## Summary

**eBay Inventory API Image Handling:**
1. **Requires:** Publicly accessible HTTPS image URLs
2. **Format:** Array of URL strings in `product.imageUrls[]`
3. **Count:** 1-12 images per listing (Media API supports up to 24)
4. **Size:** Minimum 500px on longest side (recommend 1600px)
5. **Protocol:** HTTPS only

**BookLister AI Current State:**
- ✅ Images stored locally
- ✅ Images served via FastAPI static files
- ✅ **Strategy B (Media API) IMPLEMENTED** - Upload to eBay Picture Services
- ✅ Support for multiple images per book
- ✅ Image normalization (resize, EXIF rotation, GPS stripping)
- ✅ Retry logic with exponential backoff

**Current Solution (Strategy B - Media API):**
- ✅ **Production-Ready:** Upload to eBay Picture Services via Media API
- ✅ **No Infrastructure Required:** No tunnel, hosting, or CDN needed
- ✅ **Reliable URLs:** Permanent EPS URLs hosted by eBay
- ✅ **Automatic Optimization:** eBay handles image optimization and CDN distribution

**Configuration:**
```bash
IMAGE_STRATEGY=media          # Use Media API (Strategy B)
MEDIA_MAX_IMAGES=24           # Maximum images (limit to 12 for Inventory API)
MEDIA_MIN_LONG_EDGE=500       # Minimum long edge (recommend 1600)
```

**Fallback Solution (Strategy A - Self-Host):**
- ⚠️ Requires tunnel/hosting for HTTPS URLs
- ⚠️ Not recommended for production (use Strategy B instead)

---

## References

- **eBay Inventory API:** https://developer.ebay.com/api-docs/sell/inventory/overview.html
- **eBay Media API:** https://developer.ebay.com/api-docs/commerce/media/overview.html
- **Image Requirements:** https://developer.ebay.com/api-docs/sell/static/inventory/managing-image-media.html
- **Picture Policy:** https://www.ebay.com/help/policies/listing-policies/picture-policy?id=4379

