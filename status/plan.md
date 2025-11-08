# eBay API Publishing Implementation Plan

## Overview
This plan outlines the conversion from CSV-only export to direct eBay API publishing while maintaining the CSV export as a fallback option. The implementation is organized into 4 milestones (PR1-PR4) for incremental delivery.

## Resources & Documentation

### Context7 References
Context7 provides helpful patterns and examples for eBay OAuth implementation:
- **eBay OAuth Python Client** (`/ebay/ebay-oauth-python-client`): Reference implementation for Python OAuth flow
- **eBay OAuth Node.js Client** (`/ebay/ebay-oauth-nodejs-client`): Patterns for token exchange, refresh, and authorization URL generation

**Use Context7 for**:
- OAuth flow patterns (authorization URL generation, code exchange, token refresh)
- Token management best practices
- Environment handling (PRODUCTION vs SANDBOX)
- Configuration patterns

**Official eBay API Documentation** (required for Inventory/Offer/Publish):
- Inventory API: https://developer.ebay.com/api-docs/sell/inventory/overview.html
- Offer API: https://developer.ebay.com/api-docs/sell/inventory/resources/offer/methods/createOffer
- Account API: https://developer.ebay.com/api-docs/sell/account/overview.html (for policy IDs)
- Developer Console: https://developer.ebay.com/

### Existing Credentials
Credentials are stored in `info/api_info.md`:
- **Client ID**: `your_ebay_client_id` (stored in `info/api_info.md`)
- **Client Secret**: `your_ebay_client_secret` (stored in `info/api_info.md`)
- **Dev ID**: `67ff1ea2-05bf-42df-ab4e-a08d2bfef59a`

**Note**: These credentials should be loaded into environment variables during setup, not hardcoded.

## Current State Analysis

### Architecture
- **Backend**: FastAPI (Python) with SQLModel ORM, SQLite database
- **Frontend**: Next.js with React, TypeScript
- **Current Export**: CSV-based via `ExporterService`, books must be verified before export
- **Policy Management**: Policy names stored in `Setting` table, resolved from book-specific → global defaults

### Data Models (Current)
- `Book`: Core book data with AI-generated content, status workflow (new → auto → needs_review → approved → exported)
- `Image`: Book images with file paths
- `Export`: CSV export records
- `Setting`: Key-value settings (policy defaults)

### Missing for eBay Integration
- Token storage (OAuth access/refresh tokens)
- eBay policy IDs (currently only names stored)
- Publish status tracking (draft/published/error)
- eBay listing/offer IDs
- SKU field (currently using book.id)

---

## Milestone PR1: OAuth Scaffold & Token Management

### Goal
Enable OAuth authentication flow to obtain and refresh eBay user tokens. "Connect eBay" button functional in Settings UI.

### Database Schema Updates

#### New Table: `Token`
```python
class Token(SQLModel, table=True):
    __tablename__ = "tokens"
    
    provider: str = Field(primary_key=True)  # "ebay"
    access_token: str = Field()
    refresh_token: str = Field()
    expires_at: int = Field()  # Unix timestamp (milliseconds)
    token_type: str = Field(default="Bearer")
    created_at: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
    updated_at: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
```

#### Update `Book` Model
Add eBay-related fields:
```python
sku: Optional[str] = Field(default=None)  # Can default to book.id
ebay_offer_id: Optional[str] = Field(default=None)
ebay_listing_id: Optional[str] = Field(default=None)
publish_status: Optional[str] = Field(default=None)  # "draft" | "published" | "error"
publish_error: Optional[str] = Field(default=None)
```

#### Update `Setting` Model
Add eBay settings keys:
- `ebay_payment_policy_id`
- `ebay_return_policy_id`
- `ebay_fulfillment_policy_id`
- `ebay_marketplace_id` (default: "EBAY_US")
- `ebay_category_id` (optional, can be inferred)

### Backend Modules (New)

#### `integrations/ebay/__init__.py`
Empty init file for package.

#### `integrations/ebay/config.py`
**Purpose**: Load and validate eBay configuration from environment variables.

**Functions**:
- `load_ebay_config() -> eBayConfig`: Load env vars, validate required fields
- `get_oauth_base_url() -> str`: Returns production/sandbox OAuth URL
- `get_api_base_url() -> str`: Returns Inventory/Offer API base URL

