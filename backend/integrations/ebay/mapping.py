"""
eBay Mapping Service - Converts Book objects to eBay API payloads.

This module provides deterministic mapping from Book (OCR + AI-enriched) models
to eBay Inventory API format for createOrReplaceInventoryItem and createOffer.
"""

import os
import re
import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from models import Book, ConditionGrade

logger = logging.getLogger(__name__)


# Condition grade to eBay Condition ID mapping
# From info/ebay_book_listing_fields.md lines 84-91
CONDITION_MAPPING: Dict[str, str] = {
    ConditionGrade.BRAND_NEW.value: "1000",      # New
    ConditionGrade.LIKE_NEW.value: "2750",      # Like New
    ConditionGrade.VERY_GOOD.value: "4000",      # Very Good
    ConditionGrade.GOOD.value: "5000",           # Good
    ConditionGrade.ACCEPTABLE.value: "6000"      # Acceptable
}

# eBay constants
EBAY_MARKETPLACE_ID = "EBAY_US"
EBAY_BOOKS_CATEGORY_ID = "267"  # Parent category (not used for listing)
EBAY_NONFICTION_CATEGORY_ID = "29223"  # Nonfiction - leaf category
EBAY_CHILDRENS_BOOKS_CATEGORY_ID = "29792"  # Children's Books - leaf category
EBAY_CURRENCY = "USD"
EBAY_FORMAT = "FIXED_PRICE"
EBAY_TITLE_MAX_LENGTH = 80


def get_ebay_category_id(book_type: Optional[str]) -> str:
    """
    Map book type to eBay category ID.
    
    Args:
        book_type: One of "nonfiction", "fiction", "childrens", or None
    
    Returns:
        eBay category ID string
        
    Notes:
        - Nonfiction books use Nonfiction category (29223)
        - Fiction books use Children's Books category (29792) - has Genre, Narrative Type aspects
        - Children's books use Children's Books category (29792)
        - If None, defaults to Nonfiction (29223)
    """
    if book_type == "nonfiction":
        return EBAY_NONFICTION_CATEGORY_ID
    elif book_type in ("fiction", "childrens"):
        return EBAY_CHILDRENS_BOOKS_CATEGORY_ID
    else:
        # Default to Nonfiction if not specified
        return EBAY_NONFICTION_CATEGORY_ID


def _is_aspect_valid_for_category(aspect_name: str, category_id: str) -> bool:
    """
    Check if an aspect is valid for the given category.
    
    Args:
        aspect_name: Name of the aspect (e.g., "Genre", "Binding")
        category_id: eBay category ID (e.g., "29223", "29792")
    
    Returns:
        True if aspect is valid for the category, False otherwise
    """
    if category_id == EBAY_NONFICTION_CATEGORY_ID:
        # Nonfiction: exclude Children's Books only aspects
        return aspect_name not in CHILDRENS_BOOKS_ONLY_ASPECTS
    elif category_id == EBAY_CHILDRENS_BOOKS_CATEGORY_ID:
        # Children's Books: exclude Nonfiction only aspects
        return aspect_name not in NONFICTION_ONLY_ASPECTS
    else:
        # Unknown category - allow all aspects (fallback)
        logger.warning(f"Unknown category ID: {category_id}, allowing all aspects")
        return True


class MappingResult:
    """Container for mapping result with sidecar metadata."""
    def __init__(
        self,
        inventory_item: Dict[str, Any],
        offer: Dict[str, Any],
        title_length: int,
        title_truncated: bool
    ):
        self.inventory_item = inventory_item
        self.offer = offer
        self.title_length = title_length
        self.title_truncated = title_truncated


