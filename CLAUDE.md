# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BookLister AI is a local-first eBay listing assistant that automates book listing creation. It uses GPT-4o Vision to extract book metadata directly from images and publishes listings to eBay via the Sell Inventory API and Media API.

**Architecture**: Monorepo with separate frontend and backend applications.

- **Frontend**: Next.js 15 + React 19 + TypeScript + Tailwind CSS (port 3001)
- **Backend**: FastAPI + SQLite + Python 3.10+ (port 8000)
- **AI**: GPT-4o Vision API (OpenAI) or OpenRouter for metadata extraction
- **Storage**: SQLite database (`data/books.db`) + local image files (`data/images/`)

## Important API Endpoints

### Book Management
- `GET /queue?status={status}` - Get books filtered by status (auto, needs_review, approved, etc.)
- `GET /book/{book_id}` - Get single book details
- `PUT /book/{book_id}` - Update book fields (including `verified: true` for verification)

### AI Vision Extraction
- `POST /ai/vision/{book_id}` - Trigger GPT-4o Vision extraction for a book

### eBay OAuth
- `GET /ebay/oauth/auth-url` - Get eBay OAuth authorization URL
- `POST /ebay/oauth/exchange` - Exchange authorization code for token
- `POST /ebay/oauth/set-token` - Set manual User Token from eBay Developer Console
- `GET /ebay/oauth/status` - Check OAuth connection status
- `DELETE /ebay/oauth/disconnect` - Disconnect eBay account

### eBay Publishing
- `POST /ebay/publish/{book_id}` - Publish book to eBay (or save as draft with `as_draft: true`)
- `GET /ebay/publish/{book_id}/status` - Get publish status for a book

## Common Commands

### Backend

```bash
# Setup
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run server
python main.py

# Run tests
pytest tests/ -v

# Run specific test suites
pytest tests/test_vision_extraction.py -v
pytest tests/test_oauth_integration.py -v
pytest tests/test_publish_e2e.py -v
pytest tests/test_mapping_media_integration.py -v
```

### Frontend

```bash
# Setup
cd frontend
npm install

# Development server
npm run dev

# Build
npm run build

# Production server
npm start

# Lint
npm run lint
```

### Full Stack

```bash
# Windows
start.bat

# Unix/Mac
./start.sh
```

## Code Architecture

### Backend Structure

**Core Modules**:
- `main.py` - FastAPI app entry point with lifespan management
- `models.py` - SQLModel database models (Book, Image, Export, Setting)
- `schemas.py` - Pydantic API request/response schemas
- `db/` - Database initialization and migrations
  - `__init__.py` - Session management and table creation
  - `migrate.py` - Schema migrations (adds AI columns to existing databases)

**Routes** (`routes/`):
- `upload.py` - Image upload and book creation
- `ai_vision.py` - GPT-4o Vision extraction endpoint
- `ai_settings.py` - AI provider configuration
- `ebay_oauth.py` - OAuth flow (auth URL, token exchange, refresh, disconnect)
- `ebay_publish.py` - Publishing workflow endpoint

**Services** (`services/`):
- `vision_extraction.py` - GPT-4o Vision API integration (supports OpenAI & OpenRouter)
- `ai_settings.py` - AI provider and API key management
- `filesystem.py` - File operations and cleanup
- `images/normalize.py` - Image preprocessing (EXIF rotation, GPS stripping, resize)

**eBay Integration** (`integrations/ebay/`):
- `config.py` - eBay API configuration (sandbox vs production)
- `oauth.py` - OAuth flow implementation
- `token_store.py` - Encrypted token storage in SQLite
- `client.py` - eBay API HTTP client
- `mapping.py` - Book model → eBay Inventory/Offer payload conversion
- `media_api.py` - Image upload to eBay Picture Services (EPS)
- `images.py` - Image URL resolution strategy (self-hosted vs Media API)
- `publish.py` - Full publish pipeline (Inventory → Offer → Publish)