**Env Vars**:
- `EBAY_ENV` (default: "production", must be "production" or "sandbox")
- `EBAY_CLIENT_ID` (required, from `info/api_info.md`: `your_ebay_client_id`)
- `EBAY_CLIENT_SECRET` (required, from `info/api_info.md`: `your_ebay_client_secret`)
- `EBAY_REDIRECT_URI` (optional for local-first, can use `http://localhost:3001/settings` or any URL user can copy code from)
- `EBAY_SCOPES` (default: "sell.inventory sell.account sell.account.readonly")
- `EBAY_PAYMENT_POLICY_ID` (optional, can set in settings)
- `EBAY_RETURN_POLICY_ID` (optional, can set in settings)
- `EBAY_FULFILLMENT_POLICY_ID` (optional, can set in settings)

**Credentials Setup**: Load credentials from `info/api_info.md` into environment variables:
```bash
export EBAY_CLIENT_ID="your_ebay_client_id"
export EBAY_CLIENT_SECRET="your_ebay_client_secret"
```

**Error Handling**: Raise `ValueError` with descriptive message if required env vars missing.

#### `integrations/ebay/token_store.py`
**Purpose**: Token storage and retrieval from database.

**Functions**:
- `get_token(provider: str = "ebay", session: Session) -> Optional[Token]`: Get current token
- `save_token(provider: str, access_token: str, refresh_token: str, expires_at: int, session: Session) -> Token`: Store/update token
- `is_expired(token: Token) -> bool`: Check if token expired (with 5-minute buffer)
- `refresh_if_needed(provider: str = "ebay", session: Session) -> Optional[Token]`: Auto-refresh if expired, return valid token

**Implementation Notes**:
- Use SQLModel session dependency injection
- Store tokens securely (consider at-rest encryption later)
- Calculate `expires_at` from OAuth response (expires_in seconds + current timestamp)

#### `integrations/ebay/oauth.py`
**Purpose**: OAuth flow implementation.

**Functions**:
- `build_auth_url(redirect_uri: str, client_id: str, scopes: str, state: Optional[str] = None) -> str`: Generate eBay consent URL
- `exchange_code_for_tokens(code: str, redirect_uri: str, client_id: str, client_secret: str) -> Dict[str, Any]`: Exchange authorization code for tokens
- `refresh_tokens(refresh_token: str, client_id: str, client_secret: str) -> Dict[str, Any]`: Refresh expired access token

**Context7 Reference**: `/ebay/ebay-oauth-python-client` and `/ebay/ebay-oauth-nodejs-client` provide patterns for:
- Authorization URL generation with scopes and state parameter
- Token exchange using `exchange_code_for_access_token` pattern
- Token refresh using refresh token grant type
- Environment handling (PRODUCTION vs SANDBOX)

**Implementation Patterns** (based on Context7 examples):
```python
# Authorization URL pattern
# Base URL: https://auth.ebay.com/oauth2/authorize (PRODUCTION)
# Base URL: https://auth.sandbox.ebay.com/oauth2/authorize (SANDBOX)
# Query params: client_id, redirect_uri, response_type=code, scope, state

# Token exchange pattern
# POST https://api.ebay.com/identity/v1/oauth2/token (PRODUCTION)
# POST https://api.sandbox.ebay.com/identity/v1/oauth2/token (SANDBOX)
# Headers: Content-Type: application/x-www-form-urlencoded
# Body: grant_type=authorization_code, code, redirect_uri

# Token refresh pattern
# POST https://api.ebay.com/identity/v1/oauth2/token
# Body: grant_type=refresh_token, refresh_token
```

**Dependencies**: `httpx` for HTTP requests

**Error Handling**: 
- Handle 400/401 responses with clear error messages
- Log request IDs from eBay responses for traceability (never log tokens)
- Raise `HTTPException` with appropriate status codes

### Backend Routes (New)

#### `routes/ebay_oauth.py`
**Purpose**: Simplified OAuth endpoints for local-first app.

**Endpoints**:
- `GET /ebay/oauth/auth-url`: Returns authorization URL (no redirect)
  - Reads config from `integrations/ebay/config.py`
  - Generates authorization URL via `oauth.build_auth_url()`
  - Returns: `{auth_url: string}` (frontend opens in new tab)