def select_category(book: Book) -> str:
    """
    Select the appropriate eBay category for a book.
    
    Determines whether a book should be listed in Nonfiction (29223) or 
    Children's Books (29792) based on book properties.
    
    Args:
        book: Book model instance
        
    Returns:
        Category ID string ("29223" for Nonfiction, "29792" for Children's Books)
    """
    specifics = book.specifics_ai or {}
    
    # Check intended_audience field for children's book indicators
    intended_audience = specifics.get("intended_audience", [])
    if isinstance(intended_audience, str):
        # If it's a string, try to parse it as a list or check for keywords
        intended_audience = [intended_audience.lower()]
    elif isinstance(intended_audience, list):
        intended_audience = [str(item).lower() for item in intended_audience if item]
    else:
        intended_audience = []
    
    # Check for children/young adult indicators in intended audience
    children_keywords = [
        "children", "child", "young adult", "ya", "juvenile", 
        "teen", "teenager", "kids", "toddler", "preschool"
    ]
    
    for audience in intended_audience:
        if any(keyword in audience for keyword in children_keywords):
            logger.info(f"Book {book.id} classified as Children's Books based on intended_audience: {audience}")
            return EBAY_CHILDRENS_BOOKS_CATEGORY_ID
    
    # Check genre field for children's book indicators
    genre_value = specifics.get("genre", [])
    if isinstance(genre_value, str):
        genre_value = [genre_value.lower()]
    elif isinstance(genre_value, list):
        genre_value = [str(item).lower() for item in genre_value if item]
    else:
        genre_value = []
    
    children_genre_keywords = [
        "children's", "childrens", "picture book", "young adult", 
        "juvenile", "middle grade", "board book"
    ]
    
    for genre in genre_value:
        if any(keyword in genre for keyword in children_genre_keywords):
            logger.info(f"Book {book.id} classified as Children's Books based on genre: {genre}")
            return EBAY_CHILDRENS_BOOKS_CATEGORY_ID
    
    # Default to Nonfiction if no children's book indicators found
    logger.info(f"Book {book.id} classified as Nonfiction (default)")
    return EBAY_NONFICTION_CATEGORY_ID


# Category-specific aspect mappings
# Aspects available in Children's Books (29792) but NOT in Nonfiction (29223)
CHILDRENS_BOOKS_ONLY_ASPECTS = {
    "Genre",
    "Narrative Type",
    "Intended Audience"
}

# Aspects available in Nonfiction (29223) but NOT in Children's Books (29792)
NONFICTION_ONLY_ASPECTS = {
    "Binding",
    "Subject",
    "Place of Publication"
}

# Required aspects for Children's Books (29792)
CHILDRENS_BOOKS_REQUIRED_ASPECTS = {
    "Author",
    "Language",
    "Book Title"
}


