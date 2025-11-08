# Deep Research Prompt: BookLister AI - Image to eBay Listing Flow Issues

## Objective

Investigate and identify root causes of issues preventing successful extraction of book information from images and publishing listings to eBay. Provide comprehensive analysis with specific fixes.

## Context

**Project**: BookLister AI - A local-first application that uses GPT-4o Vision to extract book metadata from images and automatically publish listings to eBay.

**Core Flow**:
```
1. User uploads book images (cover, spine, pages) → backend/routes/upload.py
2. Images stored in backend/data/images/{book_id}/
3. Vision extraction: POST /ai/vision/{book_id} → backend/routes/ai_vision.py
4. GPT-4o Vision API extracts metadata → backend/services/vision_extraction.py
5. Extracted data mapped to Book model → backend/models.py
6. User reviews/edits in Review UI → frontend/src/app/review/page.tsx
7. Publish to eBay: POST /ebay/publish/{book_id} → backend/routes/ebay_publish.py
8. Creates Inventory Item → backend/integrations/ebay/publish.py
9. Creates Offer → backend/integrations/ebay/publish.py
10. Publishes Offer → Makes listing live on eBay
```

## Known Issues & Error Reports

### 1. Error 25002 (Currency Issue) - Partially Fixed
- **Location**: `status/ERROR_25002_FIX_REPORT.md`
- **Symptom**: Publishing fails with "No <Item.Currency> exists"
- **Fix Applied**: Added extractors for both `pricing` and `pricingSummary` fields
- **Status**: Fixed but may have related issues
- **Files**: 
  - `backend/integrations/ebay/publish.py` (lines 74-145, 695-785, 788-921, 924-1045)
  - `backend/integrations/ebay/client.py` (lines 410-436, 488-500)

### 2. Vision Extraction Issues
- **Potential Problems**: 
  - Incorrect field extraction from images
  - Missing required fields for eBay
  - Field mapping errors
  - Validation failures
- **Files to Investigate**:
  - `backend/services/vision_extraction.py` - Vision extraction service
  - `backend/ai/prompt_booklister.py` - AI prompt for extraction
  - `backend/routes/ai_vision.py` - Vision extraction endpoint
  - `info/ebay_book_listing_fields.md` - Expected field schema
  - `backend/models.py` - Book model definition

### 3. Mapping Issues (Book → eBay Format)
- **Potential Problems**:
  - Incorrect field mapping
  - Missing required eBay fields
  - Category/aspect validation failures
  - Title truncation issues
- **Files to Investigate**:
  - `backend/integrations/ebay/mapping.py` - Book to eBay mapping
  - `backend/integrations/ebay/mapping_validation.py` - Preflight validation
  - `info/ebay_api_field_mappings.md` - Field mapping documentation
  - `mapping/schema.yaml` - Mapping schema

### 4. Publishing Flow Issues
- **Potential Problems**:
  - Missing required fields before publish
  - Policy ID validation failures
  - Image upload failures
  - Offer creation/publish failures
- **Files to Investigate**:
  - `backend/integrations/ebay/publish.py` - Main publish flow
  - `backend/integrations/ebay/client.py` - eBay API client
  - `backend/integrations/ebay/media_api.py` - Image upload to eBay
  - `backend/integrations/ebay/images.py` - Image URL resolution
  - `backend/routes/ebay_publish.py` - Publish endpoint

## Key Files to Analyze

### Vision Extraction Flow
1. **`backend/routes/upload.py`**
   - Image upload handler
   - Book creation
   - Status management

2. **`backend/routes/ai_vision.py`**
   - Vision extraction endpoint: `POST /ai/vision/{book_id}`
   - Error handling
   - Book model updates

3. **`backend/services/vision_extraction.py`**
   - `VisionExtractionService.extract_from_images_vision()` - Main extraction method
   - AI provider handling (OpenAI, OpenRouter, Gemini)
   - Field mapping to Book model
   - Category aspect fetching

4. **`backend/ai/prompt_booklister.py`**
   - System prompt for vision extraction
   - User prompt builder
   - Expected JSON schema

5. **`backend/models.py`**
   - `Book` model definition
   - Field types and constraints
   - Status enum

6. **`info/ebay_book_listing_fields.md`**
   - Expected field schema
   - Required vs optional fields
   - Field validation rules

### Mapping & Validation
7. **`backend/integrations/ebay/mapping.py`**
   - `build_inventory_item()` - Creates Inventory Item payload
   - `build_offer()` - Creates Offer payload
   - `get_ebay_category_id()` - Category mapping
   - Condition grade mapping
   - Title truncation logic
   - Aspect/item specifics extraction

8. **`backend/integrations/ebay/mapping_validation.py`**
   - Preflight validation
   - Required field checks
   - Category/aspect validation

9. **`info/ebay_api_field_mappings.md`**
   - Field mapping documentation
   - eBay API requirements