- `POST /ebay/oauth/exchange`: Exchanges authorization code for tokens
  - Body: `{code: string}` (manually entered by user)
  - Exchanges code via `oauth.exchange_code_for_tokens()`
  - Stores tokens via `token_store.save_token()`
  - Returns: `{success: true, expires_at: number}` or error
- `GET /ebay/oauth/status`: Returns token status
  - Returns: `{connected: bool, expires_at?: number, is_expired?: bool}`

**Error Handling**: Return JSON error responses with user-friendly messages.

### Frontend Changes

#### Settings Page Updates (`frontend/src/app/settings/page.tsx`)
- Add "eBay Integration" card section
- Add "Connect eBay" button that opens authorization URL in new tab
- Add text input field for manual authorization code entry
- Add "Submit Authorization Code" button to exchange code for tokens
- Show connection status badge (Connected/Not Connected)
- Display token expiry info if connected
- Add input fields for Policy IDs (payment, return, fulfillment) - optional if set via env

**Manual Authorization Flow:**
1. User clicks "Connect eBay" → Opens eBay authorization URL in browser
2. User authorizes app → Gets redirected with `?code=...` in URL
3. User copies authorization code from URL
4. User pastes code into input field in Settings page
5. User clicks "Submit Authorization Code" → Backend exchanges code for tokens
6. Tokens stored, connection status updated

#### API Client Updates (`frontend/src/lib/api.ts`)
- Add `ebayApi` object with:
  - `getAuthUrl()`: Returns authorization URL (frontend opens in new tab)
  - `exchangeCode(code: string)`: Exchanges authorization code for tokens
  - `getConnectionStatus()`: Calls endpoint to check token status

#### Backend Routes (Simplified)
- `GET /ebay/oauth/auth-url`: Returns authorization URL (no redirect)
- `POST /ebay/oauth/exchange`: Exchanges authorization code for tokens
  - Body: `{code: string}`
  - Returns: `{success: true, expires_at: number}` or error
- `GET /ebay/oauth/status`: Returns token status (exists, expires_at, is_expired)

### Testing
- **Unit**: Mock `httpx` responses for `oauth.exchange_code_for_tokens()` and `refresh_tokens()`
  - Use Context7 patterns to validate token exchange flow
- **Integration**: Manual OAuth flow test with real eBay credentials (use credentials from `info/api_info.md`)
  - Test authorization URL generation
  - Test code exchange
  - Test token refresh
- **UI**: Verify "Connect eBay" redirects correctly, status badge updates

**Context7 Testing Patterns**: Reference `/ebay/ebay-oauth-nodejs-client` examples for expected request/response formats

### Success Criteria
- ✅ Clicking "Connect eBay" opens eBay authorization URL in browser
- ✅ User can manually copy authorization code from redirect URL
- ✅ User can paste code into Settings page and exchange for tokens
- ✅ Tokens stored in database `tokens` table
- ✅ Settings page shows "Connected" badge after successful exchange
- ✅ Token refresh logic works for expired tokens

---

## Milestone PR2: eBay API Client & Single-Book Publish Endpoint

### Goal
Implement thin eBay API client and complete publish pipeline (Inventory → Offer → Publish). Single-book publish endpoint functional.

### Backend Modules (New)

#### `integrations/ebay/client.py`
**Purpose**: Thin wrapper around eBay REST APIs with retry logic and error handling.

**Functions**:
- `request(method: str, path: str, json: Optional[Dict] = None, params: Optional[Dict] = None, token: str) -> Dict[str, Any]`: Generic HTTP request wrapper
  - Adds `Authorization: Bearer {token}` header
  - Handles retries (3 attempts with exponential backoff for 5xx errors)
  - Logs request/response IDs from eBay (do not log tokens)
  - Raises `HTTPException` with eBay error messages

**Base URLs**:
- Inventory API: `https://api.ebay.com/sell/inventory/v1`
- Offer API: `https://api.ebay.com/sell/inventory/v1`
- Account API: `https://api.ebay.com/sell/account/v1`

**Dependencies**: `httpx`, `token_store` (for auto-refresh)

#### `integrations/ebay/publish.py`
**Purpose**: Complete publish pipeline orchestrator.

