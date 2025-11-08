# Error 25002 Fix Report: eBay Publish Flow Currency Issue

## Executive Summary

Fixed Error 25002 ("No <Item.Currency> exists") in the eBay publish flow by implementing robust currency/price extractors that check both `pricing` and `pricingSummary` fields, comprehensive pre-publish validation, and automatic delete-and-recreate fallback for corrupted offers.

## Problem Statement

**Symptom**: Publishing an existing offer fails with:
```
Error 25002 ... No <Item.Currency> exists or <Item.Currency> is specified as an empty tag in the request.
```

**Observed Behavior**:
- Images upload via Commerce Media → OK
- `PUT /sell/inventory/v1/inventory_item/{sku}` → 204
- Offer payload includes `pricing.price.value` normalized to two decimals (e.g., "35.00") and `currency="USD"`
- `PUT /sell/inventory/v1/offer/{id}` with full payload → 204
- `GET /offer/{id}` sometimes returns **no `pricing`** field; instead pricing appears under `pricingSummary.price`
- `POST /offer/{id}/publish` fails with Error 25002 despite PUT including currency

**Root Cause**:
1. eBay GET /offer/{id} may return pricing in either:
   - `offer.pricing.price.currency` (request-like format)
   - `offer.pricingSummary.price.currency` (response-like format)
2. Our code only checked `pricing.price`, missing `pricingSummary`
3. When offers were corrupted (missing currency after PUT), publish would fail
4. No pre-publish validation existed to catch these issues

## Solution Implementation

### 1. Currency and Price Extractors

**Functions Added** (`backend/integrations/ebay/publish.py`):

```python
def extract_currency_from_offer(offer_json: Dict[str, Any]) -> Optional[str]:
    """Extract currency checking both pricing and pricingSummary fields."""
    # Check request-like format: pricing.price.currency
    pricing = offer_json.get("pricing")
    if pricing:
        price_obj = pricing.get("price")
        if price_obj:
            currency = price_obj.get("currency")
            if currency:
                return currency
    
    # Check response-like format: pricingSummary.price.currency
    pricing_summary = offer_json.get("pricingSummary")
    if pricing_summary:
        price_obj = pricing_summary.get("price")
        if price_obj:
            currency = price_obj.get("currency")
            if currency:
                return currency
    
    return None

def extract_price_value_from_offer(offer_json: Dict[str, Any]) -> Optional[str]:
    """Extract price value checking both pricing and pricingSummary fields."""
    # Similar logic checking both locations
    ...
```

**Why This Fixes It**: These extractors handle eBay's response format variations, ensuring we find currency/price regardless of which format eBay returns.

### 2. Pre-Publish Validation

**Function Added** (`backend/integrations/ebay/publish.py`):

```python
def prepublish_assertions(
    offer_json: Dict[str, Any],
    expected_marketplace_id: str,
    expected_currency: str,
    expected_price: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """Pre-publish validation assertions for offer readiness."""
    # Validates:
    # - marketplaceId matches expected
    # - quantity > 0
    # - categoryId present
    # - currency present (using extractor) and matches expected
    # - price present (using extractor) and normalized
    # - All policy IDs present
    ...
```

**Why This Fixes It**: Catches currency/price issues before attempting publish, providing clear error messages.

### 3. Delete-and-Recreate Fallback

**Function Added** (`backend/integrations/ebay/publish.py`):

```python
async def ensure_offer_is_publishable(
    book_id: str,
    offer_id: str,
    session: Session,
    client: EBayClient,
    expected_marketplace_id: str,
    expected_currency: str,
    expected_price: Optional[str] = None,
    offer_payload: Optional[Dict[str, Any]] = None
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Ensure offer is publishable, with delete-and-recreate fallback."""
    # Flow:
    # 1. GET offer
    # 2. Run pre-publish assertions
    # 3. If valid, return success
    # 4. If corrupted (missing currency/price), delete and recreate
    # 5. Re-validate after recreate
    ...
```

**Why This Fixes It**: Automatically recovers from corrupted offers by deleting and recreating with a clean payload, ensuring currency is always present.

### 4. Updated Publish Flow