### Publishing Flow
10. **`backend/routes/ebay_publish.py`**
    - Publish endpoint: `POST /ebay/publish/{book_id}`
    - Request validation
    - Error responses

11. **`backend/integrations/ebay/publish.py`**
    - `publish_book()` - Main publish orchestrator
    - `prepare_for_publish()` - Pre-publish validation and image upload
    - `publish_to_ebay()` - Inventory Item → Offer → Publish flow
    - `publish_offer()` - Offer publishing with validation
    - `ensure_offer_is_publishable()` - Pre-publish checks
    - `prepublish_assertions()` - Validation assertions
    - Currency/price extractors

12. **`backend/integrations/ebay/client.py`**
    - `EBayClient` - eBay API client
    - `create_inventory_item()` - PUT /inventory_item/{sku}
    - `create_offer()` - POST /offer
    - `publish_offer()` - POST /offer/{id}/publish
    - `ensure_offer_pricing()` - Price/currency handling
    - `delete_offer()` - Offer deletion
    - OAuth token handling

13. **`backend/integrations/ebay/media_api.py`**
    - Image upload to eBay Picture Services
    - `upload_image_to_ebay()` - Single image upload
    - Retry logic
    - Error handling

14. **`backend/integrations/ebay/images.py`**
    - `resolve_listing_urls()` - Image URL resolution
    - Strategy selection (Media API vs self-host)

### Configuration & Settings
15. **`backend/settings.py`**
    - eBay configuration
    - AI provider settings
    - Environment variables

16. **`backend/services/ai_settings.py`**
    - AI provider management
    - API key handling

17. **`backend/services/policy_settings.py`**
    - Policy ID retrieval
    - Policy validation

### Frontend Integration
18. **`frontend/src/app/review/page.tsx`**
    - Review UI
    - Publish button handler
    - Error display

19. **`frontend/src/lib/api.ts`**
    - API client
    - Vision extraction calls
    - Publish calls

## Investigation Areas

### Area 1: Vision Extraction Quality
**Questions to Answer**:
- Are all required fields being extracted correctly?
- Is the AI prompt producing the expected JSON structure?
- Are field mappings from AI output to Book model correct?
- Are validation errors being caught and reported?
- Is category context being used correctly for aspect extraction?

**Files to Deep Dive**:
- `backend/services/vision_extraction.py` - Full implementation
- `backend/ai/prompt_booklister.py` - Prompt quality
- `backend/routes/ai_vision.py` - Error handling
- Check actual AI responses vs expected schema

**Test Cases to Verify**:
- Extract from sample images
- Verify all required eBay fields are present
- Check field format (dates, prices, condition grades)
- Validate against `info/ebay_book_listing_fields.md` schema

### Area 2: Book Model → eBay Mapping
**Questions to Answer**:
- Are all Book fields correctly mapped to eBay format?
- Are required eBay fields always present?
- Is category selection correct?
- Are item specifics/aspects properly formatted?
- Is title truncation working correctly?
- Are condition grades mapped correctly?

**Files to Deep Dive**:
- `backend/integrations/ebay/mapping.py` - Full mapping logic
- `backend/integrations/ebay/mapping_validation.py` - Validation rules
- Compare Book model fields to eBay requirements

**Test Cases to Verify**:
- Map sample Book to Inventory Item payload
- Map sample Book to Offer payload
- Verify all required fields present
- Check field formats match eBay API spec

### Area 3: Publishing Flow Validation
**Questions to Answer**:
- Are all required fields validated before publish?
- Is currency/price validation working correctly?
- Are policy IDs validated?
- Is image upload working correctly?
- Are offers being created with correct structure?
- Is pre-publish validation catching all issues?

**Files to Deep Dive**:
- `backend/integrations/ebay/publish.py` - Full publish flow
- `backend/integrations/ebay/client.py` - API calls
- `backend/integrations/ebay/media_api.py` - Image upload
- Check error handling at each step

**Test Cases to Verify**:
- Publish with complete book data
- Publish with missing fields (should fail gracefully)
- Verify image upload success
- Check offer creation payload
- Verify publish succeeds

### Area 4: Error Handling & Logging
**Questions to Answer**:
- Are errors being caught and logged properly?
- Are user-friendly error messages being returned?
- Is error context preserved through the flow?
- Are validation errors being surfaced to the UI?

**Files to Deep Dive**:
- All route handlers for error handling
- Logging statements throughout the flow
- Frontend error display

## Specific Issues to Investigate

### Issue 1: Vision Extraction Failures
**Symptoms**:
- Missing or incorrect fields extracted from images
- AI validation errors
- Fields not mapping to Book model correctly