**Functions**:
- `build_inventory_item(book: Book, images: List[Image], base_url: str) -> Dict[str, Any]`: Maps book data to eBay Inventory Item format
  - **SKU**: `book.sku or book.id`
  - **Product**: 
    - `title`: `book.title_ai` (truncate to 80 chars)
    - `description`: `book.description_ai`
    - `aspects`: Map from `book.specifics_ai` (author, format, language, publicationYear, publisher, ISBN)
    - `imageUrls`: Build array from book images (storage URLs)
    - `brand`: Use publisher if available
  - **Condition**: Map `condition_grade` to eBay condition enum
- `create_or_replace_inventory_item(sku: str, product: Dict, session: Session, token: str) -> Dict[str, Any]`: Create/replace inventory item
  - Calls `PUT /sell/inventory/v1/inventory_item/{sku}` via `client.request()`
  - Returns eBay response
- `create_offer(sku: str, price: float, category_id: str, policy_ids: Dict[str, str], marketplace_id: str, session: Session, token: str) -> Dict[str, Any]`: Create offer
  - Maps policies to IDs (from settings/env)
  - Calls `POST /sell/inventory/v1/offer` via `client.request()`
  - Returns offer ID from response
- `publish_offer(offer_id: str, session: Session, token: str) -> Dict[str, Any]`: Publish offer
  - Calls `POST /sell/inventory/v1/offer/{offerId}/publish` via `client.request()`
  - Returns listing ID from response
- `upsert_and_publish(book_id: str, session: Session) -> Dict[str, Any]`: Orchestrates full flow
  - 1. Get token (refresh if needed) via `token_store.refresh_if_needed()`
  - 2. Get book with images
  - 3. Validate required fields (title_ai, description_ai, price_suggested, policies)
  - 4. Build inventory item
  - 5. Create/replace inventory item (handle errors)
  - 6. Create offer (handle errors)
  - 7. Publish offer (handle errors)
  - 8. Update book with `ebay_offer_id`, `ebay_listing_id`, `publish_status="published"`
  - 9. On error, update book with `publish_status="error"` and `publish_error` message

**Error Handling**:
- Wrap each API call in try/except
- Store error messages in `book.publish_error`
- Return detailed error info to caller
- Log eBay request IDs for debugging

**Policy ID Resolution**:
- Priority: Book-specific policy IDs → Settings policy IDs → Env var policy IDs
- If missing, raise validation error before API calls

### Backend Routes (New)

#### `routes/ebay_publish.py`
**Endpoints**:
- `POST /ebay/publish/{book_id}`: Publish a single book to eBay
  - Calls `publish.upsert_and_publish(book_id)`
  - Returns: `{book_id, offer_id, listing_id, publish_status, error?}`
  - Status codes: 200 (success), 400 (validation error), 401 (no token), 500 (API error)
- `GET /ebay/publish/{book_id}/status`: Get publish status for a book
  - Returns: `{publish_status, offer_id?, listing_id?, publish_error?}`

**Dependencies**: `token_store`, `publish`, database session

### Category ID Resolution

**Approach**: Store category ID in settings or use fixed category for books (e.g., "267" for Books > General).

**Implementation**:
- Add `ebay_category_id` to Settings (key: "ebay_category_id", value: "267")
- Or use mapping from `book.category_suggestion` (future enhancement)

### Image URL Handling

**Current**: Images served via `/images/{book_id}/{filename}` static route.

**For eBay**:
- Use full URL: `http://127.0.0.1:8000/images/{book_id}/{filename}` (local dev)
- For production, need publicly accessible URLs (Cloudflare tunnel, ngrok, or hosted storage)
- Store base URL in settings: `image_base_url` (default: `http://127.0.0.1:8000`)

### Preflight Validation

**Function**: `publish.validate_book_for_publish(book: Book, session: Session) -> Dict[str, Any]`

**Checks**:
- Book has `title_ai` (≤ 80 chars)
- Book has `description_ai`
- Book has `price_suggested` (positive number)
- Policy IDs resolvable (payment, return, fulfillment)
- Book has images (at least 1)
- Token exists and not expired (via `token_store.get_token()`)

**Returns**: `{valid: bool, errors: List[str]}`

### Testing
- **Unit**: Mock `client.request()` responses for success/failure scenarios
- **Integration**: End-to-end test with real eBay account (sandbox or production test account)
  - Verify listing appears in Seller Hub
  - Verify inventory item created
  - Verify offer created
  - Verify listing published
- **Edge Cases**: Test with missing fields, expired token, API errors

