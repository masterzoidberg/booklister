"""
eBay publish flow with image upload integration
"""
import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import datetime as dt
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from sqlmodel import Session
from fastapi import HTTPException

from models import Book
from settings import ebay_settings
from integrations.ebay.mapping import build_inventory_item, build_offer
from integrations.ebay.images import resolve_listing_urls
from integrations.ebay.client import EBayClient
from integrations.ebay.utils.money import to_money_str, equal_money
from services.policy_settings import get_policy_settings

logger = logging.getLogger(__name__)

# Offer trace directory (for payload logging)
OFFER_TRACE_DIR = Path("backend/logs/offer_payloads")

# [Context7] Using /fastapi/fastapi (HTTPException 422 for preflight validation)
# [Context7] Using /websites/pydantic_dev (Decimal.quantize for 2-decimal formatting)

# Marketplace to currency mapping
# Extensible for international marketplaces
MARKETPLACE_CURRENCY = {
    "EBAY_US": "USD",
    "EBAY_GB": "GBP",
    "EBAY_AU": "AUD",
    "EBAY_DE": "EUR",
    "EBAY_CA": "CAD",
}


def normalize_price_str(value: Any) -> str:
    """
    Normalize price to string with exactly 2 decimal places.

    Wrapper around to_money_str for consistency with spec requirements.

    Args:
        value: Numeric value (int, float, Decimal, or numeric string)

    Returns:
        String with exactly 2 decimal places (e.g., "35.00")

    Raises:
        ValueError: If value cannot be converted to Decimal
    """
    return to_money_str(value)


# DEPRECATED: Use to_money_str from integrations.ebay.utils.money instead
# Kept for backward compatibility, but delegates to to_money_str
def normalize_price(value: Any) -> str:
    """
    Normalize price to string with exactly 2 decimal places.

    DEPRECATED: Use to_money_str() from integrations.ebay.utils.money instead.
    This function is kept for backward compatibility and delegates to to_money_str.

    Args:
        value: Numeric value (int, float, Decimal, or numeric string)

    Returns:
        String with exactly 2 decimal places (e.g., "35.00")

    Raises:
        ValueError: If value cannot be converted to Decimal
    """
    return to_money_str(value)


