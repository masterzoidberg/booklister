# BookLister AI

Create a fully local-first eBay listing assistant that uses GPT-4o Vision to extract book metadata directly from images and publish listings to eBay via the Sell & Media APIs.

## Summary

BookLister AI is a local-first application that automates the process of listing books on eBay. It uses GPT-4o Vision to extract structured metadata from book images (cover, spine, title page, etc.) and automatically publishes listings to eBay using the Sell Inventory API and Media API for image hosting.

## Core Flow

1. **Upload Images**: User uploads book images (cover, spine, pages, etc.)
2. **Vision Extraction**: GPT-4o Vision API analyzes images and extracts structured metadata (title, author, ISBN, condition, etc.)
3. **Review & Edit**: User reviews and edits extracted data in the Review interface
4. **Publish to eBay**: One-click publishing to eBay using OAuth-authenticated API calls
5. **Image Hosting**: Images are automatically uploaded to eBay Picture Services (EPS) via Media API

## Technical Stack

- **Frontend**: Next.js 15 + React 19 + TypeScript + Tailwind CSS
- **Backend**: FastAPI (Python 3.10+) + SQLite
- **AI**: GPT-4o Vision API (OpenAI) for multimodal extraction
- **APIs**: eBay Sell Inventory API, Media API, OAuth2
- **Image Processing**: PIL/Pillow for normalization
- **Storage**: Local file system (SQLite database, image files)

## Prerequisites

- Python 3.10+
- Node.js 18+
- OpenAI API key (for vision extraction)
- eBay Developer Account credentials

## Setup

### 1. Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Configuration

Create `backend/.env` file:

```env
# OpenAI Configuration (Required for vision extraction)
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o
USE_VISION_EXTRACTION=true

# eBay Configuration
EBAY_ENV=sandbox  # or "production"
EBAY_CLIENT_ID=your_ebay_client_id
EBAY_CLIENT_SECRET=your_ebay_client_secret
EBAY_REDIRECT_URI=http://localhost:3001/settings
EBAY_SCOPES=sell.inventory sell.account sell.account.readonly

# eBay Policy IDs (required for publishing)
EBAY_PAYMENT_POLICY_ID=your_payment_policy_id
EBAY_RETURN_POLICY_ID=your_return_policy_id
EBAY_FULFILLMENT_POLICY_ID=your_fulfillment_policy_id

# Image Strategy
IMAGE_STRATEGY=media  # or "self_host"
```

### 3. Frontend Setup

```bash
cd frontend
npm install
```

### 4. Database Initialization

The database initializes automatically on first run. No manual migration needed.

## Running the Application

### Start Backend

```bash
cd backend
python main.py
```

Backend runs on `http://127.0.0.1:8000`

### Start Frontend

```bash
cd frontend
npm run dev
```

Frontend runs on `http://localhost:3001`

## Complete Workflow

### Step 1: Connect eBay Account

1. Navigate to **Settings** page (`http://localhost:3001/settings`)
2. Scroll to **eBay Account Connection** section
3. Click **"Connect to eBay"** button
4. Authorize the application in the popup window
5. Copy the authorization code from the redirect URL
6. Paste the code in the **Authorization Code** field
7. Click **"Connect"**
8. Verify connection status shows **"Connected"**

### Step 2: Upload Book Images

1. Navigate to **Upload** page (`http://localhost:3001/upload`)
2. Select book images (cover, spine, pages, etc.)
3. Click **Upload**
4. Images are automatically scanned and processed

### Step 3: Vision Extraction

After upload, books are automatically processed:

- **If `USE_VISION_EXTRACTION=true`**: GPT-4o Vision API extracts metadata directly from images
- **If `USE_VISION_EXTRACTION=false`**: Traditional OCR + metadata enrichment workflow

Books appear in **Review** page with status:
- `new`: Just uploaded
- `auto`: Auto-processed and ready for review
- `needs_review`: Requires manual review

### Step 4: Review & Edit

1. Navigate to **Review** page (`http://localhost:3001/review`)
2. Review extracted metadata:
   - Title (AI-generated, max 80 chars)
   - Author, ISBN, Publisher, Year
   - Condition grade
   - Description (AI-generated)
   - Price suggestion
3. Edit fields as needed
4. Set suggested price if not auto-populated
5. Click **"Verify"** to mark book as verified

### Step 5: Publish to eBay