### Success Criteria
- ✅ POST `/ebay/publish/{book_id}` creates live listing on eBay
- ✅ Listing visible in Seller Hub
- ✅ Book record updated with `ebay_offer_id`, `ebay_listing_id`, `publish_status="published"`
- ✅ Error handling works (missing fields, API errors)
- ✅ Token auto-refresh works during publish

---

## Milestone PR3: Frontend UI Integration & Status Display

### Goal
Add "Publish to eBay" button to Review page, show publish status badges, implement toasts for feedback.

### Frontend Changes

#### Review Page Updates (`frontend/src/components/ReviewPage.tsx`)
- Add "Publish to eBay" button (disabled if no OAuth token)
- Show publish status badge next to book status:
  - `draft`: Gray badge "Draft"
  - `published`: Green badge "Published" with link to Seller Hub
  - `error`: Red badge "Error" with tooltip showing error message
- Show `ebay_listing_id` if published (link to eBay listing)
- Disable button if book already published or missing required fields
- Show loading state during publish

**Button Logic**:
```typescript
const handlePublishToEbay = async () => {
  if (!currentBook || !hasToken) return;
  setPublishing(true);
  try {
    await ebayApi.publishBook(currentBook.id);
    await loadBooks(); // Refresh to show updated status
    toast.success("Book published to eBay!");
  } catch (error) {
    toast.error(`Publish failed: ${error.message}`);
  } finally {
    setPublishing(false);
  }
};
```

#### API Client Updates (`frontend/src/lib/api.ts`)
- Add to `ebayApi`:
  - `publishBook(bookId: string)`: POST `/ebay/publish/{book_id}`
  - `getPublishStatus(bookId: string)`: GET `/ebay/publish/{book_id}/status`
  - `checkTokenStatus()`: GET `/ebay/oauth/status` (already added in PR1)

#### Toast Integration
- Use existing `Toast` component (or add shadcn/ui toast)
- Show success toast on publish
- Show error toast with error message on failure

#### Settings Page Updates
- Show policy ID inputs (if not set via env)
- Show "Disconnect eBay" button (deletes token from database)
- Display last token refresh time

### Backend Route Updates

#### Token Status Endpoint (`routes/ebay_oauth.py`)
- `GET /ebay/oauth/status`: Enhanced to return token expiry time, refresh status

#### Disconnect Endpoint
- `DELETE /ebay/oauth/disconnect`: Deletes token from database
  - Used by Settings page "Disconnect" button

### Seller Hub Link Construction

**Format**: `https://www.ebay.com/sh/lst/active` (general) or specific listing URL if available.

**Implementation**:
- Store listing URL in book record (optional field)
- Or construct from `ebay_listing_id` if eBay provides URL in response

### Preflight Validation (Frontend)
- Check token exists before enabling button
- Check required fields (title_ai, description_ai, price_suggested) before enabling
- Show tooltip explaining why button is disabled

### Testing
- **UI**: Verify button states, status badges, toasts
- **Integration**: Full publish flow from Review page
- **Edge Cases**: Test with missing token, expired token, API errors

### Success Criteria
- ✅ "Publish to eBay" button visible and functional on Review page
- ✅ Status badges show correct publish state
- ✅ Toasts provide feedback on publish success/failure
- ✅ Seller Hub link works (if available)
- ✅ Button disabled appropriately (no token, missing fields, already published)

---

## Milestone PR4: Hardening, Error Handling, Documentation

### Goal
Production-ready error handling, retry logic, validation, and documentation. CSV export remains functional.

### Error Handling Improvements

#### API Error Handling (`integrations/ebay/client.py`)
- Parse eBay error responses (JSON format)
- Extract error messages and request IDs
- Handle specific error codes (401: token expired, 429: rate limit, etc.)
- Implement exponential backoff for 429 errors

#### Validation Improvements (`integrations/ebay/publish.py`)
- Enhanced preflight validation:
  - Title length validation (≤ 80 chars)
  - Price validation (positive, reasonable range)
  - Image count validation (1-12 images)
  - Category ID validation (exists in settings)
  - Policy ID validation (all three required)

#### Error Recovery
- If Inventory call fails but item exists, try update instead of create
- If Offer creation fails, keep inventory item (user can retry)
- If Publish fails, offer remains in draft (can retry publish)

### Logging

#### Structured Logging
- Use Python `logging` module
- Log request/response IDs from eBay (never log tokens)
- Log publish attempts, successes, failures
- Log token refresh events