def build_inventory_item(
    book: Book,
    image_urls: Optional[List[str]] = None,
    base_url: str = "http://127.0.0.1:8000",
    category_id: Optional[str] = None
) -> Tuple[Dict[str, Any], int, bool]:
    """
    Build eBay Inventory Item payload from Book model.
    
    Args:
        book: Book model instance
        image_urls: Pre-resolved image URLs (e.g., EPS URLs from Media API).
                    If None, builds URLs from book.images using base_url.
        base_url: Base URL for constructing image URLs (used only if image_urls is None)
        
    Returns:
        Tuple of (inventory_item_dict, title_length, title_truncated)
        
    Raises:
        ValueError: If required fields are missing
    """
    # Build title (prefer title_ai, fallback to title)
    title = book.title_ai or book.title or ""
    title_truncated = False
    
    # Enforce 80 character limit
    if len(title) > EBAY_TITLE_MAX_LENGTH:
        title = _truncate_title(title)
        title_truncated = True
    
    title_length = len(title)
    
    # Build description (required)
    description = book.description_ai or ""
    
    # Build image URLs (required, at least 1, max 12)
    if image_urls is None:
        image_urls = _build_image_urls(book, base_url)
    
    if not image_urls:
        raise ValueError("Book must have at least one image")
    
    # Limit to 12 images as per eBay spec
    if len(image_urls) > 12:
        image_urls = image_urls[:12]
    
    # Map condition (required)
    condition_id = CONDITION_MAPPING.get(book.condition_grade.value, CONDITION_MAPPING[ConditionGrade.GOOD.value])
    
    # Select category if not provided
    if category_id is None:
        # Check if book has a saved category ID
        if book.ebay_category_id:
            category_id = book.ebay_category_id
            logger.info(f"Using saved category ID from book: {category_id}")
        else:
            category_id = select_category(book)
            logger.info(f"Auto-selected category ID: {category_id}")
    
    # Build aspects (item specifics) - category-specific and filtered
    aspects = _build_aspects(book, category_id)
    
    # Aspects are now properly formatted as arrays (required by eBay API)
    # Re-enabled after fixing aspect format issue
    _skip_all_aspects = False  # Set to True to skip all aspects for testing
    
    # Build product dict
    product: Dict[str, Any] = {
        "title": title,
        "description": description,
        "imageUrls": image_urls,
        "condition": condition_id
    }
    
    # Only add aspects if not skipped
    if not _skip_all_aspects and aspects:
        product["aspects"] = aspects
        logger.info(f"Added {len(aspects)} aspects to product")
        # Detailed logging of aspect names and values before API call
        logger.info(f"[Aspect Details] Book {book.id} - Aspect names being sent: {sorted(aspects.keys())}")
        for aspect_name, aspect_value in sorted(aspects.items()):
            value_preview = str(aspect_value)[:100] if aspect_value else "None"
            logger.info(f"[Aspect Details]   '{aspect_name}': {type(aspect_value).__name__} = {value_preview}")
    elif _skip_all_aspects:
        logger.warning(f"All aspects temporarily disabled for debugging. Would have added {len(aspects)} aspects: {list(aspects.keys())}")
    
    # Log aspects for debugging (only if there are any)
    if aspects:
        logger.debug(f"Built aspects for book {book.id}: {list(aspects.keys())}")
    
    # Add brand (publisher) if available
    if book.publisher:
        product["brand"] = book.publisher

    # Build availability with quantity
    # eBay requires quantity in the inventory item's availability field
    availability: Dict[str, Any] = {
        "shipToLocationAvailability": {
            "quantity": book.quantity if book.quantity is not None else 1
        }
    }

    # Build packageWeightAndSize (required for shipping)
    weight_lbs = getattr(book, "weight_lbs", None)
    if not weight_lbs or weight_lbs <= 0:
        weight_lbs = 1.0  # Default: 1 lb for books

    package_weight_and_size: Dict[str, Any] = {
        "weight": {
            "value": f"{weight_lbs:.2f}",
            "unit": "POUND"
        },
        "dimensions": {
            "length": str(getattr(book, "dim_length", 9)),
            "width": str(getattr(book, "dim_width", 6)),
            "height": str(getattr(book, "dim_height", 2)),
            "unit": "INCH"
        }
    }

    # Build inventory item payload
    inventory_item: Dict[str, Any] = {
        "sku": book.id,
        "product": product,
        "availability": availability,
        "packageWeightAndSize": package_weight_and_size
    }

    logger.info(f"[Inventory] Built inventory item for book {book.id}: quantity={book.quantity}, weight={weight_lbs:.2f} lbs")

    return inventory_item, title_length, title_truncated