**AI Prompting** (`ai/`):
- `prompt_booklister.py` - System and user prompts for GPT-4o Vision extraction

### Frontend Structure

**App Router** (`src/app/`):
- `layout.tsx` - Root layout with theme provider and navigation
- `page.tsx` - Home/dashboard page
- `upload/page.tsx` - Image upload interface with drag-and-drop
- `review/page.tsx` - Book metadata review and editing
- `settings/page.tsx` - eBay OAuth connection and AI provider configuration

**Components** (`src/components/`):
- `ReviewPage.tsx` - Main review interface with all 28+ book fields
- `ImageCarousel.tsx` - Image viewer for book images
- `Navigation.tsx` - Top navigation bar
- `Toast.tsx` - Toast notification system
- `theme-provider.tsx` & `theme-toggle.tsx` - Dark mode support
- `ui/` - Radix UI components (Button, Card, Input, Select, etc.)

**Libraries** (`src/lib/`):
- `api.ts` - Backend API client functions
- `ebay.ts` - eBay-specific API calls (OAuth, publish)
- `utils.ts` - Utility functions (cn for classNames)

**Types** (`src/types/`):
- `ai.ts` - TypeScript types for AI-related data structures

### Database Models

**Book Model** (`models.py:25-69`):
- Core metadata: title, author, publisher, year, isbn13, etc.
- AI-generated fields: `title_ai`, `description_ai`, `specifics_ai` (JSON dict with extended metadata)
- eBay fields: `sku`, `ebay_offer_id`, `ebay_listing_id`, `publish_status`
- Status: `new` → `auto` → `needs_review` → `approved` → `exported`
- Verification: `verified` boolean flag
- Images: one-to-many relationship with Image model

**Image Model** (`models.py:72-83`):
- Stores path, dimensions, and optional hash
- Linked to Book via `book_id` foreign key

**Setting Model** (`models.py:95-100`):
- Key-value store for configuration (JSON values)
- Used for AI provider settings and eBay OAuth tokens

### Key Workflows

#### 1. Vision Extraction Flow

1. User uploads images → `routes/upload.py:upload_images()`
2. Creates Book record with status `new`
3. Frontend calls `POST /ai/vision/{book_id}` → `routes/ai_vision.py:extract_vision()`
4. `services/vision_extraction.py:VisionExtractionService.extract_from_images()`:
   - Loads image files from disk
   - Base64 encodes images
   - Calls GPT-4o Vision API with structured prompt
   - Parses JSON response into Book fields
5. Updates Book with extracted metadata and sets status to `auto` or `needs_review`

**Important**: The vision extraction service supports multiple AI providers (OpenAI, OpenRouter, mock). Provider is configured via `services/ai_settings.py` and stored in database.

#### 2. eBay Publishing Flow

1. User clicks "Publish to eBay" → `POST /ebay/publish/{book_id}`
2. `integrations/ebay/publish.py:prepare_for_publish()`:
   - Validates book has required fields (title, description, price, verified)
   - Resolves image URLs via `integrations/ebay/images.py:resolve_listing_urls()`
   - If using Media API strategy: uploads images to eBay Picture Services
   - Builds eBay Inventory Item payload via `mapping.py:build_inventory_item()`
3. `integrations/ebay/publish.py:publish_to_ebay()`:
   - Creates/updates Inventory Item via eBay Sell Inventory API
   - Creates Offer via eBay Sell Inventory API (links item to pricing/policies)
   - Publishes Offer to make listing live
4. Updates Book with `ebay_offer_id`, `ebay_listing_id`, and `publish_status: "published"`

**Important**: OAuth tokens are stored encrypted in SQLite (`integrations/ebay/token_store.py`). Tokens auto-refresh when expired.

#### 3. Database Migration System

On startup, `db/migrate.py:ensure_schema()` runs to add missing AI columns to existing databases:
- Checks for `title_ai`, `description_ai`, `specifics_ai`, `ai_validation_errors`
- Adds missing columns using `ALTER TABLE` (idempotent, safe for repeated runs)
- Uses transactions with rollback on errors