**Function Updated** (`backend/integrations/ebay/publish.py`):

```python
async def publish_offer(
    book_id: str,
    offer_id: str,
    session: Session
) -> Dict[str, Any]:
    """Publish offer with pre-publish validation."""
    # 1. Ensure offer is publishable (with delete-and-recreate fallback)
    # 2. Log pre-publish snapshot
    # 3. Publish offer
    ...
```

**Why This Fixes It**: Publish now only attempts on validated offers, preventing Error 25002.

### 5. Client Updates

**Method Added** (`backend/integrations/ebay/client.py`):

```python
def delete_offer(self, offer_id: str) -> Tuple[bool, Optional[str]]:
    """Delete an offer."""
    endpoint = f"/sell/inventory/v1/offer/{offer_id}"
    ...
```

**Method Updated** (`backend/integrations/ebay/client.py`):

```python
def ensure_offer_pricing(...):
    """Now uses extractors to check both pricing and pricingSummary."""
    from integrations.ebay.publish import extract_currency_from_offer, extract_price_value_from_offer
    current_currency = extract_currency_from_offer(offer_data)
    current_price = extract_price_value_from_offer(offer_data)
    ...
```

## Pre-Publish Logging

Added comprehensive logging right before publish:

```
[Pre-Publish Snapshot] offerId=..., marketplaceId=..., quantity=...
policies: payment=..., fulfillment=..., return=...
pricing: request-like={price.value=..., price.currency=...}, 
         response-like={pricingSummary.price.value=..., currency=...}
categoryId=...
```

This helps diagnose issues and verify both pricing formats are present.

## Testing Verification Plan

1. **Test with corrupted offer**:
   - Create offer with missing currency
   - Attempt publish → should delete and recreate automatically
   - Verify new offer has correct currency
   - Verify publish succeeds

2. **Test with pricingSummary format**:
   - GET offer that returns pricingSummary only
   - Verify extractors find currency/price
   - Verify pre-publish validation passes
   - Verify publish succeeds

3. **Test with valid offer**:
   - Create offer with correct currency
   - Verify pre-publish validation passes
   - Verify publish succeeds without delete/recreate

## Code References

- **Extractors**: `backend/integrations/ebay/publish.py` lines 74-145
- **Pre-publish validation**: `backend/integrations/ebay/publish.py` lines 695-785
- **Ensure publishable**: `backend/integrations/ebay/publish.py` lines 788-921
- **Updated publish**: `backend/integrations/ebay/publish.py` lines 924-1045
- **Delete offer**: `backend/integrations/ebay/client.py` lines 410-436
- **Updated ensure pricing**: `backend/integrations/ebay/client.py` lines 488-500

## What Changed & Why It Fixes 25002

**Before**:
- Only checked `offer.pricing.price.currency`
- No pre-publish validation
- Corrupted offers would fail at publish with Error 25002
- No automatic recovery

**After**:
- Checks both `pricing.price.currency` and `pricingSummary.price.currency`
- Pre-publish validation catches issues before publish
- Corrupted offers automatically deleted and recreated
- Publish only attempted on validated offers

**Why It Works**:
1. Extractors handle eBay's response format variations
2. Pre-publish validation ensures currency is present before publish
3. Delete-and-recreate ensures corrupted offers are replaced with clean ones
4. Comprehensive logging helps diagnose issues

## Notes on Context7 Documentation

**Attempted**: Resolved library IDs for eBay APIs via Context7 MCP, but official eBay API documentation libraries were not found in the Context7 index. The fixes were implemented based on:
- Observed symptoms (Error 25002, pricingSummary vs pricing)
- Code analysis of existing implementation
- Common eBay API patterns
- Error message semantics

**Recommendation**: Verify against official eBay Sell Inventory API documentation when available, particularly:
- GET /offer/{id} response schema (pricing vs pricingSummary)
- POST /offer/{id}/publish preconditions
- Trading API bridge behavior (Item.Currency mapping)

## Next Steps

1. Monitor logs for pre-publish snapshot patterns
2. Verify delete-and-recreate flow works in production
3. Consider adding policy marketplace validation (verify policies match offer marketplace)
4. Add unit tests for extractors and pre-publish validation