1. Ensure book is **Verified** (green badge)
2. Ensure book has **Price Suggested** set
3. Ensure **eBay Account** is connected
4. Click **"Publish to eBay"** button
5. Wait for publishing to complete (loading spinner)
6. Success toast appears with **"View Listing"** button
7. Click to open the eBay listing in a new tab

## Testing

### Run Integration Tests

```bash
cd backend
pytest tests/ -v
```

### Test Coverage

- ✅ Vision extraction endpoint (`/ai/vision/{book_id}`)
- ✅ OAuth token exchange and refresh
- ✅ Full publish flow (mocked eBay API)
- ✅ Mapping + Media API integration
- ✅ Regression tests for all components

### Run Specific Test Suites

```bash
# Vision extraction tests
pytest tests/test_vision_extraction.py -v

# OAuth integration tests
pytest tests/test_oauth_integration.py -v

# End-to-end publish tests
pytest tests/test_publish_e2e.py -v

# Mapping + Media API regression tests
pytest tests/test_mapping_media_integration.py -v
```

## API Endpoints

### Vision Extraction

```bash
POST /ai/vision/{book_id}
```

Extracts structured metadata from book images using GPT-4o Vision API.

### OAuth

```bash
GET  /ebay/oauth/auth-url          # Get authorization URL
POST /ebay/oauth/exchange          # Exchange code for tokens
GET  /ebay/oauth/status            # Get connection status
POST /ebay/oauth/refresh           # Refresh access token
DELETE /ebay/oauth/disconnect      # Disconnect account
```

### Publishing

```bash
POST /ebay/publish/{book_id}              # Publish book to eBay
GET  /ebay/publish/{book_id}/status       # Get publish status
```

## Troubleshooting

### OAuth Connection Issues

- **"No token found"**: Ensure you've completed the OAuth flow in Settings
- **"Token expired"**: Click "Refresh Token" in Settings
- **"Invalid authorization code"**: Ensure you copied the entire code from the redirect URL

### Publishing Issues

- **"No valid OAuth token"**: Connect eBay account in Settings
- **"Book must have price_suggested"**: Set a price in the Review page
- **"Book not verified"**: Click "Verify" button in Review page
- **"Policy IDs required"**: Add policy IDs to `.env` file

### Vision Extraction Issues

- **"OpenAI API key not configured"**: Add `OPENAI_API_KEY` to `.env`
- **"No images found"**: Ensure images are uploaded and visible in Upload page
- **"Failed to read images"**: Check file permissions on `data/images/` directory

### Image Upload Issues

- **Media API errors**: Check network connection and eBay API credentials
- **"Image validation failed"**: Ensure images are valid JPEG/PNG files
- **"Image too small"**: Media API requires minimum 500px on long edge

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes* | - | OpenAI API key for vision extraction |
| `OPENAI_MODEL` | No | `gpt-4o` | OpenAI model to use |
| `USE_VISION_EXTRACTION` | No | `false` | Enable GPT-4o vision extraction |
| `EBAY_ENV` | Yes | `sandbox` | eBay environment (sandbox/production) |
| `EBAY_CLIENT_ID` | Yes | - | eBay OAuth client ID |
| `EBAY_CLIENT_SECRET` | Yes | - | eBay OAuth client secret |
| `EBAY_REDIRECT_URI` | No | `http://localhost:3001/settings` | OAuth redirect URI |
| `EBAY_SCOPES` | No | `sell.inventory sell.account...` | OAuth scopes |
| `EBAY_PAYMENT_POLICY_ID` | Yes** | - | Payment policy ID |
| `EBAY_RETURN_POLICY_ID` | Yes** | - | Return policy ID |
| `EBAY_FULFILLMENT_POLICY_ID` | Yes** | - | Fulfillment policy ID |
| `IMAGE_STRATEGY` | No | `self_host` | Image upload strategy (media/self_host) |
| `MEDIA_MAX_IMAGES` | No | `24` | Maximum images per listing |
| `MEDIA_MIN_LONG_EDGE` | No | `500` | Minimum image dimension (px) |

\* Required if `USE_VISION_EXTRACTION=true`  
\** Required for publishing to eBay

## Support

For issues or questions:
1. Check `status/STATUS.md` for known issues
2. Review test files in `backend/tests/` for examples
3. Check backend logs in console output
# booklister