def create_offer_and_verify(
    client: EBayClient,
    payload: Dict[str, Any],
    max_retries: int = 5,
    backoff_sec: float = 0.6
) -> str:
    """
    Create offer with read-after-write verification and retries.

    This function:
    1. Normalizes price to two-decimal string
    2. Saves request payload to trace file
    3. POSTs offer creation
    4. Retries GET until offer exists and is in valid status
    5. Returns verified offerId

    Args:
        client: EBayClient instance
        payload: Offer payload dict
        max_retries: Maximum GET retries for verification (default: 5)
        backoff_sec: Initial backoff in seconds (default: 0.6)

    Returns:
        Verified offerId string

    Raises:
        RuntimeError: If create fails or verification fails after retries
    """
    # Extract SKU for logging
    sku = payload.get("sku", "unknown")

    # Ensure price normalization (two-decimal string)
    pricing_summary = payload.get("pricingSummary", {})
    price_obj = pricing_summary.get("price", {})
    price_value = price_obj.get("value")
    if price_value:
        try:
            normalized_price = normalize_price_str(price_value)
            payload["pricingSummary"]["price"]["value"] = normalized_price
            logger.info(f"[OfferCreate] Normalized price for SKU={sku}: {price_value} → {normalized_price}")
        except ValueError as e:
            raise RuntimeError(f"Invalid price value for SKU={sku}: {price_value} ({e})")

    # Trace request payload
    OFFER_TRACE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    trace_file = OFFER_TRACE_DIR / f"{timestamp}-{sku}-create.json"
    try:
        with open(trace_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        logger.info(f"[OfferCreate] Traced payload to {trace_file}")
    except Exception as e:
        logger.warning(f"[OfferCreate] Failed to save trace: {e}")

    # POST offer creation
    success, response_data, offer_id, error = client.create_offer(offer=payload)

    if not success or not offer_id:
        error_msg = f"Create failed for SKU={sku}: {error}"
        logger.error(f"[OfferCreate] {error_msg}")
        # Save error response to trace
        try:
            error_trace_file = OFFER_TRACE_DIR / f"{timestamp}-{sku}-create-error.json"
            with open(error_trace_file, "w", encoding="utf-8") as f:
                json.dump({"error": error, "response": response_data}, f, indent=2)
            logger.error(f"[OfferCreate] Error trace saved to {error_trace_file}")
        except Exception as e:
            logger.warning(f"[OfferCreate] Failed to save error trace: {e}")
        raise RuntimeError(error_msg)

    logger.info(f"[OfferCreate] status=201 offerId={offer_id} for SKU={sku}")

    # Retry GET until offer exists and is in valid status
    valid_statuses = {"UNPUBLISHED", "PUBLISHED", "PUBLISHED_OUT_OF_STOCK"}
    for attempt in range(1, max_retries + 1):
        wait_time = backoff_sec * attempt
        time.sleep(wait_time)

        logger.info(f"[OfferVerify] Attempt {attempt}/{max_retries} - GET offer {offer_id}")
        get_success, offer_data, get_error = client.get_offer(offer_id)

        if get_success and offer_data:
            offer_status = offer_data.get("status")
            if offer_status in valid_statuses:
                logger.info(f"[OfferVerify] confirmed offerId={offer_id} status={offer_status} for SKU={sku}")
                return offer_id
            else:
                logger.warning(
                    f"[OfferVerify] Offer {offer_id} has unexpected status: {offer_status}, retrying..."
                )
        else:
            logger.warning(
                f"[OfferVerify] GET failed for offer {offer_id} (attempt {attempt}): {get_error}"
            )

    # All retries exhausted
    error_msg = f"Offer verification failed for offerId={offer_id} after {max_retries} retries"
    logger.error(f"[OfferVerify] {error_msg}")
    raise RuntimeError(error_msg)


def verify_offer_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify and log critical fields in offer payload before sending to eBay.

    Args:
        payload: Offer payload to verify

    Returns:
        Dict with verification report (for logging)

    Raises:
        HTTPException if critical fields are missing
    """
    report = {
        "sku": payload.get("sku"),
        "marketplaceId": payload.get("marketplaceId"),
        "format": payload.get("format"),
        "categoryId": payload.get("categoryId"),
        "price_value": None,
        "price_currency": None,
        "paymentPolicyId": None,
        "returnPolicyId": None,
        "fulfillmentPolicyId": None,
        "merchantLocationKey": payload.get("merchantLocationKey"),
        "quantity": payload.get("availableQuantity") or payload.get("quantity")
    }

    # Extract price from nested structure
    pricing = payload.get("pricingSummary") or payload.get("pricing")
    if pricing:
        price_obj = pricing.get("price")
        if price_obj:
            report["price_value"] = price_obj.get("value")
            report["price_currency"] = price_obj.get("currency")

    # Extract policy IDs from various possible locations
    # Payment policy
    if "pricingSummary" in payload and "paymentPolicyId" in payload["pricingSummary"]:
        report["paymentPolicyId"] = payload["pricingSummary"]["paymentPolicyId"]
    elif "paymentPolicyId" in payload:
        report["paymentPolicyId"] = payload["paymentPolicyId"]

    # Return policy
    if "returnPolicyId" in payload:
        report["returnPolicyId"] = payload["returnPolicyId"]

    # Fulfillment policy
    if "fulfillmentPolicyId" in payload:
        report["fulfillmentPolicyId"] = payload["fulfillmentPolicyId"]

    # Check critical fields
    missing = []
    if not report["sku"]:
        missing.append("sku")
    if not report["marketplaceId"]:
        missing.append("marketplaceId")
    if not report["categoryId"]:
        missing.append("categoryId")
    if not report["price_value"]:
        missing.append("price.value")
    if not report["price_currency"]:
        missing.append("price.currency")
    if not report["paymentPolicyId"]:
        missing.append("paymentPolicyId")
    if not report["returnPolicyId"]:
        missing.append("returnPolicyId")
    if not report["fulfillmentPolicyId"]:
        missing.append("fulfillmentPolicyId")

    if missing:
        logger.error(f"[Offer Verification] FAILED - Missing fields: {missing}")
        logger.error(f"[Offer Verification] Report: {json.dumps(report, indent=2)}")
        raise HTTPException(
            status_code=422,
            detail=f"Offer payload missing required fields: {', '.join(missing)}"
        )

    # Log success
    logger.info(f"[Offer Verification] PASSED - {json.dumps(report, separators=(',', ':'))}")

    return report


def extract_currency_from_offer(offer_json: Dict[str, Any]) -> Optional[str]:
    """
    Extract currency from offer JSON, checking both pricing and pricingSummary fields.

    eBay GET /offer/{id} may return pricing in either:
    - offer.pricing.price.currency (request-like format)
    - offer.pricingSummary.price.currency (response-like format)
    
    This function checks both locations and returns the first found currency.
    
    Args:
        offer_json: Offer JSON from GET /offer/{id}
    
    Returns:
        Currency code (e.g., "USD") or None if not found
    """
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
    """
    Extract price value from offer JSON, checking both pricing and pricingSummary fields.
    
    eBay GET /offer/{id} may return pricing in either:
    - offer.pricing.price.value (request-like format)
    - offer.pricingSummary.price.value (response-like format)
    
    This function checks both locations and returns the first found price value.
    
    Args:
        offer_json: Offer JSON from GET /offer/{id}
    
    Returns:
        Price value string (e.g., "35.00") or None if not found
    """
    # Check request-like format: pricing.price.value
    pricing = offer_json.get("pricing")
    if pricing:
        price_obj = pricing.get("price")
        if price_obj:
            value = price_obj.get("value")
            if value is not None:
                return str(value)
    
    # Check response-like format: pricingSummary.price.value
    pricing_summary = offer_json.get("pricingSummary")
    if pricing_summary:
        price_obj = pricing_summary.get("price")
        if price_obj:
            value = price_obj.get("value")
            if value is not None:
                return str(value)
    
    return None


def validate_currency(offer_payload: Dict[str, Any], marketplace_id: str) -> None:
    """
    Preflight validation for offer currency.

    Validates that:
    1. Expected currency is defined for marketplace
    2. Offer pricingSummary structure is present (never pricing)
    3. Price value is present, numeric, and > 0
    4. Price is formatted with 2 decimal places (e.g., "35.00")
    5. Currency matches marketplace expected currency

    Raises HTTPException 422 on validation failure (fail-fast).

    Args:
        offer_payload: eBay offer payload (must contain pricingSummary.price.value and pricingSummary.price.currency)
        marketplace_id: eBay marketplace ID (e.g., "EBAY_US")

    Raises:
        HTTPException: 422 Unprocessable Entity if validation fails
    """
    # Check marketplace currency is defined
    expected_currency = MARKETPLACE_CURRENCY.get(marketplace_id)
    if not expected_currency:
        error_msg = f"No currency mapping for marketplace {marketplace_id}. Define in MARKETPLACE_CURRENCY."
        logger.error(f"[Currency Validation] {error_msg}")
        raise HTTPException(status_code=422, detail=error_msg)

    # Check pricingSummary structure (never pricing)
    pricing_summary = offer_payload.get("pricingSummary")
    if not pricing_summary:
        error_msg = "Offer payload missing 'pricingSummary' field (required by eBay Sell Inventory API)"
        logger.error(f"[Currency Validation] {error_msg}")
        raise HTTPException(status_code=422, detail=error_msg)

    # DEBUG: Reject if pricing field exists (should never happen)
    if "pricing" in offer_payload:
        logger.warning(
            f"[Currency Validation] WARNING: Offer payload contains deprecated 'pricing' field. "
            f"Only 'pricingSummary' should be used."
        )

    price_obj = pricing_summary.get("price")
    if not price_obj:
        error_msg = "Offer payload missing 'pricingSummary.price' field"
        logger.error(f"[Currency Validation] {error_msg}")
        raise HTTPException(status_code=422, detail=error_msg)

    # Validate price value
    price_value = price_obj.get("value")
    if price_value is None:
        error_msg = "Offer payload missing 'pricingSummary.price.value'"
        logger.error(f"[Currency Validation] {error_msg}")
        raise HTTPException(status_code=422, detail=error_msg)

    # Validate price is a string (eBay requires string format)
    if not isinstance(price_value, str):
        error_msg = f"Price value must be a string, got {type(price_value).__name__}: {price_value}"
        logger.error(f"[Currency Validation] {error_msg}")
        raise HTTPException(status_code=422, detail=error_msg)

    # Validate price is numeric and > 0
    try:
        price_decimal = Decimal(price_value)
        if price_decimal <= 0:
            error_msg = f"Price value must be > 0, got {price_value}"
            logger.error(f"[Currency Validation] {error_msg}")
            raise HTTPException(status_code=422, detail=error_msg)
    except (InvalidOperation, ValueError) as e:
        error_msg = f"Price value is not a valid decimal: {price_value} ({str(e)})"
        logger.error(f"[Currency Validation] {error_msg}")
        raise HTTPException(status_code=422, detail=error_msg)

    # Validate price has exactly 2 decimal places
    if '.' in price_value:
        decimal_part = price_value.split('.')[1]
        if len(decimal_part) != 2:
            error_msg = f"Price must have exactly 2 decimal places (e.g., '35.00'), got '{price_value}'"
            logger.error(f"[Currency Validation] {error_msg}")
            raise HTTPException(status_code=422, detail=error_msg)
    else:
        error_msg = f"Price must include decimal point and 2 decimal places (e.g., '35.00'), got '{price_value}'"
        logger.error(f"[Currency Validation] {error_msg}")
        raise HTTPException(status_code=422, detail=error_msg)

    # Validate currency
    currency = price_obj.get("currency")
    if not currency:
        error_msg = "Offer payload missing 'pricingSummary.price.currency'"
        logger.error(f"[Currency Validation] {error_msg}")
        raise HTTPException(status_code=422, detail=error_msg)

    if currency != expected_currency:
        error_msg = (
            f"Currency mismatch for marketplace {marketplace_id}: "
            f"expected '{expected_currency}', got '{currency}'"
        )
        logger.error(f"[Currency Validation] {error_msg}")
        raise HTTPException(status_code=422, detail=error_msg)

    # Validation passed
    logger.info(
        f"[Currency Validation] marketplace={marketplace_id} currency={currency} "
        f"price={to_money_str(price_value)}"
    )


async def prepare_for_publish(
    book_id: str,
    token: str,
    session: Session,
    payment_policy_id: Optional[str] = None,
    return_policy_id: Optional[str] = None,
    fulfillment_policy_id: Optional[str] = None,
    category_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Prepare book for publishing by resolving images and building inventory item.
    
    This function:
    1. Resolves image URLs (uploads via Media API if Strategy B)
    2. Validates images meet requirements
    3. Builds inventory item payload with image URLs
    4. Returns payload ready for eBay Inventory API
    
    Args:
        book_id: Book ID
        token: OAuth bearer token
        session: Database session
        payment_policy_id: Payment policy ID (from settings/env if None)
        return_policy_id: Return policy ID (from settings/env if None)
        fulfillment_policy_id: Fulfillment policy ID (from settings/env if None)
    
    Returns:
        Dict with:
            - inventory_item: eBay Inventory API payload
            - image_urls: List of resolved image URLs
            - title_length: Title length
            - title_truncated: Whether title was truncated
    
    Raises:
        HTTPException: On validation or image resolution failure
        ValueError: On missing required fields
    """
    # Get book
    book = session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found")
    
    # Resolve image URLs (uploads via Media API if Strategy B)
    try:
        # Use Media API base URL for media strategy, regular API base URL for self-host
        if ebay_settings.image_strategy == "media":
            base_url = ebay_settings.get_media_api_base_url()
        else:
            base_url = ebay_settings.get_api_base_url()
        image_urls = await resolve_listing_urls(
            book_id=book_id,
            token=token,
            session=session,
            base_url=base_url
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Image resolution failed: {str(e)}")
    except Exception as e:
        logger.error(f"Image resolution error for book {book_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Image resolution error: {str(e)}")
    
    # Validate image URLs
    if not image_urls:
        raise HTTPException(status_code=400, detail="No valid image URLs resolved")
    
    # Validate all URLs are HTTPS (required by eBay)
    for url in image_urls:
        if not url.startswith('https://'):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid image URL (must be HTTPS): {url}"
            )
    
    # Build inventory item with resolved image URLs
    try:
        inventory_item, title_length, title_truncated = build_inventory_item(
            book=book,
            image_urls=image_urls,
            category_id=category_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Inventory item build failed: {str(e)}")
    
    # Get policy IDs from saved defaults if not provided (auto-fetch and persist if missing)
    if not payment_policy_id or not return_policy_id or not fulfillment_policy_id:
        policy_service = get_policy_settings(session)
        defaults = policy_service.ensure_defaults(ebay_settings.ebay_marketplace_id)

        if not payment_policy_id:
            payment_policy_id = defaults.payment_policy_id
        if not return_policy_id:
            return_policy_id = defaults.return_policy_id
        if not fulfillment_policy_id:
            fulfillment_policy_id = defaults.fulfillment_policy_id

        # Fallback to environment settings if still None (no policies on account)
        if not payment_policy_id:
            payment_policy_id = ebay_settings.ebay_payment_policy_id if hasattr(ebay_settings, 'ebay_payment_policy_id') else None
        if not return_policy_id:
            return_policy_id = ebay_settings.ebay_return_policy_id if hasattr(ebay_settings, 'ebay_return_policy_id') else None
        if not fulfillment_policy_id:
            fulfillment_policy_id = ebay_settings.ebay_fulfillment_policy_id if hasattr(ebay_settings, 'ebay_fulfillment_policy_id') else None
    
    return {
        "inventory_item": inventory_item,
        "image_urls": image_urls,
        "title_length": title_length,
        "title_truncated": title_truncated,
        "payment_policy_id": payment_policy_id,
        "return_policy_id": return_policy_id,
        "fulfillment_policy_id": fulfillment_policy_id
    }


async def create_or_replace_inventory_item(
    book_id: str,
    session: Session,
    payment_policy_id: Optional[str] = None,
    return_policy_id: Optional[str] = None,
    fulfillment_policy_id: Optional[str] = None,
    category_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create or replace inventory item for a book.
    
    Args:
        book_id: Book ID
        session: Database session
        payment_policy_id: Payment policy ID
        return_policy_id: Return policy ID
        fulfillment_policy_id: Fulfillment policy ID
    
    Returns:
        Dict with:
            - success: bool
            - sku: SKU used
            - response: API response data
            - error: Error message if failed
    """
    # Get book
    book = session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found")
    
    # Get valid token for image resolution
    from integrations.ebay.token_store import TokenStore, get_encryption
    encryption = get_encryption()
    token_store = TokenStore(session, encryption)
    token_obj = token_store.get_valid_token("ebay")
    if not token_obj:
        raise HTTPException(status_code=401, detail="No valid OAuth token. Please authenticate via /ebay/oauth/auth-url")
    
    # Prepare for publish (resolves images and builds payload)
    prep_result = await prepare_for_publish(
        book_id=book_id,
        token=token_obj.access_token,
        session=session,
        payment_policy_id=payment_policy_id,
        return_policy_id=return_policy_id,
        fulfillment_policy_id=fulfillment_policy_id,
        category_id=category_id
    )
    
    inventory_item = prep_result["inventory_item"]
    sku = inventory_item.get("sku", book_id)

    # Validate packageWeightAndSize is present
    if "packageWeightAndSize" not in inventory_item:
        raise HTTPException(
            status_code=422,
            detail="Inventory item missing required packageWeightAndSize"
        )
    weight_data = inventory_item["packageWeightAndSize"].get("weight")
    if not weight_data or not weight_data.get("value") or weight_data.get("unit") != "POUND":
        raise HTTPException(
            status_code=422,
            detail="Inventory item packageWeightAndSize.weight must have value and unit=POUND"
        )

    # Log aspect names before API call for debugging Error 25001
    if "product" in inventory_item and "aspects" in inventory_item["product"]:
        aspects = inventory_item["product"]["aspects"]
        logger.info(f"[Pre-API Call] Book {book_id} - Exact aspect names being sent to eBay: {sorted(aspects.keys())}")
        for aspect_name in sorted(aspects.keys()):
            logger.info(f"[Pre-API Call]   Aspect name: '{aspect_name}' (type check: {type(aspect_name).__name__})")
    
    # Create eBay client
    client = EBayClient(session)
    
    # Create or replace inventory item
    success, response_data, error = client.create_or_replace_inventory_item(
        sku=sku,
        inventory_item=inventory_item
    )
    
    if success:
        logger.info(f"Successfully created/replaced inventory item for book {book_id} with SKU {sku}")
        return {
            "success": True,
            "sku": sku,
            "response": response_data,
            "error": None
        }
    else:
        logger.error(f"Failed to create/replace inventory item for book {book_id}: {error}")
        return {
            "success": False,
            "sku": sku,
            "response": response_data,
            "error": error
        }


async def create_or_update_offer(
    book_id: str,
    session: Session,
    payment_policy_id: Optional[str] = None,
    return_policy_id: Optional[str] = None,
    fulfillment_policy_id: Optional[str] = None,
    category_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create or update offer for a book (idempotent).

    Checks for existing offers by SKU and reuses them to avoid "Offer entity already exists" errors.

    Args:
        book_id: Book ID
        session: Database session
        payment_policy_id: Payment policy ID
        return_policy_id: Return policy ID
        fulfillment_policy_id: Fulfillment policy ID
        category_id: eBay category ID

    Returns:
        Dict with:
            - success: bool
            - offer_id: eBay offer ID if created/updated
            - action: "created" or "updated"
            - response: API response data
            - error: Error message if failed
    """
    # Get book
    book = session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found")

    # Validate required fields
    if book.price_suggested is None:
        error_msg = f"Book {book_id} must have price_suggested to create offer"
        logger.error(error_msg)
        raise HTTPException(status_code=400, detail=error_msg)

    # Pre-publish weight guard: Require shipping weight before creating offer
    weight_lb = book.shipping_weight_lb or 0.0
    weight_oz = book.shipping_weight_oz or 0.0
    total_weight_lb = weight_lb + (weight_oz / 16.0)
    
    if total_weight_lb <= 0:
        error_msg = "missing_shipping_weight"
        logger.error(f"[Pre-Publish Guard] Book {book_id}: {error_msg}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": error_msg,
                "message": "Please enter book weight (lb/oz) before publishing."
            }
        )

    # Get policy IDs from saved defaults if not provided (auto-fetch and persist if missing)
    marketplace_id = ebay_settings.ebay_marketplace_id
    if not payment_policy_id or not return_policy_id or not fulfillment_policy_id:
        policy_service = get_policy_settings(session)
        defaults = policy_service.ensure_defaults(marketplace_id)

        if not payment_policy_id:
            payment_policy_id = defaults.payment_policy_id
        if not return_policy_id:
            return_policy_id = defaults.return_policy_id
        if not fulfillment_policy_id:
            fulfillment_policy_id = defaults.fulfillment_policy_id

        # Fallback to environment settings if still None (no policies on account)
        if not payment_policy_id:
            payment_policy_id = ebay_settings.ebay_payment_policy_id if hasattr(ebay_settings, 'ebay_payment_policy_id') else None
        if not return_policy_id:
            return_policy_id = ebay_settings.ebay_return_policy_id if hasattr(ebay_settings, 'ebay_return_policy_id') else None
        if not fulfillment_policy_id:
            fulfillment_policy_id = ebay_settings.ebay_fulfillment_policy_id if hasattr(ebay_settings, 'ebay_fulfillment_policy_id') else None

    # Preflight validation: Fail fast with 422 if any policy ID is missing
    if not payment_policy_id or not return_policy_id or not fulfillment_policy_id:
        missing_policies = []
        if not payment_policy_id:
            missing_policies.append("payment_policy_id")
        if not return_policy_id:
            missing_policies.append("return_policy_id")
        if not fulfillment_policy_id:
            missing_policies.append("fulfillment_policy_id")
        error_msg = f"Payment, return, and fulfillment policy IDs are required. Missing: {', '.join(missing_policies)}"
        logger.error(f"[Policies] Book {book_id}: {error_msg}")
        raise HTTPException(
            status_code=422,
            detail=error_msg
        )

    # Log confirmation of resolved policy IDs
    logger.info(
        f"[Policies] Using IDs for book {book_id}: "
        f"payment={payment_policy_id}, "
        f"fulfillment={fulfillment_policy_id}, "
        f"return={return_policy_id} "
        f"(marketplace={marketplace_id})"
    )

    # Build offer payload
    try:
        offer = build_offer(
            book=book,
            payment_policy_id=payment_policy_id,
            return_policy_id=return_policy_id,
            fulfillment_policy_id=fulfillment_policy_id,
            category_id=category_id
        )
    except ValueError as e:
        error_msg = f"Offer build failed for book {book_id}: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=400, detail=error_msg)

    # Verify offer payload completeness
    try:
        verify_offer_payload(offer)
    except HTTPException:
        # Re-raise verification errors
        raise

    # Preflight validation: validate currency BEFORE any API calls
    try:
        validate_currency(offer, marketplace_id)
    except HTTPException:
        # Re-raise HTTPException as-is (already has proper status code and detail)
        raise

    # Log offer payload snapshot (first 2000 chars for debugging)
    offer_json = json.dumps(offer, indent=2)
    offer_snapshot = offer_json[:2000] + ("..." if len(offer_json) > 2000 else "")
    logger.info(f"[Offer Payload] Book {book_id} offer payload:\n{offer_snapshot}")

    # Create eBay client
    client = EBayClient(session)

    sku = book.id

    # Pre-check: Look for existing offers for this SKU
    logger.info(f"[Offer] Checking for existing offers for SKU={sku}, marketplace={marketplace_id}")
    check_success, existing_offers, check_error = client.get_offers_by_sku(sku, marketplace_id)

    existing_offer_id = None
    if check_success and existing_offers and len(existing_offers) > 0:
        # Found existing offer(s) - use the first one
        existing_offer_id = existing_offers[0].get("offerId")
        logger.info(f"[Offer] Found existing offer {existing_offer_id} for SKU={sku}")

        # Self-heal: Ensure existing offer has correct currency
        expected_currency = MARKETPLACE_CURRENCY.get(marketplace_id)
        expected_price = offer.get("pricingSummary", {}).get("price", {}).get("value")

        if expected_currency:
            logger.info(f"[Self-Heal] Checking offer {existing_offer_id} for currency={expected_currency}")
            heal_success, was_updated, heal_error = client.ensure_offer_pricing(
                offer_id=existing_offer_id,
                expected_currency=expected_currency,
                expected_price=expected_price
            )

            if not heal_success:
                logger.error(f"[Self-Heal] Failed to verify/update offer {existing_offer_id}: {heal_error}")
                # Continue anyway - update_offer below will retry
            elif was_updated:
                logger.warning(f"[Self-Heal] Offer {existing_offer_id} was corrected (had incorrect pricing)")
            else:
                logger.info(f"[Self-Heal] Offer {existing_offer_id} pricing is already correct")

    # Decide: create or update
    if existing_offer_id:
        # Update existing offer
        logger.info(f"[Guard] Modifying offer {existing_offer_id}; ensure pricingSummary preserved")
        logger.info(f"[Offer] Updating existing offer {existing_offer_id} for SKU={sku}")
        success, response_data, error = client.update_offer(existing_offer_id, offer)

        if success:
            # Verify update succeeded with read-after-write check
            logger.info(f"[OfferUpdate] 204 → reGET to verify")
            verify_success, verify_data, verify_error = client.get_offer(existing_offer_id)

            if verify_success and verify_data:
                # Check that price and policies match expectations
                verify_price = verify_data.get("pricingSummary", {}).get("price", {}).get("value")
                expected_price = offer.get("pricingSummary", {}).get("price", {}).get("value")
                verify_lp = verify_data.get("listingPolicies") or {}

                if verify_price != expected_price:
                    logger.warning(
                        f"[OfferUpdate] Price mismatch after update: "
                        f"expected={expected_price} got={verify_price}, retrying update"
                    )
                    # Retry update once
                    success2, response2, error2 = client.update_offer(existing_offer_id, offer)
                    if success2:
                        logger.info(f"[OfferUpdate] Retry succeeded for offer {existing_offer_id}")
                    else:
                        logger.error(f"[OfferUpdate] Retry failed for offer {existing_offer_id}: {error2}")

                # Log verified state
                logger.info(
                    f"[OfferUpdate] Verified offer {existing_offer_id}: "
                    f"price={verify_price} policies={sorted(verify_lp.keys())}"
                )
            else:
                logger.warning(f"[OfferUpdate] Verification GET failed: {verify_error}")

            logger.info(
                f"[Offer] Using offerId={existing_offer_id} for SKU={sku} (marketplace={marketplace_id}); "
                f"action=update; publish=pending"
            )
            return {
                "success": True,
                "offer_id": existing_offer_id,
                "action": "updated",
                "response": response_data,
                "error": None
            }
        else:
            logger.error(f"[Offer] Failed to update offer {existing_offer_id}: {error}")
            return {
                "success": False,
                "offer_id": None,
                "action": "update_failed",
                "response": response_data,
                "error": error
            }
    else:
        # Create new offer
        # Extract key values for logging
        price_value = offer.get("pricingSummary", {}).get("price", {}).get("value")
        currency = offer.get("pricingSummary", {}).get("price", {}).get("currency")
        
        # Log preflight: payload keys and key values
        payload_keys = sorted(offer.keys())
        logger.info(
            f"[Offer Build] sku={sku} mkt={marketplace_id} price_value={price_value} currency={currency}"
        )
        logger.info(f"[Offer Build] Payload keys: {payload_keys}")
        
        # Dump full payload to trace file
        import os
        from pathlib import Path
        from datetime import datetime
        
        trace_dir = Path("backend/logs/offer_payloads")
        trace_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        trace_file = trace_dir / f"{timestamp}-{sku}-create.json"
        
        try:
            with open(trace_file, "w", encoding="utf-8") as f:
                json.dump(offer, f, indent=2, ensure_ascii=False)
            logger.info(f"[Offer Build] Full payload traced to: {trace_file}")
        except Exception as e:
            logger.warning(f"[Offer Build] Failed to save trace: {e}")
        
        logger.info(f"[Offer] Creating new offer for SKU={sku}")

        # Use create_offer_and_verify for read-after-write verification
        try:
            offer_id = create_offer_and_verify(client, offer)
            success = True
            response_data = {"offerId": offer_id}  # Simplified response for consistency
            error = None
        except RuntimeError as e:
            success = False
            offer_id = None
            error = str(e)
            response_data = None
            logger.error(f"[Offer] create_offer_and_verify failed: {error}")

        if success:
            logger.info(
                f"[Offer] Using offerId={offer_id} for SKU={sku} (marketplace={marketplace_id}); "
                f"action=create; publish=pending"
            )
            return {
                "success": True,
                "offer_id": offer_id,
                "action": "created",
                "response": response_data,
                "error": None
            }
        elif "Offer entity already exists" in str(error):
            # Create failed with "already exists" - extract offer ID from error if possible
            logger.warning(f"[Offer] Create failed with 'already exists' for SKU={sku}, attempting recovery")

            # Try to extract offer ID from error response
            recovered_offer_id = None
            if response_data and isinstance(response_data, dict):
                # eBay may return offerId in error response
                recovered_offer_id = response_data.get("offerId")

            if not recovered_offer_id:
                # Retry the pre-check
                check_success2, existing_offers2, check_error2 = client.get_offers_by_sku(sku, marketplace_id)
                if check_success2 and existing_offers2 and len(existing_offers2) > 0:
                    recovered_offer_id = existing_offers2[0].get("offerId")

            if recovered_offer_id:
                logger.info(f"[Offer] Recovered offer ID {recovered_offer_id}, attempting update")
                success, response_data, error = client.update_offer(recovered_offer_id, offer)

                if success:
                    logger.info(
                        f"[Offer] Using offerId={recovered_offer_id} for SKU={sku} (marketplace={marketplace_id}); "
                        f"action=recovered_update; publish=pending"
                    )
                    return {
                        "success": True,
                        "offer_id": recovered_offer_id,
                        "action": "recovered_updated",
                        "response": response_data,
                        "error": None
                    }

            # Recovery failed
            logger.error(f"[Offer] Failed to create or recover offer for book {book_id}: {error}")
            return {
                "success": False,
                "offer_id": None,
                "action": "create_failed",
                "response": response_data,
                "error": error
            }
        else:
            logger.error(f"[Offer] Failed to create offer for book {book_id}: {error}")
            return {
                "success": False,
                "offer_id": None,
                "action": "create_failed",
                "response": response_data,
                "error": error
            }


# Backwards compatibility alias
create_offer = create_or_update_offer


def self_heal_offer_policies(
    client: EBayClient,
    offer_id: str,
    offer_data: Dict[str, Any],
    payment_policy_id: str,
    fulfillment_policy_id: str,
    return_policy_id: str
) -> Tuple[bool, Optional[str]]:
    """
    Self-heal offer if policies are missing from listingPolicies.

    Checks if offer has all three policy IDs under listingPolicies.
    If any are missing, patches the offer with corrected listingPolicies and re-verifies.

    Args:
        client: EBayClient instance
        offer_id: Offer ID to heal
        offer_data: Current offer data from GET
        payment_policy_id: Expected payment policy ID
        fulfillment_policy_id: Expected fulfillment policy ID
        return_policy_id: Expected return policy ID

    Returns:
        Tuple of (success, error_message)
        - success: True if policies are present or successfully healed
        - error_message: Error description if healing failed
    """
    # Check listingPolicies presence
    lp = offer_data.get("listingPolicies") or {}
    missing = []
    if not lp.get("paymentPolicyId"):
        missing.append("paymentPolicyId")
    if not lp.get("fulfillmentPolicyId"):
        missing.append("fulfillmentPolicyId")
    if not lp.get("returnPolicyId"):
        missing.append("returnPolicyId")

    if not missing:
        # All policies present
        logger.info(f"[Policy Self-Heal] Offer {offer_id} has all policies in listingPolicies")
        return True, None

    # Log missing policies
    logger.warning(
        f"[Policy Self-Heal] offerId={offer_id} missing={missing} → patching listingPolicies"
    )

    # Build patch payload with corrected listingPolicies
    from integrations.ebay.offer_builder import build_listing_policies
    patch_payload = build_listing_policies(
        payment_id=payment_policy_id,
        fulfillment_id=fulfillment_policy_id,
        return_id=return_policy_id
    )

    # Send PUT to update offer
    update_success, update_response, update_error = client.update_offer(offer_id, patch_payload)

    if not update_success:
        error_msg = f"Self-heal PUT failed for offer {offer_id}: {update_error}"
        logger.error(f"[Policy Self-Heal] {error_msg}")
        return False, error_msg

    logger.info(f"[Policy Self-Heal] PUT succeeded for offer {offer_id}")

    # Re-GET to verify healing
    get_success, healed_offer_data, get_error = client.get_offer(offer_id)
    if not get_success:
        error_msg = f"Self-heal re-GET failed for offer {offer_id}: {get_error}"
        logger.error(f"[Policy Self-Heal] {error_msg}")
        return False, error_msg

    # Check if policies are now present
    healed_lp = healed_offer_data.get("listingPolicies") or {}
    still_missing = []
    if not healed_lp.get("paymentPolicyId"):
        still_missing.append("paymentPolicyId")
    if not healed_lp.get("fulfillmentPolicyId"):
        still_missing.append("fulfillmentPolicyId")
    if not healed_lp.get("returnPolicyId"):
        still_missing.append("returnPolicyId")

    if still_missing:
        error_msg = f"Self-heal failed: offer {offer_id} still missing {still_missing} after PUT"
        logger.error(f"[Policy Self-Heal] {error_msg}")
        logger.error(f"[Policy Self-Heal] Healed offer listingPolicies: {healed_lp}")
        return False, error_msg

    logger.info(
        f"[Policy Self-Heal] Offer {offer_id} successfully healed, "
        f"listingPolicies keys: {sorted(healed_lp.keys())}"
    )
    return True, None


def prepublish_assertions(
    offer_json: Dict[str, Any],
    expected_marketplace_id: str,
    expected_currency: str,
    expected_price: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Pre-publish validation assertions for offer readiness.

    Validates that offer has all required fields for publishing:
    - marketplaceId matches expected
    - categoryId present
    - pricing.price.currency OR pricingSummary.price.currency matches expected
    - pricing.price.value OR pricingSummary.price.value present and normalized
    - listingPolicies.paymentPolicyId, fulfillmentPolicyId, returnPolicyId present

    Note: Quantity is NOT validated here. eBay manages quantity at the inventory item level
    (availability.shipToLocationAvailability.quantity), not in the offer. The offer links to
    the inventory item via SKU.

    DRAFT offers: Accepts offers with status DRAFT/UNPUBLISHED even if pricingSummary is missing,
    as long as pricing.price.currency/value are present.

    Args:
        offer_json: Offer JSON from GET /offer/{id}
        expected_marketplace_id: Expected marketplace ID (e.g., "EBAY_US")
        expected_currency: Expected currency code (e.g., "USD")
        expected_price: Optional expected price value (e.g., "35.00") for validation

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if all assertions pass, False otherwise
        - error_message: Error description if validation fails, None if valid
    """
    # Log offer JSON keys for debugging
    logger.info(f"[Pre-Publish Validation] Offer JSON keys: {sorted(offer_json.keys())}")
    logger.debug(f"[Pre-Publish Validation] Full offer JSON: {json.dumps(offer_json, indent=2)}")

    # Check offer status (DRAFT, UNPUBLISHED, PUBLISHED, PUBLISHING are all valid)
    offer_status = offer_json.get("status")
    is_draft = offer_status in ["DRAFT", "UNPUBLISHED"]
    logger.info(f"[Pre-Publish Validation] Offer status: {offer_status} (is_draft={is_draft})")

    # Check marketplaceId
    marketplace_id = offer_json.get("marketplaceId")
    if not marketplace_id:
        return False, "Offer missing required field: marketplaceId"
    if marketplace_id != expected_marketplace_id:
        return False, f"Offer marketplaceId mismatch: expected {expected_marketplace_id}, got {marketplace_id}"

    # NOTE: Quantity is NOT checked here. eBay manages quantity at the inventory item level (availability.shipToLocationAvailability.quantity),
    # not in the offer. The offer links to the inventory item via SKU.

    # Check categoryId
    category_id = offer_json.get("categoryId")
    if not category_id:
        return False, "Offer missing required field: categoryId"
    
    # Check currency - prioritize pricingSummary (required by eBay Sell Inventory API)
    currency = None
    pricing_summary = offer_json.get("pricingSummary")
    if pricing_summary and pricing_summary.get("price") and pricing_summary["price"].get("currency"):
        currency = pricing_summary["price"]["currency"]
    else:
        # Fallback: check pricing field (for backward compatibility with old offers)
        pricing = offer_json.get("pricing")
        if pricing and pricing.get("price") and pricing["price"].get("currency"):
            currency = pricing["price"]["currency"]
            logger.warning(
                f"[Pre-Publish Validation] Offer using deprecated 'pricing' field. "
                f"Should use 'pricingSummary' instead."
            )
    
    if not currency:
        # Save trace file for debugging
        import os
        from pathlib import Path
        from datetime import datetime
        
        trace_dir = Path("backend/logs/offer_payloads")
        trace_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        offer_id = offer_json.get("offerId", "unknown")
        trace_file = trace_dir / f"{timestamp}-{offer_id}-get.json"
        
        try:
            with open(trace_file, "w", encoding="utf-8") as f:
                json.dump(offer_json, f, indent=2, ensure_ascii=False)
            logger.error(f"[Validate] Missing currency in pricingSummary; see trace: {trace_file}")
        except Exception as e:
            logger.error(f"[Validate] Missing currency in pricingSummary; failed to save trace: {e}")
        
        return False, "Offer missing currency in pricingSummary.price.currency"
    if currency != expected_currency:
        return False, f"Offer currency mismatch: expected {expected_currency}, got {currency}"

    # Check price value - prioritize pricingSummary (required by eBay Sell Inventory API)
    price_value = None
    pricing_summary = offer_json.get("pricingSummary")
    if pricing_summary and pricing_summary.get("price") and pricing_summary["price"].get("value") is not None:
        price_value = str(pricing_summary["price"]["value"])
    else:
        # Fallback: check pricing field (for backward compatibility with old offers)
        pricing = offer_json.get("pricing")
        if pricing and pricing.get("price") and pricing["price"].get("value") is not None:
            price_value = str(pricing["price"]["value"])
            logger.warning(
                f"[Pre-Publish Validation] Offer using deprecated 'pricing' field. "
                f"Should use 'pricingSummary' instead."
            )
    
    if not price_value:
        return False, "Offer missing price value in pricingSummary.price.value"
    
    # Normalize and validate price format using numeric comparison
    # eBay may return prices as numeric (75.0) or string ("75.00")
    # Use equal_money for cents-precision comparison
    try:
        normalized_price = to_money_str(price_value)

        # Log price validation details
        logger.info(
            f"[Pre-Publish Validation] offerId={offer_json.get('offerId')} "
            f"api_value={price_value} (type={type(price_value).__name__}) "
            f"normalized={normalized_price} "
            f"equal={equal_money(price_value, normalized_price)}"
        )

        # Relaxed check: Allow numeric values like 75.0 to pass even if not "75.00" string
        if not equal_money(price_value, normalized_price):
            return False, f"Offer price value not normalized: got {price_value}, expected {normalized_price}"
    except ValueError as e:
        return False, f"Offer price value invalid: {str(e)}"

    # If expected_price provided, validate match using numeric comparison
    if expected_price:
        try:
            normalized_expected = to_money_str(expected_price)

            logger.info(
                f"[Pre-Publish Validation] Price comparison: "
                f"api_value={price_value} expected={expected_price} "
                f"normalized_api={normalized_price} normalized_expected={normalized_expected} "
                f"equal={equal_money(normalized_price, normalized_expected)}"
            )

            # Use equal_money for cents-precision comparison
            if not equal_money(normalized_price, normalized_expected):
                return False, f"Offer price mismatch: expected {normalized_expected}, got {normalized_price}"
        except ValueError as e:
            return False, f"Invalid expected_price: {str(e)}"
    
    # Check policy IDs (must be under listingPolicies)
    listing_policies = offer_json.get("listingPolicies") or {}

    payment_policy_id = listing_policies.get("paymentPolicyId")
    if not payment_policy_id:
        return False, "Offer missing required field: listingPolicies.paymentPolicyId"

    fulfillment_policy_id = listing_policies.get("fulfillmentPolicyId")
    if not fulfillment_policy_id:
        return False, "Offer missing required field: listingPolicies.fulfillmentPolicyId"

    return_policy_id = listing_policies.get("returnPolicyId")
    if not return_policy_id:
        return False, "Offer missing required field: listingPolicies.returnPolicyId"

    # Log policy IDs for debugging
    logger.info(
        f"[Offer Inspect] listingPolicies keys: {sorted(listing_policies.keys())}"
    )

    # All assertions passed
    return True, None


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
    """
    Ensure offer is publishable, with delete-and-recreate fallback for corrupted offers.
    
    Flow:
    1. GET offer
    2. Run pre-publish assertions
    3. If valid, return success
    4. If invalid due to missing currency/price, attempt delete-and-recreate
    5. Re-validate after recreate
    
    Args:
        book_id: Book ID
        offer_id: eBay offer ID
        session: Database session
        client: EBayClient instance
        expected_marketplace_id: Expected marketplace ID
        expected_currency: Expected currency code
        expected_price: Optional expected price value
        offer_payload: Full offer payload for recreate (if None, will rebuild from book)
    
    Returns:
        Tuple of (success, final_offer_id, error_message)
        - success: True if offer is publishable, False otherwise
        - final_offer_id: Offer ID to use for publish (may differ from input if recreated)
        - error_message: Error description if failed, None if succeeded
    """
    # Step 1: GET offer
    logger.info(f"[Pre-Publish] Retrieving offer {offer_id} for validation")
    get_success, offer_data, get_error = client.get_offer(offer_id)
    
    if not get_success:
        return False, None, f"Failed to retrieve offer {offer_id}: {get_error}"
    
    if not offer_data:
        return False, None, f"Offer {offer_id} returned empty data"
    
    # Step 2: Run pre-publish assertions
    is_valid, validation_error = prepublish_assertions(
        offer_json=offer_data,
        expected_marketplace_id=expected_marketplace_id,
        expected_currency=expected_currency,
        expected_price=expected_price
    )
    
    if is_valid:
        logger.info(f"[Pre-Publish] Offer {offer_id} passed all pre-publish assertions")
        return True, offer_id, None

    # Step 2a: Check if validation error is policy-related
    is_policy_error = (
        validation_error and
        "listingPolicies" in validation_error
    )

    if is_policy_error:
        # Attempt policy self-heal
        logger.warning(f"[Pre-Publish] Offer {offer_id} has policy error: {validation_error}")

        # Get policy IDs from settings
        from services.policy_settings import get_policy_settings
        policy_service = get_policy_settings(session)
        defaults = policy_service.ensure_defaults(expected_marketplace_id)

        if defaults.payment_policy_id and defaults.return_policy_id and defaults.fulfillment_policy_id:
            heal_success, heal_error = self_heal_offer_policies(
                client=client,
                offer_id=offer_id,
                offer_data=offer_data,
                payment_policy_id=defaults.payment_policy_id,
                fulfillment_policy_id=defaults.fulfillment_policy_id,
                return_policy_id=defaults.return_policy_id
            )

            if heal_success:
                # Re-GET and re-validate
                logger.info(f"[Pre-Publish] Policy self-heal succeeded, re-validating offer {offer_id}")
                get_success2, offer_data2, get_error2 = client.get_offer(offer_id)

                if get_success2:
                    is_valid2, validation_error2 = prepublish_assertions(
                        offer_json=offer_data2,
                        expected_marketplace_id=expected_marketplace_id,
                        expected_currency=expected_currency,
                        expected_price=expected_price
                    )

                    if is_valid2:
                        logger.info(f"[Pre-Publish] Offer {offer_id} passed validation after policy self-heal")
                        return True, offer_id, None
                    else:
                        logger.warning(
                            f"[Pre-Publish] Offer {offer_id} still invalid after policy self-heal: {validation_error2}"
                        )
                        # Continue to price auto-correct if applicable
                else:
                    logger.error(f"[Pre-Publish] Re-GET failed after policy self-heal: {get_error2}")
            else:
                logger.error(f"[Pre-Publish] Policy self-heal failed: {heal_error}")
        else:
            logger.error(f"[Pre-Publish] Cannot self-heal policies - missing policy defaults")

    # Step 3: Auto-correct price mismatch if validation failed due to price issue
    currency = extract_currency_from_offer(offer_data)
    price_value = extract_price_value_from_offer(offer_data)

    # Check if validation error is price-related and auto-correctable
    is_price_error = (
        validation_error and
        ("price" in validation_error.lower() or "mismatch" in validation_error.lower())
    )

    if is_price_error and expected_price and price_value:
        # Attempt auto-correct: Update offer with normalized price
        try:
            normalized_expected = to_money_str(expected_price)

            # Check if prices are actually different (use equal_money for cents precision)
            if not equal_money(price_value, normalized_expected):
                logger.warning(
                    f"[Pre-Publish Auto-Correct] Offer {offer_id} has price mismatch: "
                    f"api_value={price_value} expected={normalized_expected}. "
                    f"Attempting auto-correction via PUT offer update."
                )

                # Build minimal update payload with corrected price
                patch_payload = {
                    "pricingSummary": {
                        "price": {
                            "value": normalized_expected,
                            "currency": currency or expected_currency
                        }
                    }
                }

                # Update offer with corrected price
                logger.info(f"[Pre-Publish Auto-Correct] Sending PUT update to offer {offer_id}")
                update_success, update_response, update_error = client.update_offer(offer_id, patch_payload)

                if not update_success:
                    logger.error(
                        f"[Pre-Publish Auto-Correct] Failed to update offer {offer_id}: {update_error}"
                    )
                    return False, None, f"Pre-publish validation failed and auto-correct failed: {update_error}"

                # Re-fetch the offer to verify the update
                logger.info(f"[Pre-Publish Auto-Correct] Re-fetching offer {offer_id} to verify correction")
                get_success2, offer_data2, get_error2 = client.get_offer(offer_id)

                if not get_success2:
                    return False, None, f"Auto-correct succeeded but re-fetch failed: {get_error2}"

                # Re-validate after correction
                is_valid2, validation_error2 = prepublish_assertions(
                    offer_json=offer_data2,
                    expected_marketplace_id=expected_marketplace_id,
                    expected_currency=expected_currency,
                    expected_price=expected_price
                )

                if is_valid2:
                    logger.info(
                        f"[Pre-Publish Auto-Correct] Offer {offer_id} successfully corrected and validated"
                    )
                    return True, offer_id, None
                else:
                    logger.error(
                        f"[Pre-Publish Auto-Correct] Offer {offer_id} still invalid after correction: {validation_error2}"
                    )
                    return False, None, f"Pre-publish validation failed after auto-correct: {validation_error2}"
            else:
                # Prices are equal at cents precision but validation still failed
                # This shouldn't happen with equal_money, but log for debugging
                logger.warning(
                    f"[Pre-Publish] Offer {offer_id} price comparison passed but validation failed: {validation_error}"
                )
        except Exception as e:
            logger.error(f"[Pre-Publish Auto-Correct] Exception during auto-correct: {e}", exc_info=True)
            # Fall through to manual intervention required

    # No auto-correct for non-price errors or if auto-correct failed
    logger.warning(
        f"[Pre-Publish] Offer {offer_id} validation failed: {validation_error} "
        f"(currency={currency}, price={price_value}). "
        f"Manual intervention required."
    )

    # Return validation failure
    return False, None, f"Pre-publish validation failed: {validation_error}"


async def publish_offer(
    book_id: str,
    offer_id: str,
    session: Session
) -> Dict[str, Any]:
    """
    Publish offer to create listing.
    
    This function now includes comprehensive pre-publish validation and
    automatic recovery from corrupted offers via delete-and-recreate.
    
    Args:
        book_id: Book ID
        offer_id: eBay offer ID
        session: Database session
    
    Returns:
        Dict with:
            - success: bool
            - listing_id: eBay listing ID if published
            - response: API response data
            - error: Error message if failed
    """
    # Create eBay client
    client = EBayClient(session)
    
    # Get expected values
    marketplace_id = ebay_settings.ebay_marketplace_id
    expected_currency = MARKETPLACE_CURRENCY.get(marketplace_id)
    if not expected_currency:
        error_msg = f"No currency mapping for marketplace {marketplace_id}"
        logger.error(f"[Publish] {error_msg}")
        return {
            "success": False,
            "listing_id": None,
            "response": None,
            "error": error_msg
        }
    
    # Get expected price from book
    book = session.get(Book, book_id)
    expected_price = None
    if book and book.price_suggested is not None:
        expected_price = normalize_price(book.price_suggested)
    
    # Get offer payload for potential recreate
    offer_payload = None
    try:
        from integrations.ebay.mapping import build_offer
        from services.policy_settings import get_policy_settings

        policy_service = get_policy_settings(session)
        defaults = policy_service.ensure_defaults(marketplace_id)

        if book:
            offer_payload = build_offer(
                book=book,
                payment_policy_id=defaults.payment_policy_id,
                return_policy_id=defaults.return_policy_id,
                fulfillment_policy_id=defaults.fulfillment_policy_id
            )
    except Exception as e:
        logger.warning(f"[Publish] Could not build offer payload for recreate fallback: {e}")
    
    # Ensure offer is publishable (with delete-and-recreate fallback)
    ensure_success, final_offer_id, ensure_error = await ensure_offer_is_publishable(
        book_id=book_id,
        offer_id=offer_id,
        session=session,
        client=client,
        expected_marketplace_id=marketplace_id,
        expected_currency=expected_currency,
        expected_price=expected_price,
        offer_payload=offer_payload
    )
    
    if not ensure_success:
        return {
            "success": False,
            "listing_id": None,
            "response": None,
            "error": f"Pre-publish validation failed: {ensure_error}"
        }
    
    # Log pre-publish snapshot
    get_success, offer_data, get_error = client.get_offer(final_offer_id)
    if get_success and offer_data:
        currency = extract_currency_from_offer(offer_data)
        price_value = extract_price_value_from_offer(offer_data)
        
        logger.info(
            f"[Pre-Publish Snapshot] offerId={final_offer_id}, marketplaceId={offer_data.get('marketplaceId')}, "
            f"quantity={offer_data.get('quantity')}, "
            f"policies: payment={offer_data.get('paymentPolicyId')}, "
            f"fulfillment={offer_data.get('fulfillmentPolicyId')}, "
            f"return={offer_data.get('returnPolicyId')}, "
            f"pricing: request-like={{price.value={offer_data.get('pricing', {}).get('price', {}).get('value')}, "
            f"price.currency={offer_data.get('pricing', {}).get('price', {}).get('currency')}}}, "
            f"response-like={{pricingSummary.price.value={offer_data.get('pricingSummary', {}).get('price', {}).get('value')}, "
            f"currency={offer_data.get('pricingSummary', {}).get('price', {}).get('currency')}}}, "
            f"categoryId={offer_data.get('categoryId')}"
        )
    
    # Publish offer
    success, response_data, listing_id, error = client.publish_offer(offer_id=final_offer_id)
    
    if success:
        logger.info(f"Successfully published offer {final_offer_id} for book {book_id}, listing_id={listing_id}")
        return {
            "success": True,
            "listing_id": listing_id,
            "response": response_data,
            "error": None
        }
    else:
        logger.error(f"Failed to publish offer {final_offer_id} for book {book_id}: {error}")
        return {
            "success": False,
            "listing_id": None,
            "response": response_data,
            "error": error
        }


async def publish_book(
    book_id: str,
    session: Session,
    payment_policy_id: Optional[str] = None,
    return_policy_id: Optional[str] = None,
    fulfillment_policy_id: Optional[str] = None,
    category_id: Optional[str] = None,
    as_draft: bool = False
) -> Dict[str, Any]:
    """
    Complete publish flow: create inventory item, create offer, optionally publish offer.

    Args:
        book_id: Book ID
        session: Database session
        payment_policy_id: Payment policy ID
        return_policy_id: Return policy ID
        fulfillment_policy_id: Fulfillment policy ID
        category_id: eBay category ID (if None, uses book.ebay_category_id or auto-selects)
        as_draft: If True, creates offer but does not publish (leaves as draft)

    Returns:
        Dict with success status, offer_id, listing_id (if published), and any errors

    """
    # Step 0: Determine and store category ID
    book = session.get(Book, book_id)
    if not book:
        return {
            "success": False,
            "sku": None,
            "offer_id": None,
            "listing_id": None,
            "listing_url": None,
            "steps": {},
            "error": f"Book {book_id} not found"
        }

    # Determine category_id (priority: parameter > book.ebay_category_id > auto-select)
    if category_id is None:
        if book.ebay_category_id:
            category_id = book.ebay_category_id
            logger.info(f"Using saved category ID from book: {category_id}")
        else:
            # Import here to avoid circular dependency
            from integrations.ebay.mapping import select_category
            category_id = select_category(book)
            logger.info(f"Auto-selected category ID: {category_id}")
    else:
        logger.info(f"Using provided category ID: {category_id}")

    # Ensure policy defaults are set (auto-select if not set)
    from services.policy_settings import get_policy_settings
    from settings import ebay_settings

    marketplace_id = ebay_settings.ebay_marketplace_id

    # If policy IDs not provided, use defaults (ensure defaults exist)
    if not payment_policy_id or not return_policy_id or not fulfillment_policy_id:
        try:
            policy_service = get_policy_settings(session)
            defaults = policy_service.ensure_defaults(marketplace_id)

            # Use defaults for any missing policy IDs
            if not payment_policy_id:
                payment_policy_id = defaults.payment_policy_id
            if not return_policy_id:
                return_policy_id = defaults.return_policy_id
            if not fulfillment_policy_id:
                fulfillment_policy_id = defaults.fulfillment_policy_id

            # Validate all policies are present
            if not payment_policy_id or not return_policy_id or not fulfillment_policy_id:
                return {
                    "success": False,
                    "sku": None,
                    "offer_id": None,
                    "listing_id": None,
                    "listing_url": None,
                    "steps": {},
                    "error": "Missing policy defaults",
                    "marketplace_id": marketplace_id,
                    "action": "Call /ebay/policies/auto-select or set manually"
                }

            logger.info(
                f"[Publish] Using policies: payment={payment_policy_id}, "
                f"return={return_policy_id}, fulfillment={fulfillment_policy_id}"
            )

        except Exception as e:
            logger.error(f"[Publish] Failed to ensure policy defaults: {e}")
            return {
                "success": False,
                "sku": None,
                "offer_id": None,
                "listing_id": None,
                "listing_url": None,
                "steps": {},
                "error": f"Failed to resolve policy defaults: {str(e)}",
                "action": "Call /ebay/policies/auto-select or check eBay account connection"
            }

    # Step 1: Create or replace inventory item
    inv_result = await create_or_replace_inventory_item(
        book_id=book_id,
        session=session,
        payment_policy_id=payment_policy_id,
        return_policy_id=return_policy_id,
        fulfillment_policy_id=fulfillment_policy_id,
        category_id=category_id
    )
    
    if not inv_result["success"]:
        # Update book publish_status to failed
        book.publish_status = "failed"
        book.updated_at = int(dt.datetime.now().timestamp() * 1000)
        session.add(book)
        session.commit()

        return {
            "success": False,
            "sku": None,
            "offer_id": None,
            "listing_id": None,
            "listing_url": None,
            "steps": {
                "inventory_item": inv_result
            },
            "error": f"Inventory item creation failed: {inv_result['error']}"
        }
    
    sku = inv_result["sku"]
    
    # Step 2: Create offer
    try:
        offer_result = await create_offer(
            book_id=book_id,
            session=session,
            payment_policy_id=payment_policy_id,
            return_policy_id=return_policy_id,
            fulfillment_policy_id=fulfillment_policy_id,
            category_id=category_id
        )
    except HTTPException as e:
        # Convert HTTPException to failure result dict for consistency
        logger.error(f"Offer creation failed for book {book_id}: {e.detail}")

        # Update book publish_status to failed
        book.publish_status = "failed"
        book.updated_at = int(dt.datetime.now().timestamp() * 1000)
        session.add(book)
        session.commit()

        return {
            "success": False,
            "sku": sku,
            "offer_id": None,
            "listing_id": None,
            "listing_url": None,
            "steps": {
                "inventory_item": inv_result,
                "offer": {
                    "success": False,
                    "offer_id": None,
                    "response": None,
                    "error": e.detail
                }
            },
            "error": f"Offer creation failed: {e.detail}"
        }
    
    if not offer_result["success"]:
        # Update book publish_status to failed
        book.publish_status = "failed"
        book.updated_at = int(dt.datetime.now().timestamp() * 1000)
        session.add(book)
        session.commit()

        return {
            "success": False,
            "sku": sku,
            "offer_id": None,
            "listing_id": None,
            "listing_url": None,
            "steps": {
                "inventory_item": inv_result,
                "offer": offer_result
            },
            "error": f"Offer creation failed: {offer_result['error']}"
        }
    
    offer_id = offer_result["offer_id"]

    # Step 3: Publish offer (skip if as_draft=True)
    if as_draft:
        # Save as draft - don't publish, just return offer
        book = session.get(Book, book_id)
        if book:
            book.ebay_offer_id = offer_id
            book.ebay_category_id = category_id
            book.publish_status = "draft"
            book.updated_at = int(dt.datetime.now().timestamp() * 1000)
            session.add(book)
            session.commit()

        return {
            "success": True,
            "sku": sku,
            "offer_id": offer_id,
            "listing_id": None,
            "listing_url": None,
            "draft": True,
            "steps": {
                "inventory_item": inv_result,
                "offer": offer_result,
                "publish": {"skipped": True, "reason": "Saved as draft"}
            },
            "error": None
        }

    publish_result = await publish_offer(
        book_id=book_id,
        offer_id=offer_id,
        session=session
    )

    if not publish_result["success"]:
        # Update book publish_status to failed
        book = session.get(Book, book_id)
        if book:
            book.publish_status = "failed"
            book.updated_at = int(dt.datetime.now().timestamp() * 1000)
            session.add(book)
            session.commit()

        return {
            "success": False,
            "sku": sku,
            "offer_id": offer_id,
            "listing_id": None,
            "listing_url": None,
            "steps": {
                "inventory_item": inv_result,
                "offer": offer_result,
                "publish": publish_result
            },
            "error": f"Publish failed: {publish_result['error']}"
        }
    
    listing_id = publish_result["listing_id"]
    
    # Build listing URL (eBay format: https://www.ebay.com/itm/{listing_id})
    listing_url = None
    if listing_id:
        if ebay_settings.ebay_env == "sandbox":
            listing_url = f"https://sandbox.ebay.com/itm/{listing_id}"
        else:
            listing_url = f"https://www.ebay.com/itm/{listing_id}"
    
    # Update book with publish results
    book = session.get(Book, book_id)
    if book:
        book.sku = sku
        book.ebay_category_id = category_id
        book.ebay_offer_id = offer_id
        book.ebay_listing_id = listing_id
        book.publish_status = "published"
        book.updated_at = int(dt.datetime.now().timestamp() * 1000)
        session.add(book)
        session.commit()
        session.refresh(book)
    
    return {
        "success": True,
        "sku": sku,
        "offer_id": offer_id,
        "listing_id": listing_id,
        "listing_url": listing_url,
        "steps": {
            "inventory_item": inv_result,
            "offer": offer_result,
            "publish": publish_result
        },
        "error": None
    }

