# Response to Deep Research AI - Investigation Guidance

## Investigation Approach

### Recommended: **Systematic End-to-End Review**

Please conduct a **complete review across all four issue categories**, but prioritize them in this order:

1. **Vision Extraction Quality** (Start Here)
   - This is the foundation - if extraction fails, everything downstream fails
   - Check if AI is extracting all required fields correctly
   - Verify field mapping from AI output to Book model

2. **Book Model → eBay Mapping** (Second Priority)
   - Verify extracted data maps correctly to eBay format
   - Check for missing required eBay fields
   - Validate category/aspect handling

3. **Publishing Flow Validation** (Third Priority)
   - Check pre-publish validation catches all issues
   - Verify API calls succeed with correct payloads
   - Check error handling and recovery

4. **Data Flow Issues** (Fourth Priority)
   - Trace data through entire flow
   - Verify database updates at each step
   - Check status transitions

## Where to Find Error Data

### 1. Database Error Storage

**Location**: `backend/data/books.db` (SQLite database)

**Error Fields in Book Model** (`backend/models.py`):
- `ai_validation_errors: List[str]` (line 53) - Stores validation errors from vision extraction as JSON array
- `publish_status: Optional[str]` (line 70) - Can be "published", "failed", "pending", or None
- `ebay_offer_id: Optional[str]` (line 68) - If None, offer creation may have failed
- `ebay_listing_id: Optional[str]` (line 69) - If None, publish may have failed

**How to Access**:
```python
# You can use SQLite to query the database
import sqlite3
conn = sqlite3.connect('backend/data/books.db')
cursor = conn.cursor()

# Find books with validation errors
cursor.execute("SELECT id, ai_validation_errors, publish_status FROM books WHERE ai_validation_errors IS NOT NULL AND json_array_length(ai_validation_errors) > 0")

# Find books that failed to publish
cursor.execute("SELECT id, publish_status, ebay_offer_id, ebay_listing_id FROM books WHERE publish_status = 'failed' OR (publish_status IS NULL AND ebay_listing_id IS NULL)")

# Get all books with their status
cursor.execute("SELECT id, status, title, ai_validation_errors, publish_status FROM books ORDER BY created_at DESC LIMIT 20")
```

### 2. Console Logs

**Logging**: All errors are logged to console using Python `logging` module

**Key Files with Error Logging**:
- `backend/routes/ai_vision.py` - Vision extraction errors
- `backend/integrations/ebay/publish.py` - Publishing errors
- `backend/integrations/ebay/client.py` - API call errors (lines 210-219)
- `backend/services/vision_extraction.py` - Vision service errors
- `backend/main.py` - General exception handler (lines 66-75)

**Log Format**: Errors are logged with full stack traces and context

**Note**: The `backend/logs/` directory exists but is currently empty - logs go to console/stdout

### 3. Frontend Error Display

**Location**: `frontend/src/app/review/page.tsx`

**Error Display**:
- Toast notifications for errors
- Error messages in UI
- Status badges showing failure states

### 4. Test Files (For Understanding Expected Behavior)

**Test Files to Review**:
- `backend/tests/test_vision_extraction.py` - Vision extraction tests
- `backend/tests/test_mapping.py` - Mapping tests
- `backend/tests/test_mapping_validation.py` - Validation tests
- `backend/tests/test_publish_e2e.py` - End-to-end publish tests
- `backend/tests/test_media_api.py` - Media API tests

These show expected behavior and can help identify discrepancies.

## Specific Failure Patterns to Look For

### Pattern 1: Vision Extraction Failures

**Symptoms**:
- `ai_validation_errors` field contains error messages
- Books stuck in `status = "new"` after vision extraction attempt
- Missing required fields (title, author, ISBN, etc.)
- Fields extracted but in wrong format

**Investigation**:
1. Check `backend/services/vision_extraction.py` - `extract_from_images_vision()` method
2. Review `backend/ai/prompt_booklister.py` - Prompt quality
3. Check JSON parsing in `backend/routes/ai_vision.py`
4. Verify field mapping in `map_to_book_fields()`

**Database Query**:
```sql
SELECT id, status, title, ai_validation_errors 
FROM books 
WHERE ai_validation_errors IS NOT NULL 
AND json_array_length(ai_validation_errors) > 0;
```

### Pattern 2: Mapping Failures

**Symptoms**:
- Books have extracted data but publish fails
- Missing required eBay fields in payload
- Category/aspect validation errors
- Title truncation issues

**Investigation**:
1. Check `backend/integrations/ebay/mapping.py` - `build_inventory_item()` and `build_offer()`
2. Review `backend/integrations/ebay/mapping_validation.py` - Validation logic
3. Compare Book model fields to eBay requirements in `info/ebay_api_field_mappings.md`

**Database Query**:
```sql
SELECT id, title, title_ai, description_ai, price_suggested, ebay_category_id, publish_status
FROM books 
WHERE title_ai IS NOT NULL 
AND (publish_status = 'failed' OR publish_status IS NULL);
```

### Pattern 3: Publishing Flow Failures

**Symptoms**:
- `publish_status = "failed"`
- `ebay_offer_id` exists but `ebay_listing_id` is None
- Pre-publish validation errors
- API error responses

**Investigation**:
1. Check `backend/integrations/ebay/publish.py` - `publish_book()` and `publish_offer()`
2. Review `prepublish_assertions()` validation
3. Check `ensure_offer_is_publishable()` logic
4. Review API error handling in `backend/integrations/ebay/client.py`

**Database Query**:
```sql
SELECT id, publish_status, ebay_offer_id, ebay_listing_id, price_suggested, verified
FROM books 
WHERE publish_status = 'failed' 
OR (ebay_offer_id IS NOT NULL AND ebay_listing_id IS NULL);
```