def build_offer(
    book: Book,
    payment_policy_id: Optional[str] = None,
    return_policy_id: Optional[str] = None,
    fulfillment_policy_id: Optional[str] = None,
    category_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Build eBay Offer payload from Book model and policy IDs.
    
    Args:
        book: Book model instance
        payment_policy_id: Payment policy ID from settings/env
        return_policy_id: Return policy ID from settings/env
        fulfillment_policy_id: Fulfillment policy ID from settings/env
        
    Returns:
        eBay offer payload dict
        
    Raises:
        ValueError: If required fields (price, quantity, policy IDs) are missing
    """
    # Validate required fields
    if book.price_suggested is None:
        raise ValueError("Book must have price_suggested")
    
    if book.quantity is None or book.quantity < 1:
        raise ValueError("Book must have quantity >= 1")
    
    if not payment_policy_id:
        raise ValueError("payment_policy_id is required")
    
    if not return_policy_id:
        raise ValueError("return_policy_id is required")
    
    if not fulfillment_policy_id:
        raise ValueError("fulfillment_policy_id is required")
    
    # Select category if not provided
    if category_id is None:
        # Check if book has a saved category ID
        if book.ebay_category_id:
            category_id = book.ebay_category_id
            logger.info(f"Using saved category ID from book: {category_id}")
        else:
            category_id = select_category(book)
            logger.info(f"Auto-selected category ID: {category_id}")
    
    # Build pricing with currency validation and 2-decimal normalization
    from decimal import Decimal, ROUND_HALF_UP

    currency = EBAY_CURRENCY
    if not currency:
        raise ValueError("Currency is required for offer creation (EBAY_CURRENCY must be set)")

    # Normalize price to exactly 2 decimal places (e.g., 35.0 -> "35.00")
    try:
        decimal_price = Decimal(str(book.price_suggested))
        normalized_price = str(decimal_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except Exception as e:
        raise ValueError(f"Invalid price value {book.price_suggested}: {str(e)}")

    pricing: Dict[str, Any] = {
        "price": {
            "value": normalized_price,
            "currency": currency
        }
    }

    # Log offer details for debugging
    logger.info(
        f"[Offer] Building offer for book {book.id}: "
        f"currency={currency}, price={normalized_price} (original={book.price_suggested}), category={category_id}"
    )

    # Build offer payload
    # NOTE: quantity is NOT included in offer - it goes in the inventory item's availability field
    offer: Dict[str, Any] = {
        "sku": book.id,
        "marketplaceId": EBAY_MARKETPLACE_ID,
        "format": EBAY_FORMAT,
        "categoryId": category_id,
        "pricing": pricing,
        "fulfillmentPolicyId": fulfillment_policy_id,
        "paymentPolicyId": payment_policy_id,
        "returnPolicyId": return_policy_id
    }

    return offer


def build_mapping_result(
    book: Book,
    image_urls: Optional[List[str]] = None,
    base_url: str = "http://127.0.0.1:8000",
    payment_policy_id: Optional[str] = None,
    return_policy_id: Optional[str] = None,
    fulfillment_policy_id: Optional[str] = None,
    category_id: Optional[str] = None
) -> MappingResult:
    """
    Build both inventory item and offer, returning result with metadata.
    
    Args:
        book: Book model instance
        image_urls: Pre-resolved image URLs (e.g., EPS URLs from Media API).
                    If None, builds URLs from book.images using base_url.
        base_url: Base URL for image URLs (used only if image_urls is None)
        payment_policy_id: Payment policy ID
        return_policy_id: Return policy ID
        fulfillment_policy_id: Fulfillment policy ID
        category_id: eBay category ID (if None, will be determined from book.book_type)
        
    Returns:
        MappingResult with inventory_item, offer, and metadata
    """
    # Determine category once and reuse for both inventory item and offer
    if category_id is None:
        category_id = get_ebay_category_id(book.book_type)
    
    inventory_item, title_length, title_truncated = build_inventory_item(book, image_urls, base_url, category_id)
    offer = build_offer(book, payment_policy_id, return_policy_id, fulfillment_policy_id, category_id)
    
    return MappingResult(inventory_item, offer, title_length, title_truncated)


def _build_image_urls(book: Book, base_url: str) -> List[str]:
    """Build list of image URLs from book images."""
    if not book.images:
        return []
    
    urls = []
    for img in book.images:
        # Extract filename from path
        # Path format: data/images/{book_id}/{filename} or just filename
        path = img.path
        if '/' in path:
            filename = path.split('/')[-1]
        else:
            filename = path
        
        url = f"{base_url}/images/{book.id}/{filename}"
        urls.append(url)
    
    return urls


def _normalize_aspect_value(value: Any) -> Optional[str]:
    """
    Normalize aspect value to a valid string.
    
    Args:
        value: Value to normalize (string, list, None, etc.)
    
    Returns:
        Normalized string value or None if invalid
    """
    if value is None:
        return None
    
    # Handle string values
    if isinstance(value, str):
        normalized = value.strip()
        # Remove all control characters (except space, tab, newline, carriage return)
        # Control characters are 0x00-0x1F except 0x09 (tab), 0x0A (newline), 0x0D (carriage return)
        # Remove all control characters (0x00-0x1F) except tab (0x09), newline (0x0A), CR (0x0D)
        normalized = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', normalized)
        # Normalize whitespace (including newlines/tabs) to single spaces
        normalized = " ".join(normalized.split())
        # Ensure it's not empty after cleaning
        if not normalized:
            return None
        # Ensure it's JSON-serializable (no invalid UTF-8 sequences)
        try:
            normalized.encode('utf-8').decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError):
            # If encoding fails, try to fix it
            normalized = normalized.encode('utf-8', errors='ignore').decode('utf-8')
        return normalized if normalized else None
    
    # Handle list values - join with comma (eBay accepts comma-separated strings for some fields)
    if isinstance(value, list):
        # Filter empty values and convert to strings
        valid_items = [str(item).strip() for item in value if item and str(item).strip()]
        if not valid_items:
            return None
        # Join with comma for multi-value aspects
        return ", ".join(valid_items)
    
    # Handle dict/object - skip (not valid for string aspects)
    if isinstance(value, dict):
        return None
    
    # Handle other types - convert to string
    try:
        normalized = str(value).strip()
        # Remove control characters and normalize whitespace
        normalized = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', normalized)
        normalized = " ".join(normalized.split())
        # Ensure UTF-8 encoding is valid
        try:
            normalized.encode('utf-8').decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError):
            normalized = normalized.encode('utf-8', errors='ignore').decode('utf-8')
        return normalized if normalized else None
    except Exception:
        return None


def _normalize_aspect_array(value: Any) -> Optional[List[str]]:
    """
    Normalize aspect value to a valid array of strings.
    
    Args:
        value: Value to normalize
    
    Returns:
        List of normalized strings or None if invalid
    """
    if value is None:
        return None
    
    # Handle list values
    if isinstance(value, list):
        valid_items = [str(item).strip() for item in value if item and str(item).strip()]
        return valid_items if valid_items else None
    
    # Handle string values - split by comma if needed
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        # Split by comma and clean up
        items = [item.strip() for item in normalized.split(",") if item.strip()]
        return items if items else None
    
    # Handle other types - convert to single-item list
    normalized = str(value).strip()
    return [normalized] if normalized else None


def _build_aspects(book: Book, category_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Build product aspects (item specifics) from book fields.
    
    Maps non-empty values from book model and specifics_ai to eBay aspect names.
    All values are normalized and validated before inclusion.
    Filters aspects based on category_id to only include valid aspects for that category.
    
    Args:
        book: Book model instance
        category_id: eBay category ID (e.g., "29223" for Nonfiction, "29792" for Children's Books).
                     If None, determines category automatically.
    
    Returns:
        Dict of aspect name -> aspect value (will be converted to arrays in cleanup)
    """
    # Select category if not provided
    if category_id is None:
        # Check if book has a saved category ID
        if book.ebay_category_id:
            category_id = book.ebay_category_id
            logger.info(f"Using saved category ID from book: {category_id}")
        else:
            category_id = select_category(book)
            logger.info(f"Auto-selected category ID: {category_id}")
    
    # Determine if this is Children's Books or Nonfiction
    is_childrens_books = category_id == EBAY_CHILDRENS_BOOKS_CATEGORY_ID
    is_nonfiction = category_id == EBAY_NONFICTION_CATEGORY_ID
    
    aspects: Dict[str, Any] = {}
    
    # Extract from specifics_ai first (so we can check both sources)
    specifics = book.specifics_ai or {}
    
    # Product identifiers
    if book.isbn13:
        isbn_value = _normalize_aspect_value(book.isbn13)
        if isbn_value:
            aspects["ISBN"] = isbn_value
    
    # Book metadata - single string values
    # Check both book.author and specifics_ai for author (prefer specifics_ai if available)
    author_source = None
    if specifics.get("author"):
        author_source = specifics.get("author")
    elif book.author:
        author_source = book.author
    
    # Author field re-enabled - aspect values are now properly formatted as arrays
    if author_source:
        try:
            author_value = _normalize_aspect_value(author_source)
            if author_value and isinstance(author_value, str) and len(author_value) > 0:
                # Additional validation: ensure it's JSON-serializable and not too long
                # eBay typically accepts up to 65 characters for Author
                # Test JSON serialization before adding
                try:
                    json.dumps(author_value)
                except (TypeError, ValueError) as json_err:
                    logger.error(f"Author value is not JSON-serializable: {json_err}, value='{author_value}' (repr: {repr(author_value)})")
                    author_value = None
                
                if author_value and len(author_value) <= 65:
                    aspects["Author"] = author_value
                    logger.info(f"Author aspect value: '{author_value}' (type: {type(author_value).__name__}, length: {len(author_value)}, repr: {repr(author_value)})")
                elif author_value and len(author_value) > 65:
                    logger.warning(f"Author value too long ({len(author_value)} chars), truncating to 65")
                    aspects["Author"] = author_value[:65].rstrip()
                    logger.info(f"Author aspect value (truncated): '{aspects['Author']}'")
            else:
                logger.warning(f"Author value failed normalization: source={author_source}, type={type(author_source).__name__}, normalized={author_value}")
        except Exception as e:
            logger.error(f"Error normalizing Author value: {e}, source={author_source}, type={type(author_source).__name__}", exc_info=True)
    else:
        logger.debug("No author value found in book.author or specifics_ai")
    
    # NOTE: Publisher field may be causing serialization issues with ampersand (&) character
    # Example: "Congdon & Lattes, Inc." - eBay may have issues with ampersands in aspect values
    if book.publisher:
        publisher_value = _normalize_aspect_value(book.publisher)
        if publisher_value:
            # Try replacing ampersand with "and" to avoid potential serialization issues
            # eBay may have issues with & character in aspect values
            if "&" in publisher_value:
                logger.warning(f"Publisher contains ampersand: '{publisher_value}' - replacing with 'and' to avoid serialization issues")
                # Replace & with "and" - eBay may have issues with & character in aspect values
                publisher_value = publisher_value.replace("&", "and")
            aspects["Publisher"] = publisher_value
    
    if book.year:
        year_value = _normalize_aspect_value(book.year)
        if year_value:
            aspects["Publication Year"] = year_value
    
    if book.language:
        language_value = _normalize_aspect_value(book.language)
        if language_value:
            aspects["Language"] = language_value
    
    if book.edition:
        edition_value = _normalize_aspect_value(book.edition)
        if edition_value:
            aspects["Edition"] = edition_value
    
    # Format - can be array or string
    if book.format:
        format_value = _normalize_aspect_value(book.format)
        if format_value:
            aspects["Format"] = format_value
    
    # Format from specifics_ai (array) - override if present
    format_from_specifics = specifics.get("format")
    if format_from_specifics:
        format_array = _normalize_aspect_array(format_from_specifics)
        if format_array:
            aspects["Format"] = format_array if len(format_array) > 1 else format_array[0]
    
    # Topic - available in both categories (split comma-joined strings into arrays)
    topic_value = specifics.get("topic")
    if topic_value:
        if isinstance(topic_value, str) and "," in topic_value:
            # Split comma-separated string into array
            topic_list = [t.strip() for t in topic_value.split(",") if t.strip()]
            aspects["Topic"] = topic_list
        elif isinstance(topic_value, list):
            aspects["Topic"] = [str(t).strip() for t in topic_value if t and str(t).strip()]
        else:
            normalized = _normalize_aspect_value(topic_value)
            if normalized:
                aspects["Topic"] = [normalized]
    
    # Genre - ONLY available in Children's Books (29792)
    if is_childrens_books:
        genre_value = specifics.get("genre")
        if genre_value:
            genre_array = _normalize_aspect_array(genre_value)
            if genre_array:
                aspects["Genre"] = genre_array if len(genre_array) > 1 else genre_array[0]
    
    # Intended Audience - ONLY available in Children's Books (29792)
    if is_childrens_books:
        intended_audience = specifics.get("intended_audience")
        if intended_audience:
            audience_array = _normalize_aspect_array(intended_audience)
            if audience_array:
                aspects["Intended Audience"] = audience_array if len(audience_array) > 1 else audience_array[0]
    
    # Narrative Type - ONLY available in Children's Books (29792)
    if is_childrens_books:
        if specifics.get("narrative_type"):
            narrative_value = _normalize_aspect_value(specifics.get("narrative_type"))
            if narrative_value:
                aspects["Narrative Type"] = narrative_value
    
    # Additional fields from specifics_ai
    if specifics.get("book_title"):
        book_title_value = _normalize_aspect_value(specifics.get("book_title"))
        if book_title_value:
            aspects["Book Title"] = book_title_value
    
    # REMOVED: ISBN10 aspect - eBay only accepts "ISBN" aspect name (not "ISBN10")
    # If ISBN-10 value is available, it should be included in the same "ISBN" aspect
    # or handled separately via eBay's ISBN validation logic
    # if specifics.get("isbn10"):
    #     isbn10_value = _normalize_aspect_value(specifics.get("isbn10"))
    #     if isbn10_value:
    #         aspects["ISBN"] = isbn10_value  # Use "ISBN" not "ISBN10"
    
    # Binding - ONLY available in Nonfiction (29223)
    if is_nonfiction:
        # Map from format field if it contains binding information
        format_value = specifics.get("format") or book.format
        if format_value:
            format_str = str(format_value).lower()
            if "hardcover" in format_str or "hardback" in format_str:
                aspects["Binding"] = "Hardcover"
            elif "paperback" in format_str or "softcover" in format_str:
                aspects["Binding"] = "Paperback"
    
    # Subject - ONLY available in Nonfiction (29223)
    # Map from topic or genre
    if is_nonfiction:
        subject_value = _normalize_aspect_value(specifics.get("topic") or (specifics.get("genre")[0] if specifics.get("genre") and isinstance(specifics.get("genre"), list) else None))
        if subject_value:
            aspects["Subject"] = subject_value
    
    # Place of Publication - ONLY available in Nonfiction (29223)
    if is_nonfiction:
        # Map from country_of_manufacture if available
        country_value = _normalize_aspect_value(specifics.get("country_of_manufacture"))
        if country_value:
            aspects["Place of Publication"] = country_value
    
    # NEEDS VERIFICATION: Country/Region of Manufacture
    # Verify exact aspect name via eBay Taxonomy API - may need to be "Country of Manufacture"
    # Temporarily disabled to avoid Error 25001 until verified
    # if specifics.get("country_of_manufacture"):
    #     country_value = _normalize_aspect_value(specifics.get("country_of_manufacture"))
    #     if country_value:
    #         aspects["Country/Region of Manufacture"] = country_value
    #         # Or try: aspects["Country of Manufacture"] = country_value
    
    if specifics.get("signed_by"):
        signed_by_value = _normalize_aspect_value(specifics.get("signed_by"))
        if signed_by_value:
            aspects["Signed By"] = signed_by_value
    
    # RE-ENABLED: Type - confirmed valid for Books category
    if specifics.get("type"):
        type_value = _normalize_aspect_value(specifics.get("type"))
        if type_value:
            aspects["Type"] = type_value
    
    # NEEDS VERIFICATION: Era - verify if valid for Books category via Taxonomy API
    # Temporarily disabled to avoid Error 25001 until verified
    # if specifics.get("era"):
    #     era_value = _normalize_aspect_value(specifics.get("era"))
    #     if era_value:
    #         aspects["Era"] = era_value
    
    if specifics.get("illustrator"):
        illustrator_value = _normalize_aspect_value(specifics.get("illustrator"))
        if illustrator_value:
            aspects["Illustrator"] = illustrator_value
    
    if specifics.get("literary_movement"):
        movement_value = _normalize_aspect_value(specifics.get("literary_movement"))
        if movement_value:
            aspects["Literary Movement"] = movement_value
    
    if specifics.get("book_series"):
        series_value = _normalize_aspect_value(specifics.get("book_series"))
        if series_value:
            aspects["Book Series"] = series_value
    
    # RE-ENABLED: Confirmed valid aspects for Books category (ID 267)
    # Inscribed - confirmed valid for Books category
    if specifics.get("inscribed") is not None:
        aspects["Inscribed"] = "Yes" if specifics.get("inscribed") else "No"
    else:
        aspects["Inscribed"] = "No"
    
    # Vintage - confirmed valid for Books category (likely valid)
    if specifics.get("vintage") is not None:
        aspects["Vintage"] = "Yes" if specifics.get("vintage") else "No"
    
    # Features - confirmed valid for Books category (array)
    features = specifics.get("features", [])
    if features:
        features_array = _normalize_aspect_array(features)
        if features_array:
            aspects["Features"] = features_array
    
    # Signed - re-enabled after verification
    if specifics.get("signed") is not None:
        aspects["Signed"] = "Yes" if specifics.get("signed") else "No"
    else:
        aspects["Signed"] = "No"
    
    # NEEDS CASE/SPELLING VERIFICATION: Ex Libris
    # May need to be "Ex-Libris" or "Ex-Library" - test with API
    # Keeping as "Ex Libris" for now, but verify exact spelling via Taxonomy API
    if specifics.get("ex_libris") is not None:
        aspects["Ex Libris"] = "Yes" if specifics.get("ex_libris") else "No"
    
        
    # Filter aspects based on category - remove aspects not valid for this category
    filtered_aspects = {}
    for key, value in aspects.items():
        # Skip if aspect is not valid for this category
        if is_nonfiction and key in CHILDRENS_BOOKS_ONLY_ASPECTS:
            logger.debug(f"Skipping aspect '{key}' - not valid for Nonfiction category")
            continue
        if is_childrens_books and key in NONFICTION_ONLY_ASPECTS:
            logger.debug(f"Skipping aspect '{key}' - not valid for Children's Books category")
            continue
        filtered_aspects[key] = value
    
    # Ensure required aspects for Children's Books are present
    if is_childrens_books:
        missing_required = []
        if "Author" not in filtered_aspects:
            author_source = specifics.get("author") or book.author
            if author_source:
                author_value = _normalize_aspect_value(author_source)
                if author_value and len(author_value) <= 65:
                    filtered_aspects["Author"] = author_value
                else:
                    missing_required.append("Author")
            else:
                missing_required.append("Author")
        if "Language" not in filtered_aspects:
            if book.language:
                language_value = _normalize_aspect_value(book.language)
                if language_value:
                    filtered_aspects["Language"] = language_value
                else:
                    missing_required.append("Language")
            else:
                missing_required.append("Language")
        if "Book Title" not in filtered_aspects:
            book_title_source = specifics.get("book_title") or book.title_ai or book.title
            if book_title_source:
                book_title_value = _normalize_aspect_value(book_title_source)
                if book_title_value:
                    filtered_aspects["Book Title"] = book_title_value
                else:
                    missing_required.append("Book Title")
            else:
                missing_required.append("Book Title")
        if missing_required:
            logger.warning(f"Book {book.id} is missing required aspects for Children's Books category: {missing_required}")
    
    # Final cleanup: remove any None values or empty strings/arrays that might have slipped through
    # Also ensure all values are JSON-serializable
    # IMPORTANT: eBay requires ALL aspect values to be arrays, even single values
    # Convert strings to single-element arrays, keep arrays as-is
    cleaned_aspects = {}
    for key, value in filtered_aspects.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, list) and len(value) == 0:
            continue
        if isinstance(value, list) and all(not str(v).strip() for v in value):
            continue
        
        # eBay requires aspect values to be arrays - convert strings to arrays
        if isinstance(value, str):
            # Convert string to single-element array
            value = [value]
        elif isinstance(value, list):
            # Already an array, keep as-is
            pass
        else:
            # Other types - convert to string then array
            value = [str(value)]
        
        # Test JSON serialization - skip if not serializable
        try:
            json.dumps(value)
            cleaned_aspects[key] = value
        except (TypeError, ValueError) as e:
            logger.warning(f"Skipping aspect '{key}' - not JSON-serializable: {e}, value={repr(value)}")
    
    # Enhanced logging for Error 25001 debugging - show exact aspect names being sent
    logger.info(f"[Aspect Validation] Built {len(cleaned_aspects)} aspects for category ID {category_id}")
    logger.info(f"[Aspect Validation] Aspect names (sorted): {sorted(cleaned_aspects.keys())}")
    
    # Log each aspect name and value type for verification
    for aspect_name in sorted(cleaned_aspects.keys()):
        aspect_value = cleaned_aspects[aspect_name]
        value_type = type(aspect_value).__name__
        if isinstance(aspect_value, list):
            value_preview = f"list[{len(aspect_value)} items] = {aspect_value[:3]}" if len(aspect_value) > 3 else f"list = {aspect_value}"
        else:
            value_preview = str(aspect_value)[:50] if aspect_value else "None"
        logger.info(f"[Aspect Validation]   '{aspect_name}': {value_type} = {value_preview}")
    
    # Log Author aspect specifically if present
    if "Author" in cleaned_aspects:
        logger.info(f"[Aspect Validation] Author aspect in final payload: '{cleaned_aspects['Author']}' (type: {type(cleaned_aspects['Author']).__name__})")
    else:
        logger.info("[Aspect Validation] Author aspect NOT in final payload")
    
    logger.info(f"Built {len(cleaned_aspects)} aspects for category {category_id}: {list(cleaned_aspects.keys())}")
    return cleaned_aspects


def _truncate_title(title: str) -> str:
    """
    Truncate title to 80 characters with clean truncation rule.
    
    Truncates at word boundary if possible, otherwise at character limit.
    """
    if len(title) <= EBAY_TITLE_MAX_LENGTH:
        return title
    
    # Try to truncate at word boundary
    truncated = title[:EBAY_TITLE_MAX_LENGTH]
    last_space = truncated.rfind(' ')
    
    if last_space > EBAY_TITLE_MAX_LENGTH * 0.7:  # If space is reasonably close to end
        return truncated[:last_space].rstrip()
    
    # Otherwise just truncate at character limit
    return truncated.rstrip()

