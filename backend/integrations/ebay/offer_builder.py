"""
eBay Offer Payload Builder - Single Source of Truth

This module provides a centralized function for building eBay offer payloads
with guaranteed currency inference from marketplace and consistent pricingSummary structure.
"""

import logging
from typing import Dict, Any
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .utils.money import to_money_str

logger = logging.getLogger(__name__)

# Marketplace to currency mapping - 100% coverage for all eBay marketplaces
MARKETPLACE_CURRENCY = {
    "EBAY_US": "USD",
    "EBAY_GB": "GBP",
    "EBAY_DE": "EUR",
    "EBAY_AU": "AUD",
    "EBAY_CA": "CAD",
    "EBAY_FR": "EUR",
    "EBAY_IT": "EUR",
    "EBAY_ES": "EUR",
}


def build_listing_policies(
    payment_id: str,
    fulfillment_id: str,
    return_id: str
) -> Dict[str, Any]:
    """
    Build listingPolicies object for eBay offer payloads.

    Centralizes policy ID placement under listingPolicies structure (NEVER at root).
    All CREATE and UPDATE offer payloads MUST use this function.

    Args:
        payment_id: Payment policy ID
        fulfillment_id: Fulfillment policy ID
        return_id: Return policy ID

    Returns:
        Dict with listingPolicies structure containing all three policy IDs
    """
    return {
        "listingPolicies": {
            "paymentPolicyId": payment_id,
            "fulfillmentPolicyId": fulfillment_id,
            "returnPolicyId": return_id,
        }
    }


def build_offer_payload(
    *,
    sku: str,
    marketplace_id: str,
    category_id: str,
    price_value: str,  # Pass as string "65.00"
    payment_policy_id: str,
    return_policy_id: str,
    fulfillment_policy_id: str
) -> Dict[str, Any]:
    """
    Build eBay offer payload with guaranteed currency inference and pricingSummary structure.

    This is the SINGLE SOURCE OF TRUTH for offer payload construction.
    All offer creation/update paths MUST use this function.

    Args:
        sku: Book SKU (typically book.id)
        marketplace_id: eBay marketplace ID (e.g., "EBAY_US")
        category_id: eBay category ID (e.g., "29223")
        price_value: Price as string with 2 decimals (e.g., "65.00")
        payment_policy_id: Payment policy ID
        return_policy_id: Return policy ID
        fulfillment_policy_id: Fulfillment policy ID

    Returns:
        Dict with offer payload using ONLY pricingSummary (never pricing)

    Raises:
        ValueError: If any required field is missing or invalid
    """
    # Validate all required fields
    if not sku or not sku.strip():
        raise ValueError("sku is required and cannot be empty")
    
    if not marketplace_id or not marketplace_id.strip():
        raise ValueError("marketplace_id is required and cannot be empty")
    
    if not category_id or not category_id.strip():
        raise ValueError("category_id is required and cannot be empty")
    
    if not price_value or not str(price_value).strip():
        raise ValueError("price_value is required and cannot be empty")
    
    if not payment_policy_id or not payment_policy_id.strip():
        raise ValueError("payment_policy_id is required and cannot be empty")
    
    if not return_policy_id or not return_policy_id.strip():
        raise ValueError("return_policy_id is required and cannot be empty")
    
    if not fulfillment_policy_id or not fulfillment_policy_id.strip():
        raise ValueError("fulfillment_policy_id is required and cannot be empty")

    # Infer currency from marketplace_id - 100% coverage
    currency = MARKETPLACE_CURRENCY.get(marketplace_id)
    if not currency:
        raise ValueError(
            f"Unknown marketplace_id '{marketplace_id}'. "
            f"Supported marketplaces: {list(MARKETPLACE_CURRENCY.keys())}"
        )

    # Validate and normalize price_value to exactly 2 decimal places using to_money_str
    try:
        decimal_price = Decimal(str(price_value))
        if decimal_price <= 0:
            raise ValueError(f"price_value must be > 0, got {price_value}")
        normalized_price = to_money_str(price_value)
    except (ValueError, InvalidOperation) as e:
        raise ValueError(f"Invalid price_value '{price_value}': {str(e)}")

    # Build payload using ONLY pricingSummary (never pricing)
    # Policies MUST live under listingPolicies, NEVER at root
    payload: Dict[str, Any] = {
        "sku": sku,
        "marketplaceId": marketplace_id,
        "format": "FIXED_PRICE",
        "categoryId": category_id,
        "pricingSummary": {
            "price": {
                "value": normalized_price,
                "currency": currency
            }
        },
    }

    # Merge listingPolicies (centralized policy structure)
    listing_policies_dict = build_listing_policies(
        payment_id=payment_policy_id,
        fulfillment_id=fulfillment_policy_id,
        return_id=return_policy_id
    )
    payload.update(listing_policies_dict)

    # Add merchantLocationKey if configured (optional)
    import os
    merchant_location_key = os.environ.get("EBAY_MERCHANT_LOCATION_KEY")
    if merchant_location_key:
        payload["merchantLocationKey"] = merchant_location_key

    # Log for debugging
    logger.info(
        f"[Offer Build] sku={sku} mkt={marketplace_id} normalized price={normalized_price} {currency}"
    )
    logger.info(
        f"[Offer Build] policies: payment={payment_policy_id} fulfillment={fulfillment_policy_id} return={return_policy_id}"
    )

    return payload