**Log Format**:
```
[INFO] eBay publish started: book_id={book_id}
[INFO] eBay inventory item created: sku={sku}, request_id={request_id}
[ERROR] eBay offer creation failed: book_id={book_id}, error={error_message}, request_id={request_id}
```

### Retry Logic

#### Client Retry (`integrations/ebay/client.py`)
- Retry on 5xx errors (3 attempts, exponential backoff)
- Retry on 429 rate limit (with Retry-After header)
- Do not retry on 4xx errors (except 401 token refresh)

### Documentation

#### Code Documentation
- Docstrings for all public functions
- Type hints for all function parameters
- README in `integrations/ebay/` explaining module structure

#### User Documentation
- Update main README with eBay integration setup
- Add OAuth setup instructions
- Add environment variable documentation
- Add troubleshooting section

### Feature Flag

#### Environment Variable
- `APP_FEATURE_EBAY_API=true|false` (default: `true`)
- If `false`, hide eBay publish button and routes

#### Implementation
- Check flag in routes and frontend
- Return 503 if feature disabled and endpoint called

### CSV Export Preservation

#### Verify CSV Export Still Works
- Test CSV export with existing books
- Ensure no breaking changes to export flow
- Export button remains in Review page (if applicable)

### Settings Management

#### Policy ID Fetching (Optional Enhancement)
- Add endpoint to fetch policy IDs from eBay Account API
- Store fetched IDs in Settings table
- Manual override still possible via settings UI

**Endpoint**: `GET /ebay/policies`: Fetches payment/return/fulfillment policy IDs from eBay Account API

### Testing

#### Comprehensive Test Coverage
- Unit tests for all publish functions
- Integration tests for full publish flow
- Error scenario tests (expired token, missing fields, API errors)
- CSV export regression tests

#### Test Fixtures
- Mock eBay API responses for common scenarios
- Test books with various field combinations

### Success Criteria
- ✅ Error messages are user-friendly and actionable
- ✅ Retry logic works for transient errors
- ✅ Logging provides traceability
- ✅ CSV export still functional
- ✅ Feature flag works
- ✅ Documentation complete

---

## Implementation Checklist

### Phase 1: PR1 - OAuth Scaffold
- [ ] Create `Token` model and migration
- [ ] Update `Book` model with eBay fields
- [ ] Create `integrations/ebay/config.py`
- [ ] Create `integrations/ebay/token_store.py`
- [ ] Create `integrations/ebay/oauth.py`
- [ ] Create `routes/ebay_oauth.py`
- [ ] Add `/ebay/oauth/status` endpoint
- [ ] Update Settings page UI
- [ ] Update API client
- [ ] Test OAuth flow

### Phase 2: PR2 - API Client & Publish
- [ ] Create `integrations/ebay/client.py`
- [ ] Create `integrations/ebay/publish.py`
- [ ] Create `routes/ebay_publish.py`
- [ ] Implement inventory item mapping
- [ ] Implement offer creation
- [ ] Implement publish flow
- [ ] Add preflight validation
- [ ] Test full publish pipeline

### Phase 3: PR3 - Frontend Integration
- [ ] Add "Publish to eBay" button to Review page
- [ ] Add status badges
- [ ] Add toast notifications
- [ ] Update API client with publish endpoints
- [ ] Add disconnect endpoint
- [ ] Test UI flow

### Phase 4: PR4 - Hardening
- [ ] Improve error handling
- [ ] Add retry logic
- [ ] Add structured logging
- [ ] Write documentation
- [ ] Add feature flag
- [ ] Test CSV export still works
- [ ] Final integration testing

---

## Technical Decisions

### Token Storage
- **Decision**: Store tokens in SQLite `tokens` table
- **Rationale**: Simple, local, no external dependencies
- **Future**: Consider at-rest encryption for production

### Policy ID Management
- **Decision**: Support env vars, settings table, and manual input
- **Rationale**: Flexible for different deployment scenarios

### Image URLs
- **Decision**: Use localhost URLs for dev, require tunnel for production
- **Rationale**: Simpler than hosting images separately for MVP
- **Future**: Consider cloud storage (S3, Cloudflare R2) for production

### Category ID
- **Decision**: Fixed category ID in settings (default: "267" for Books)
- **Rationale**: Simplify MVP, can add category mapping later