**Investigation Path**:
1. Review `backend/services/vision_extraction.py` extraction logic
2. Check `backend/ai/prompt_booklister.py` prompt quality
3. Verify JSON parsing and validation
4. Check field mapping in `map_to_book_fields()`
5. Review error handling in `backend/routes/ai_vision.py`

**Expected Output**:
- Identify missing/incorrect field extraction
- Fix prompt if needed
- Fix field mapping if needed
- Improve error messages

### Issue 2: Mapping Validation Failures
**Symptoms**:
- Required fields missing in eBay payload
- Category/aspect validation failures
- Field format mismatches

**Investigation Path**:
1. Review `backend/integrations/ebay/mapping.py` mapping logic
2. Check `backend/integrations/ebay/mapping_validation.py` validation
3. Compare Book model fields to eBay requirements
4. Verify category/aspect handling
5. Check title truncation logic

**Expected Output**:
- Identify missing required fields
- Fix mapping logic
- Improve validation
- Add missing field handling

### Issue 3: Publishing Flow Failures
**Symptoms**:
- Publish fails with validation errors
- Currency/price issues (Error 25002 related)
- Policy ID validation failures
- Image upload failures

**Investigation Path**:
1. Review `backend/integrations/ebay/publish.py` publish flow
2. Check `prepare_for_publish()` validation
3. Verify `ensure_offer_is_publishable()` logic
4. Check `prepublish_assertions()` validation
5. Review image upload flow
6. Check API error handling

**Expected Output**:
- Identify validation gaps
- Fix pre-publish checks
- Improve error handling
- Add missing validations

### Issue 4: Data Flow Issues
**Symptoms**:
- Data lost between steps
- Fields not persisting to database
- Status not updating correctly

**Investigation Path**:
1. Trace data flow from upload → vision → review → publish
2. Check database updates at each step
3. Verify Book model field updates
4. Check status transitions

**Expected Output**:
- Identify data loss points
- Fix database updates
- Ensure status transitions are correct

## Testing Strategy

### Unit Tests to Review
- `backend/tests/test_vision_extraction.py` - Vision extraction tests
- `backend/tests/test_mapping.py` - Mapping tests
- `backend/tests/test_mapping_validation.py` - Validation tests
- `backend/tests/test_publish_e2e.py` - End-to-end publish tests
- `backend/tests/test_media_api.py` - Media API tests

### Integration Tests to Run
1. **Full Flow Test**:
   - Upload images → Vision extraction → Review → Publish
   - Verify each step succeeds
   - Check database state at each step

2. **Error Path Tests**:
   - Missing required fields
   - Invalid field formats
   - API failures
   - Validation failures

## Documentation to Review

1. **`status/STATUS.md`** - Current implementation status
2. **`status/ERROR_25002_FIX_REPORT.md`** - Previous fix details
3. **`status/MVP_PROGRESS_REPORT.md`** - Implementation progress
4. **`info/ebay_book_listing_fields.md`** - Expected field schema
5. **`info/ebay_api_field_mappings.md`** - Field mapping docs
6. **`CLAUDE.md`** - Architecture overview
7. **`README.md`** - User guide and troubleshooting

## Expected Deliverables

### 1. Root Cause Analysis
- Identify all issues preventing successful image-to-listing flow
- Categorize issues by area (vision extraction, mapping, publishing)
- Prioritize by impact and frequency

### 2. Specific Fixes
- Provide code fixes for each identified issue
- Include file paths and line numbers
- Explain why each fix addresses the root cause

### 3. Validation Improvements
- Add missing validations
- Improve error messages
- Add logging for debugging

### 4. Testing Recommendations
- Suggest test cases to verify fixes
- Recommend integration tests
- Identify edge cases to test

### 5. Documentation Updates
- Update status documents with findings
- Document fixes applied
- Update troubleshooting guide

## Success Criteria

The fixes should enable:
1. ✅ Successful vision extraction from book images
2. ✅ All required fields extracted and mapped correctly
3. ✅ Successful mapping from Book model to eBay format
4. ✅ Pre-publish validation catches all issues
5. ✅ Successful publishing to eBay with all required fields
6. ✅ Clear error messages when issues occur
7. ✅ Proper logging for debugging

## Notes

- The codebase uses FastAPI (Python) backend and Next.js (TypeScript) frontend
- Database is SQLite with SQLModel ORM
- AI providers supported: OpenAI, OpenRouter, Google Gemini
- eBay APIs: Sell Inventory API, Media API, OAuth2
- All sensitive data (API keys, tokens) stored in `.env` (excluded from git)

## Starting Points

Begin investigation by:
1. Reading `status/STATUS.md` for current state
2. Reviewing `status/ERROR_25002_FIX_REPORT.md` for previous fixes
3. Tracing a complete flow from `backend/routes/upload.py` through `backend/integrations/ebay/publish.py`
4. Checking error logs and validation failures
5. Comparing expected vs actual data at each step

Good luck with your investigation! 🚀