**Important**: All routes that modify Books must call `session.rollback()` in exception handlers to prevent partial commits.

### Environment Configuration

**Backend** (`backend/.env`):
```env
# OpenAI (required if USE_VISION_EXTRACTION=true)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
USE_VISION_EXTRACTION=true

# eBay OAuth (required for publishing)
EBAY_ENV=sandbox  # or "production"
EBAY_CLIENT_ID=...
EBAY_CLIENT_SECRET=...
EBAY_REDIRECT_URI=http://localhost:3001/settings

# eBay Policies (required for publishing)
EBAY_PAYMENT_POLICY_ID=...
EBAY_RETURN_POLICY_ID=...
EBAY_FULFILLMENT_POLICY_ID=...

# Image Strategy
IMAGE_STRATEGY=media  # "media" (eBay Picture Services) or "self_host"
```

See `README.md` lines 244-263 for full environment variable reference.

### Testing Guidelines

**Backend Tests** (`backend/tests/`):
- All tests use pytest with pytest-asyncio
- Tests mock external APIs (OpenAI, eBay) to avoid real API calls
- Fixtures in `tests/create_fixtures.py` for sample books and images
- Key test files:
  - `test_vision_extraction.py` - Vision API integration tests
  - `test_oauth_integration.py` - OAuth flow tests
  - `test_publish_e2e.py` - End-to-end publish workflow
  - `test_mapping_media_integration.py` - Mapping + Media API regression tests

**Running Tests**:
```bash
cd backend
pytest tests/ -v  # All tests
pytest tests/test_vision_extraction.py -v  # Specific suite
```

### Image Processing

**Normalization** (`services/images/normalize.py`):
- EXIF orientation correction (auto-rotates images)
- GPS metadata stripping (privacy)
- Resizing to max dimensions while preserving aspect ratio
- Runs automatically on upload

**Media API Integration** (`integrations/ebay/media_api.py`):
- Uploads images to eBay Picture Services (EPS) using Commerce Media API v1 (GA)
- Sends images as binary data with `Content-Type: image/jpeg` (not multipart/form-data)
- Required headers: `Authorization`, `Content-Type`, `X-EBAY-C-MARKETPLACE-ID`, `Accept`
- Returns HTTPS URLs for use in listings
- Validates image dimensions (min 500px on long edge)
- Limits: max 24 images per listing
- Requires `EBAY_MARKETPLACE_ID` in environment (defaults to `EBAY_US`)

### Important Implementation Notes

1. **JSON Field Storage**: `specifics_ai` and `ai_validation_errors` must be stored as Python `dict`/`list`/`None`, never as string literals like `'null'` or `'[]'`. SQLModel JSON columns handle serialization automatically.

2. **eBay Title Limit**: eBay titles are max 80 characters. `mapping.py:build_inventory_item()` automatically truncates and returns metadata about truncation.

3. **OAuth Token Refresh**: Tokens expire after ~2 hours. The `integrations/ebay/client.py:EBayClient` automatically refreshes expired tokens using the refresh token.

4. **Condition Mapping**: Book condition grades map to eBay condition IDs via `CONDITION_MAPPING` in `mapping.py:15-21`.

5. **Database Rollback**: All routes that catch exceptions during database modifications must call `session.rollback()` before cleanup or raising errors.

6. **Provider Flexibility**: The vision extraction service supports multiple AI providers. Always check `ai_settings.get_active_provider()` rather than hardcoding to OpenAI.

### Known Issues and Documentation

- Check `status/STATUS.md` for detailed implementation status and recent fixes
- See `info/` directory for eBay API documentation and field reference
- Review `PROJECT_SUMMARY.md` for high-level architecture overview

### Startup Behavior

On first run, the application:
1. Creates SQLite database at `data/books.db`
2. Runs schema migrations to ensure AI columns exist
3. Initializes default settings in the Setting table
4. Creates `data/images/` directory if missing

No manual database migrations are required.