### Pattern 4: Data Flow Issues

**Symptoms**:
- Data lost between steps
- Status not updating correctly
- Fields not persisting to database

**Investigation**:
1. Trace data flow: upload → vision → review → publish
2. Check database updates at each step
3. Verify Book model field updates
4. Check status transitions

**Database Query**:
```sql
SELECT id, status, created_at, updated_at, title, title_ai, description_ai, publish_status
FROM books 
ORDER BY created_at DESC 
LIMIT 10;
```

## Sample Book Images

**Location**: `backend/data/images/{book_id}/`

**Note**: Actual book images are stored locally but excluded from git (in `.gitignore`). If you need to test with images, you can:
1. Check if there are any test images in `backend/tests/fixtures/`
2. Use the database to find books with images: `SELECT id FROM books WHERE id IN (SELECT DISTINCT book_id FROM images)`

## AI Output Examples

**Expected Format**: See `backend/models/ai.py` for expected AI output structure:
- `CoreFields` - Basic book metadata
- `AIDescription` - AI-generated description
- `EnrichResult` - Complete extraction result

**Actual Outputs**: Check `book.specifics_ai` field in database (JSON field) for actual AI extraction results

**Database Query**:
```sql
SELECT id, title_ai, description_ai, specifics_ai, ai_validation_errors
FROM books 
WHERE title_ai IS NOT NULL 
LIMIT 5;
```

## Investigation Checklist

### Phase 1: Vision Extraction (Priority 1)
- [ ] Review `backend/services/vision_extraction.py` extraction logic
- [ ] Check `backend/ai/prompt_booklister.py` prompt quality
- [ ] Verify JSON parsing and validation
- [ ] Check field mapping in `map_to_book_fields()`
- [ ] Query database for books with `ai_validation_errors`
- [ ] Compare extracted fields to expected schema in `info/ebay_book_listing_fields.md`

### Phase 2: Mapping (Priority 2)
- [ ] Review `backend/integrations/ebay/mapping.py` mapping logic
- [ ] Check `backend/integrations/ebay/mapping_validation.py` validation
- [ ] Compare Book model fields to eBay requirements
- [ ] Verify category/aspect handling
- [ ] Check title truncation logic
- [ ] Query database for books with extracted data but no publish

### Phase 3: Publishing Flow (Priority 3)
- [ ] Review `backend/integrations/ebay/publish.py` publish flow
- [ ] Check `prepare_for_publish()` validation
- [ ] Verify `ensure_offer_is_publishable()` logic
- [ ] Check `prepublish_assertions()` validation
- [ ] Review image upload flow
- [ ] Check API error handling
- [ ] Query database for failed publishes

### Phase 4: Data Flow (Priority 4)
- [ ] Trace data flow from upload → vision → review → publish
- [ ] Check database updates at each step
- [ ] Verify Book model field updates
- [ ] Check status transitions
- [ ] Verify error persistence

## Expected Deliverables

After investigation, please provide:

1. **Root Cause Analysis**
   - List all issues found, categorized by area
   - Prioritize by impact and frequency
   - Explain root causes, not just symptoms

2. **Specific Fixes**
   - Code fixes for each issue with file paths and line numbers
   - Explain why each fix addresses the root cause
   - Include before/after code examples

3. **Validation Improvements**
   - Missing validations to add
   - Improved error messages
   - Additional logging for debugging

4. **Testing Recommendations**
   - Test cases to verify fixes
   - Integration test scenarios
   - Edge cases to test

5. **Documentation Updates**
   - Update status documents with findings
   - Document fixes applied
   - Update troubleshooting guide

## Starting Points

**Recommended Starting Sequence**:

1. **Start with Database Analysis**:
   - Query `backend/data/books.db` to find books with errors
   - Identify patterns in `ai_validation_errors`
   - Check `publish_status` for failures

2. **Review Vision Extraction**:
   - Read `backend/services/vision_extraction.py` completely
   - Check `backend/ai/prompt_booklister.py` prompt
   - Trace through `backend/routes/ai_vision.py` endpoint

3. **Check Mapping Logic**:
   - Review `backend/integrations/ebay/mapping.py`
   - Check validation in `backend/integrations/ebay/mapping_validation.py`
   - Compare to eBay requirements

4. **Examine Publishing Flow**:
   - Read `backend/integrations/ebay/publish.py` completely
   - Check error handling in `backend/integrations/ebay/client.py`
   - Review API call sequences

5. **Trace Complete Flow**:
   - Follow one book from upload to publish (or failure point)
   - Check database state at each step
   - Identify where data is lost or corrupted

## Questions to Answer

1. **Vision Extraction**:
   - Are all required fields being extracted?
   - Is the prompt producing correct JSON structure?
   - Are field mappings correct?
   - Are validation errors being caught?

2. **Mapping**:
   - Are all Book fields mapped to eBay format?
   - Are required eBay fields always present?
   - Is category selection correct?
   - Are item specifics properly formatted?

3. **Publishing**:
   - Are all required fields validated before publish?
   - Is currency/price validation working?
   - Are policy IDs validated?
   - Is image upload working?
   - Are offers created correctly?

4. **Data Flow**:
   - Is data preserved through the flow?
   - Are database updates happening correctly?
   - Are status transitions correct?

## Additional Resources

- **Architecture Overview**: `CLAUDE.md`
- **Status & History**: `status/STATUS.md`
- **Error Reports**: `status/ERROR_25002_FIX_REPORT.md`
- **Field Schema**: `info/ebay_book_listing_fields.md`
- **Field Mappings**: `info/ebay_api_field_mappings.md`
- **Implementation Plan**: `status/plan.md`

Good luck with your investigation! 🚀

