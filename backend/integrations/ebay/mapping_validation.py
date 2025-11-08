"""
eBay Mapping Validation - Validates inventory item and offer payloads.

This module validates that mapped payloads contain all required fields
and meet eBay API requirements.
"""

from typing import List, Dict, Any

# eBay constants
EBAY_TITLE_MAX_LENGTH = 80


def validate_required_fields(inv: Dict[str, Any], offer: Dict[str, Any]) -> List[str]:
    """
    Validate inventory item and offer payloads for required fields.
    
    Args:
        inv: Inventory item payload dict
        offer: Offer payload dict
        
    Returns:
        List of error messages (empty if valid)
    """
    errors: List[str] = []
    
    # Validate inventory item
    errors.extend(_validate_inventory_item(inv))
    
    # Validate offer
    errors.extend(_validate_offer(offer))
    
    # Cross-validate (e.g., SKU must match)
    if inv.get("sku") and offer.get("sku"):
        if inv["sku"] != offer["sku"]:
            errors.append("Inventory item SKU and offer SKU must match")
    
    return errors


def _validate_inventory_item(inv: Dict[str, Any]) -> List[str]:
    """Validate inventory item payload."""
    errors: List[str] = []
    
    # Check SKU
    if not inv.get("sku"):
        errors.append("Inventory item missing required field: sku")
    
    # Check product
    product = inv.get("product")
    if not product:
        errors.append("Inventory item missing required field: product")
        return errors  # Can't validate further without product
    
    # Check title
    title = product.get("title")
    if not title:
        errors.append("Inventory item missing required field: product.title")
    else:
        if len(title) > EBAY_TITLE_MAX_LENGTH:
            errors.append(f"Product title exceeds {EBAY_TITLE_MAX_LENGTH} characters (found {len(title)})")
    
    # Check description
    if not product.get("description"):
        errors.append("Inventory item missing required field: product.description")
    
    # Check images (at least 1 required, max 12)
    image_urls = product.get("imageUrls", [])
    if not image_urls:
        errors.append("Inventory item missing required field: product.imageUrls (at least 1 image required)")
    else:
        if len(image_urls) > 12:
            errors.append(f"Product has too many images (max 12, found {len(image_urls)})")
    
    # Check condition
    if not product.get("condition"):
        errors.append("Inventory item missing required field: product.condition")
    
    # Check aspects (optional but warn if completely empty)
    # Note: We don't error on missing aspects as they're optional
    
    return errors


def _validate_offer(offer: Dict[str, Any]) -> List[str]:
    """Validate offer payload."""
    errors: List[str] = []
    
    # Check SKU
    if not offer.get("sku"):
        errors.append("Offer missing required field: sku")
    
    # Check marketplace ID
    if offer.get("marketplaceId") != "EBAY_US":
        errors.append("Offer must have marketplaceId: EBAY_US")
    
    # Check format
    if offer.get("format") != "FIXED_PRICE":
        errors.append("Offer must have format: FIXED_PRICE")
    
    # Check category ID
    if offer.get("categoryId") != "267":
        errors.append("Offer must have categoryId: 267 (Books)")
    
    # Check pricing
    pricing = offer.get("pricing")
    if not pricing:
        errors.append("Offer missing required field: pricing")
    else:
        price = pricing.get("price")
        if not price:
            errors.append("Offer missing required field: pricing.price")
        else:
            if not price.get("value"):
                errors.append("Offer missing required field: pricing.price.value")
            if price.get("currency") != "USD":
                errors.append("Offer pricing.price.currency must be: USD")
    
    # Check quantity
    quantity = offer.get("quantity")
    if quantity is None:
        errors.append("Offer missing required field: quantity")
    elif not isinstance(quantity, int) or quantity < 1:
        errors.append("Offer quantity must be >= 1")
    
    # Check policy IDs
    if not offer.get("fulfillmentPolicyId"):
        errors.append("Offer missing required field: fulfillmentPolicyId")
    
    if not offer.get("paymentPolicyId"):
        errors.append("Offer missing required field: paymentPolicyId")
    
    if not offer.get("returnPolicyId"):
        errors.append("Offer missing required field: returnPolicyId")
    
    return errors


def validate_title_length(title: str) -> tuple[int, bool]:
    """
    Validate title length and return character count and truncation flag.
    
    Args:
        title: Title string to validate
        
    Returns:
        Tuple of (character_count, is_truncated)
    """
    length = len(title)
    truncated = length > EBAY_TITLE_MAX_LENGTH
    return length, truncated