### Error Handling Strategy
- **Decision**: Store error messages in `book.publish_error`, return to frontend
- **Rationale**: User can see what went wrong, can retry after fixing

### Feature Flag
- **Decision**: Environment variable `APP_FEATURE_EBAY_API`
- **Rationale**: Easy to disable without code changes

---

## Dependencies

### New Python Packages
- `httpx` (already in requirements.txt)
- No additional packages needed

### Environment Variables Required
```
EBAY_ENV=production
EBAY_CLIENT_ID=your_ebay_client_id
EBAY_CLIENT_SECRET=your_ebay_client_secret
EBAY_REDIRECT_URI=https://<your-tunnel>/ebay/oauth/callback
EBAY_SCOPES="sell.inventory sell.account sell.account.readonly"
EBAY_PAYMENT_POLICY_ID=<optional>
EBAY_RETURN_POLICY_ID=<optional>
EBAY_FULFILLMENT_POLICY_ID=<optional>
APP_FEATURE_EBAY_API=true
```

**Note**: Credentials are stored in `info/api_info.md`. Load these into `.env` file (never commit `.env` to version control).

### eBay Developer Setup
1. ✅ App already created in eBay Developer Console
2. ✅ Client ID and Secret available in `info/api_info.md`
3. ✅ Simplified to local-first manual authorization flow (no callback endpoint needed)
4. ⚠️ **ACTION REQUIRED**: Configure redirect URI in eBay Developer Console
   - Go to: https://developer.ebay.com/my/keys
   - Edit app: **NicolasQ-Booklist-PRD**
   - Add Redirect URI: `http://localhost:3001/settings` (or any URL - user copies code from it)
   - Save changes
5. ⚠️ **ACTION REQUIRED**: Request MAD Exemption (Marketplace Account Deletion)
   - Go to: https://developer.ebay.com/marketplace-account-deletion
   - Click "Notifications" link next to your App ID
   - Toggle "Not persisting eBay data" to "On"
   - Submit exemption request with justification: "Local-first application, no data persistence"
   - **Result:** No webhook endpoints needed (`/ebay/mad` not required)
   - See `info/ebay_mad_exemption.md` for details
6. ⏳ Get Business Policy IDs from Seller Hub or Account API (can fetch programmatically after OAuth)

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Token expiry during publish | Auto-refresh logic in `token_store.refresh_if_needed()` |
| Missing policy IDs | Preflight validation before API calls |
| Image URLs not accessible | Use tunnel (ngrok/Cloudflare) or cloud storage |
| API rate limiting | Retry logic with exponential backoff |
| Field validation failures | Preflight checks server-side |
| CSV export broken | Keep export code unchanged, test regression |

---

## Success Criteria Summary

### End-to-End Flow
1. User clicks "Connect eBay" in Settings
2. User authorizes app in eBay consent page
3. Tokens stored in database
4. User reviews book in Review page
5. User clicks "Publish to eBay"
6. Book published to eBay (Inventory → Offer → Publish)
7. Listing appears in Seller Hub
8. Review page shows "Published" badge with link

### Fallback
- If API fails, user can still export CSV and upload manually

---

## Timeline Estimate

- **PR1**: 2-3 days (OAuth flow, token management)
- **PR2**: 3-4 days (API client, publish pipeline)
- **PR3**: 2-3 days (Frontend integration)
- **PR4**: 2-3 days (Hardening, docs)

**Total**: ~9-13 days of development time

---

## Next Steps

1. ✅ Review and approve this plan
2. ✅ eBay Developer account already set up (credentials in `info/api_info.md`)
3. ⚠️ Configure redirect URI in eBay Developer Console
4. Start implementation with PR1 (OAuth scaffold)
   - Use Context7 patterns (`/ebay/ebay-oauth-python-client`) as reference for OAuth flow
5. Test incrementally after each milestone
6. Document any deviations from plan

**Context7 Usage During Implementation**:
- Reference `/ebay/ebay-oauth-python-client` and `/ebay/ebay-oauth-nodejs-client` for OAuth patterns
- Use Context7 examples to validate request/response formats
- Reference patterns for token refresh and authorization URL generation

---

## Notes

- Keep CSV export code unchanged to ensure backward compatibility
- All eBay API calls should use production environment (not sandbox) as per requirements
- Consider adding batch publish feature in future (publish multiple books at once)
- Monitor eBay API rate limits and adjust retry logic as needed

