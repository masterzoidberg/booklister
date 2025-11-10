"""
eBay API Client - Authenticated HTTP client for eBay Sell APIs.

Handles authenticated requests with automatic token refresh and retry logic.
"""

import json
import logging
import requests
import time
import uuid
from typing import Dict, Any, Optional, Tuple, List
from sqlmodel import Session

from .token_store import TokenStore, get_encryption
from .oauth import OAuthFlow
from .config import get_oauth_config
from settings import ebay_settings

logger = logging.getLogger(__name__)


class EBayClient:
    """Authenticated HTTP client for eBay Sell APIs."""
    
    def __init__(self, session: Session):
        """
        Initialize eBay client.
        
        Args:
            session: Database session for token management
        """
        self.session = session
        self.encryption = get_encryption()
        self.token_store = TokenStore(session, self.encryption)
        self.oauth_flow = OAuthFlow(config=get_oauth_config(), session=session)
        self.base_url = ebay_settings.get_api_base_url()
    
    def _get_valid_token(self) -> Optional[str]:
        """
        Get valid access token, refreshing if needed.
        
        Returns:
            Access token string or None if unavailable
        """
        token = self.token_store.get_token("ebay")
        if not token:
            logger.warning("No token found for eBay")
            return None
        
        # Check if expired (with 5 minute buffer)
        if self.token_store.is_expired(token, buffer_seconds=300):
            logger.info("Token expired or expiring soon, refreshing...")
            refresh_result = self.oauth_flow.refresh_token(token.refresh_token, self.session)
            
            if refresh_result["ok"]:
                # Get refreshed token
                refreshed_token = self.token_store.get_token("ebay")
                if refreshed_token:
                    logger.info("Token refreshed successfully")
                    return refreshed_token.access_token
                else:
                    logger.error("Token refreshed but not found in store")
                    return None
            else:
                logger.error(f"Token refresh failed: {refresh_result.get('error')}")
                return None
        
        # Token is valid
        return token.access_token
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        retry_on_auth_error: bool = True,
        max_retries: int = 1
    ) -> Tuple[Optional[Dict[str, Any]], Optional[int], Optional[str]]:
        """
        Make authenticated HTTP request to eBay API.
        
        Args:
            method: HTTP method (GET, POST, PUT, etc.)
            endpoint: API endpoint path (e.g., "/sell/inventory/v1/inventory_item/{sku}")
            data: Request body (will be JSON-encoded)
            params: Query parameters
            retry_on_auth_error: Whether to retry once on 401/403
            max_retries: Maximum number of retries on auth error
        
        Returns:
            Tuple of (response_json, status_code, error_message)
            - response_json: Parsed JSON response or None on error
            - status_code: HTTP status code
            - error_message: Error message if request failed
        """
        # Get valid token
        token = self._get_valid_token()
        if not token:
            return None, None, "No valid access token available. Please authenticate via /ebay/oauth/auth-url"
        
        # Generate request ID for logging
        request_id = str(uuid.uuid4())[:8]
        url = f"{self.base_url}{endpoint}"

        # Build headers - only include Content-Type when there's a body
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Language": "en-US",
            "Accept": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
        }

        # Add Content-Type only when sending data
        if data is not None:
            headers["Content-Type"] = "application/json"

        retries = 0
        while retries <= max_retries:
            try:
                logger.info(f"[Request {request_id}] {method} {url} (body: {'yes' if data else 'no'})")
                if data:
                    # Log full request body for debugging serialization issues
                    try:
                        request_body_json = json.dumps(data, indent=2)
                        logger.info(f"[Request {request_id}] Full request body (first 2000 chars):\n{request_body_json[:2000]}")
                        if len(request_body_json) > 2000:
                            logger.info(f"[Request {request_id}] ... (truncated, total length: {len(request_body_json)} chars)")
                    except Exception as e:
                        logger.error(f"[Request {request_id}] Failed to serialize request body to JSON: {e}")
                    
                    # Log aspects for debugging if present
                    if isinstance(data, dict) and "product" in data and "aspects" in data.get("product", {}):
                        aspects = data["product"]["aspects"]
                        logger.info(f"[Request {request_id}] Product aspects: {list(aspects.keys())}")
                        if "Author" in aspects:
                            author_val = aspects["Author"]
                            logger.info(f"[Request {request_id}] Author value: '{author_val}' (type: {type(author_val).__name__}, repr: {repr(author_val)})")
                        # Log full aspects dict for debugging serialization issues
                        try:
                            aspects_json = json.dumps(aspects, indent=2)
                            logger.info(f"[Request {request_id}] Aspects JSON:\n{aspects_json}")
                        except Exception as e:
                            logger.error(f"[Request {request_id}] Failed to serialize aspects to JSON: {e}")
                
                # Make request
                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data if data else None,
                    params=params,
                    timeout=30
                )
                
                # Log response
                logger.info(f"[Request {request_id}] Status: {response.status_code}")
                
                # Handle authentication errors with retry
                if retry_on_auth_error and response.status_code in [401, 403] and retries < max_retries:
                    logger.warning(f"[Request {request_id}] Auth error {response.status_code}, refreshing token and retrying...")
                    # Refresh token and retry
                    token = self._get_valid_token()
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                        retries += 1
                        time.sleep(0.5)  # Brief delay before retry
                        continue
                    else:
                        return None, response.status_code, f"Authentication failed and token refresh unavailable"
                
                # Parse response
                if response.status_code >= 200 and response.status_code < 300:
                    try:
                        response_json = response.json() if response.content else {}
                        logger.debug(f"[Request {request_id}] Response: {response_json}")
                        return response_json, response.status_code, None
                    except ValueError:
                        # Non-JSON response (shouldn't happen with eBay API)
                        return None, response.status_code, f"Invalid JSON response: {response.text[:200]}"
                else:
                    # Error response - log full details for debugging
                    try:
                        error_data = response.json()
                        
                        # Extract all error messages
                        errors = error_data.get("errors", [])
                        if errors:
                            error_messages = []
                            for err in errors:
                                error_id = err.get("errorId", "N/A")
                                domain = err.get("domain", "N/A")
                                subdomain = err.get("subdomain", "N/A")
                                category = err.get("category", "N/A")
                                message = err.get("message", "No message")
                                parameters = err.get("parameter", [])
                                
                                error_detail = f"Error {error_id} ({domain}/{subdomain}/{category}): {message}"
                                if parameters:
                                    error_detail += f" [Parameters: {parameters}]"
                                error_messages.append(error_detail)
                            
                            error_message = "; ".join(error_messages)
                        else:
                            error_message = error_data.get("message", response.text[:500])
                        
                        # Log full error response for debugging
                        logger.error(
                            f"[Request {request_id}] Error {response.status_code}: {error_message}\n"
                            f"Full error response: {error_data}"
                        )
                    except (ValueError, IndexError, KeyError) as e:
                        error_message = response.text[:500] if response.text else f"HTTP {response.status_code}"
                        logger.error(
                            f"[Request {request_id}] Error {response.status_code}: {error_message}\n"
                            f"Failed to parse error response: {e}, Raw response: {response.text[:500]}"
                        )
                    
                    return None, response.status_code, error_message
                    
            except requests.RequestException as e:
                logger.error(f"[Request {request_id}] Request exception: {e}")
                return None, None, f"Request failed: {str(e)}"
            except Exception as e:
                logger.error(f"[Request {request_id}] Unexpected error: {e}", exc_info=True)
                return None, None, f"Unexpected error: {str(e)}"
        
        # All retries exhausted
        return None, None, "Max retries exceeded"
    
    def create_or_replace_inventory_item(
        self,
        sku: str,
        inventory_item: Dict[str, Any]
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Create or replace inventory item.
        
        Args:
            sku: SKU identifier for the inventory item
            inventory_item: Inventory item payload
        
        Returns:
            Tuple of (success, response_data, error_message)
        """
        endpoint = f"/sell/inventory/v1/inventory_item/{sku}"
        response_json, status_code, error = self._make_request(
            method="PUT",
            endpoint=endpoint,
            data=inventory_item
        )
        
        if status_code in [200, 201, 204]:
            return True, response_json or {}, None
        else:
            return False, response_json, error
    
    def create_offer(
        self,
        offer: Dict[str, Any]
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        """
        Create offer.
        
        Args:
            offer: Offer payload
        
        Returns:
            Tuple of (success, response_data, offer_id, error_message)
        """
        endpoint = "/sell/inventory/v1/offer"
        response_json, status_code, error = self._make_request(
            method="POST",
            endpoint=endpoint,
            data=offer
        )
        
        if status_code in [200, 201]:
            offer_id = response_json.get("offerId") if response_json else None
            return True, response_json, offer_id, None
        else:
            return False, response_json, None, error
    
    def publish_offer(
        self,
        offer_id: str
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        """
        Publish offer to create listing.

        Args:
            offer_id: Offer ID from create_offer response

        Returns:
            Tuple of (success, response_data, listing_id, error_message)
        """
        endpoint = f"/sell/inventory/v1/offer/{offer_id}/publish"
        # eBay publish endpoint requires NO request body
        # Marketplace and currency are already specified in the offer payload
        logger.info(f"[Publish] Publishing offer {offer_id} (no request body)")
        response_json, status_code, error = self._make_request(
            method="POST",
            endpoint=endpoint,
            data=None  # No body required for publish endpoint
        )

        if status_code in [200, 201]:
            logger.info(f"[Publish] Offer {offer_id} published successfully, status={status_code}")
            # Extract listing ID from response
            listing_id = None
            if response_json:
                # eBay returns listingId in response
                listing_id = response_json.get("listingId")
                # Or in warnings/errors - check eBay API docs for exact format
                if not listing_id and "warnings" in response_json:
                    # Sometimes listingId is in warnings
                    warnings = response_json.get("warnings", [])
                    for warning in warnings:
                        if "listingId" in warning:
                            listing_id = warning.get("listingId")

            return True, response_json, listing_id, None
        elif status_code == 409:
            # 409 Conflict - offer already published (idempotent success)
            logger.info(f"[Publish] Offer {offer_id} already published (409 Conflict), treating as success")
            listing_id = None
            if response_json:
                listing_id = response_json.get("listingId")
                # Try to extract from error message if not in direct field
                if not listing_id and "errors" in response_json:
                    errors = response_json.get("errors", [])
                    for err in errors:
                        msg = err.get("message", "")
                        if "listing" in msg.lower() or "listingId" in err:
                            listing_id = err.get("listingId")
            return True, response_json, listing_id, None
        else:
            logger.error(f"[Publish] Offer {offer_id} publish failed, status={status_code}, error={error}")
            # Log full error JSON for debugging
            if response_json:
                logger.error(f"[Publish] Full eBay error response: {response_json}")
            return False, response_json, None, error
    
    def get_offer(self, offer_id: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Get offer details.

        Args:
            offer_id: Offer ID

        Returns:
            Tuple of (success, response_data, error_message)
        """
        endpoint = f"/sell/inventory/v1/offer/{offer_id}"
        response_json, status_code, error = self._make_request(
            method="GET",
            endpoint=endpoint
        )

        if status_code == 200:
            return True, response_json, None
        else:
            return False, response_json, error

    def get_offers_by_sku(
        self,
        sku: str,
        marketplace_id: str = "EBAY_US"
    ) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        Get all offers for a SKU in a marketplace.

        Args:
            sku: SKU identifier
            marketplace_id: eBay marketplace ID

        Returns:
            Tuple of (success, offers_list, error_message)
        """
        endpoint = "/sell/inventory/v1/offer"
        response_json, status_code, error = self._make_request(
            method="GET",
            endpoint=endpoint,
            params={"sku": sku, "marketplace_id": marketplace_id}
        )

        if status_code == 200:
            # eBay returns offers in 'offers' array
            offers = response_json.get("offers", []) if response_json else []
            logger.info(f"[Offer] Found {len(offers)} existing offer(s) for SKU={sku}, marketplace={marketplace_id}")
            return True, offers, None
        else:
            return False, None, error

    def update_offer(
        self,
        offer_id: str,
        offer: Dict[str, Any]
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Update existing offer.

        Args:
            offer_id: Offer ID to update
            offer: Offer payload

        Returns:
            Tuple of (success, response_data, error_message)
        """
        endpoint = f"/sell/inventory/v1/offer/{offer_id}"
        logger.info(f"[Offer] Updating offer {offer_id}")
        response_json, status_code, error = self._make_request(
            method="PUT",
            endpoint=endpoint,
            data=offer
        )

        if status_code in [200, 204]:
            logger.info(f"[Offer] Offer {offer_id} updated successfully")
            return True, response_json or {}, None
        else:
            logger.error(f"[Offer] Offer {offer_id} update failed: {error}")
            return False, response_json, error

    def delete_offer(
        self,
        offer_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Delete an offer.

        Args:
            offer_id: Offer ID to delete

        Returns:
            Tuple of (success, error_message)
        """
        endpoint = f"/sell/inventory/v1/offer/{offer_id}"
        logger.info(f"[Offer] Deleting offer {offer_id}")
        response_json, status_code, error = self._make_request(
            method="DELETE",
            endpoint=endpoint,
            data=None
        )

        if status_code in [200, 204]:
            logger.info(f"[Offer] Offer {offer_id} deleted successfully")
            return True, None
        else:
            logger.error(f"[Offer] Offer {offer_id} delete failed: {error}")
            return False, error

    def ensure_offer_pricing(
        self,
        offer_id: str,
        expected_currency: str,
        expected_price: Optional[str] = None
    ) -> Tuple[bool, bool, Optional[str]]:
        """
        Self-heal existing offer pricing (currency and optionally price).

        Retrieves an existing offer, checks if pricing.price.currency matches expected currency,
        and if not, updates the offer with corrected pricing.

        This is useful for recovering from malformed offers that may have been created
        with incorrect currency values that cause Error 25002 during publish.

        Args:
            offer_id: eBay offer ID
            expected_currency: Expected currency code (e.g., "USD")
            expected_price: Optional expected price value (e.g., "35.00"). If provided, will be normalized to 2 decimals.

        Returns:
            Tuple of (success, was_updated, error_message)
            - success: True if validation/update succeeded, False if failed
            - was_updated: True if offer was updated, False if no update needed
            - error_message: Error message if failed, None if succeeded
        """
        from decimal import Decimal, ROUND_HALF_UP

        # Normalize expected_price to 2 decimals if provided
        if expected_price:
            try:
                decimal_price = Decimal(str(expected_price))
                expected_price = str(decimal_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                logger.info(f"[Self-Heal] Normalized expected price to {expected_price}")
            except Exception as e:
                logger.error(f"[Self-Heal] Failed to normalize expected price '{expected_price}': {e}")
                return False, False, f"Invalid expected_price: {str(e)}"

        # Step 1: GET offer
        logger.info(f"[Self-Heal] Retrieving offer {offer_id} for currency validation")
        get_success, offer_data, get_error = self.get_offer(offer_id)

        if not get_success:
            logger.error(f"[Self-Heal] Failed to retrieve offer {offer_id}: {get_error}")
            return False, False, f"Failed to retrieve offer: {get_error}"

        if not offer_data:
            logger.error(f"[Self-Heal] Offer {offer_id} returned empty data")
            return False, False, "Offer data is empty"

        # Step 2: Check pricing (using extractors that check both pricing and pricingSummary)
        from integrations.ebay.publish import extract_currency_from_offer, extract_price_value_from_offer
        
        current_currency = extract_currency_from_offer(offer_data)
        current_price = extract_price_value_from_offer(offer_data)
        
        if not current_currency:
            logger.error(f"[Self-Heal] Offer {offer_id} missing currency in both pricing and pricingSummary")
            return False, False, "Offer missing currency in both pricing.price.currency and pricingSummary.price.currency"
        
        if not current_price:
            logger.error(f"[Self-Heal] Offer {offer_id} missing price value in both pricing and pricingSummary")
            return False, False, "Offer missing price value in both pricing.price.value and pricingSummary.price.value"

        # Normalize current_price for comparison (may have incorrect decimals)
        normalized_current_price = None
        if current_price:
            try:
                decimal_current = Decimal(str(current_price))
                normalized_current_price = str(decimal_current.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            except Exception as e:
                logger.warning(f"[Self-Heal] Could not normalize current price '{current_price}': {e}")
                normalized_current_price = current_price  # Keep as-is if can't normalize

        logger.info(
            f"[Self-Heal] Offer {offer_id} current pricing: "
            f"currency={current_currency}, price={current_price} (normalized={normalized_current_price})"
        )

        # Step 3: Determine if update needed
        needs_update = False
        update_reason = []

        if current_currency != expected_currency:
            needs_update = True
            update_reason.append(f"currency mismatch ({current_currency} → {expected_currency})")

        # Check if price needs normalization (compare normalized values)
        if normalized_current_price and normalized_current_price != current_price:
            needs_update = True
            update_reason.append(f"price format incorrect ({current_price} → {normalized_current_price})")
            # Update expected_price to the normalized current price if no specific price was requested
            if not expected_price:
                expected_price = normalized_current_price

        if expected_price and normalized_current_price != expected_price:
            needs_update = True
            update_reason.append(f"price mismatch ({normalized_current_price} → {expected_price})")

        if not needs_update:
            logger.info(f"[Self-Heal] Offer {offer_id} pricing is correct, no update needed")
            return True, False, None

        # Step 4: Update offer with corrected pricing
        logger.warning(
            f"[Self-Heal] Offer {offer_id} needs update: {', '.join(update_reason)}"
        )

        # Ensure pricing structure exists in offer_data (use request-like format)
        if "pricing" not in offer_data:
            offer_data["pricing"] = {}
        if "price" not in offer_data["pricing"]:
            offer_data["pricing"]["price"] = {}
        
        # Update the pricing in the offer data
        offer_data["pricing"]["price"]["currency"] = expected_currency
        if expected_price:
            offer_data["pricing"]["price"]["value"] = expected_price
        elif normalized_current_price:
            offer_data["pricing"]["price"]["value"] = normalized_current_price
        else:
            offer_data["pricing"]["price"]["value"] = current_price

        # PUT the updated offer
        update_success, update_data, update_error = self.update_offer(offer_id, offer_data)

        if update_success:
            logger.info(
                f"[Self-Heal] Offer {offer_id} successfully updated: "
                f"currency={expected_currency}, price={expected_price or current_price}"
            )
            return True, True, None
        else:
            logger.error(f"[Self-Heal] Failed to update offer {offer_id}: {update_error}")
            return False, False, f"Failed to update offer: {update_error}"

    def get_payment_policies(self, marketplace_id: str = "EBAY_US") -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Get payment policies for a marketplace.
        
        Args:
            marketplace_id: eBay marketplace ID (default: EBAY_US)
        
        Returns:
            Tuple of (success, response_data, error_message)
            response_data contains 'paymentPolicies' list if successful
        """
        endpoint = f"/sell/account/v1/payment_policy"
        response_json, status_code, error = self._make_request(
            method="GET",
            endpoint=endpoint,
            params={"marketplace_id": marketplace_id}
        )
        
        if status_code == 200:
            return True, response_json, None
        else:
            return False, response_json, error
    
    def get_fulfillment_policies(self, marketplace_id: str = "EBAY_US") -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Get fulfillment (shipping) policies for a marketplace.
        
        Args:
            marketplace_id: eBay marketplace ID (default: EBAY_US)
        
        Returns:
            Tuple of (success, response_data, error_message)
            response_data contains 'fulfillmentPolicies' list if successful
        """
        endpoint = f"/sell/account/v1/fulfillment_policy"
        response_json, status_code, error = self._make_request(
            method="GET",
            endpoint=endpoint,
            params={"marketplace_id": marketplace_id}
        )
        
        if status_code == 200:
            return True, response_json, None
        else:
            return False, response_json, error
    
    def get_return_policies(self, marketplace_id: str = "EBAY_US") -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Get return policies for a marketplace.
        
        Args:
            marketplace_id: eBay marketplace ID (default: EBAY_US)
        
        Returns:
            Tuple of (success, response_data, error_message)
            response_data contains 'returnPolicies' list if successful
        """
        endpoint = f"/sell/account/v1/return_policy"
        response_json, status_code, error = self._make_request(
            method="GET",
            endpoint=endpoint,
            params={"marketplace_id": marketplace_id}
        )
        
        if status_code == 200:
            return True, response_json, None
        else:
            return False, response_json, error
    
    def get_category_tree(self, marketplace_id: str = "EBAY_US") -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Get default category tree ID for a marketplace using Taxonomy API.
        
        This endpoint returns the category_tree_id that should be used in subsequent
        category tree API calls.
        
        Args:
            marketplace_id: eBay marketplace ID (default: EBAY_US)
        
        Returns:
            Tuple of (success, response_data, error_message)
            response_data contains categoryTreeId and other metadata
        """
        # eBay Taxonomy API uses different base URL
        taxonomy_base_url = "https://api.ebay.com"  # Same as main API for Taxonomy
        endpoint = f"/commerce/taxonomy/v1/get_default_category_tree_id?marketplace_id={marketplace_id}"
        
        token = self._get_valid_token()
        if not token:
            return False, None, "No valid access token available. Please authenticate via /ebay/oauth/auth-url"
        
        request_id = str(uuid.uuid4())[:8]
        url = f"{taxonomy_base_url}{endpoint}"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Content-Language": "en-US",
            "X-EBAY-SOA-REQUEST-DATA-FORMAT": "JSON",
            "X-EBAY-SOA-RESPONSE-DATA-FORMAT": "JSON"
        }
        
        try:
            logger.info(f"[Request {request_id}] GET {url}")
            response = requests.request(
                method="GET",
                url=url,
                headers=headers,
                timeout=30
            )
            
            logger.info(f"[Request {request_id}] Status: {response.status_code}")
            
            if response.status_code == 200:
                response_json = response.json() if response.content else {}
                return True, response_json, None
            else:
                try:
                    error_data = response.json()
                    error_message = error_data.get("message", response.text[:500])
                    logger.error(f"[Request {request_id}] Error {response.status_code}: {error_message}")
                except:
                    error_message = response.text[:500] if response.text else f"HTTP {response.status_code}"
                
                return False, None, error_message
        except Exception as e:
            logger.error(f"[Request {request_id}] Request exception: {e}")
            return False, None, f"Request failed: {str(e)}"
    
    def get_category_subtree(self, category_tree_id: str, category_id: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Get subtree of a specific category from category tree.
        
        Args:
            category_tree_id: Category tree ID from get_category_tree response
            category_id: Category ID to get subtree for (e.g., "267" for Books)
        
        Returns:
            Tuple of (success, response_data, error_message)
            response_data contains category subtree with leaf categories
        """
        taxonomy_base_url = "https://api.ebay.com"
        endpoint = f"/commerce/taxonomy/v1/category_tree/{category_tree_id}/get_category_subtree"
        
        token = self._get_valid_token()
        if not token:
            return False, None, "No valid access token available. Please authenticate via /ebay/oauth/auth-url"
        
        request_id = str(uuid.uuid4())[:8]
        url = f"{taxonomy_base_url}{endpoint}"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Content-Language": "en-US",
            "X-EBAY-SOA-REQUEST-DATA-FORMAT": "JSON",
            "X-EBAY-SOA-RESPONSE-DATA-FORMAT": "JSON"
        }
        
        params = {"category_id": category_id}
        
        try:
            logger.info(f"[Request {request_id}] GET {url}?category_id={category_id}")
            response = requests.request(
                method="GET",
                url=url,
                headers=headers,
                params=params,
                timeout=30
            )
            
            logger.info(f"[Request {request_id}] Status: {response.status_code}")
            
            if response.status_code == 200:
                response_json = response.json() if response.content else {}
                return True, response_json, None
            else:
                try:
                    error_data = response.json()
                    error_message = error_data.get("message", response.text[:500])
                    logger.error(f"[Request {request_id}] Error {response.status_code}: {error_message}")
                except:
                    error_message = response.text[:500] if response.text else f"HTTP {response.status_code}"
                
                return False, None, error_message
        except Exception as e:
            logger.error(f"[Request {request_id}] Request exception: {e}")
            return False, None, f"Request failed: {str(e)}"

    def get_item_aspects_for_category(self, category_tree_id: str, category_id: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Get item aspects for a category (Sell Metadata API).

        Args:
            category_tree_id: Category tree ID
            category_id: Leaf or branch category ID

        Returns:
            Tuple of (success, response_json, error_message)
        """
        taxonomy_base_url = "https://api.ebay.com"
        endpoint = f"/sell/metadata/v1/item_aspects/category/tree/{category_tree_id}/get_item_aspects_for_category"

        token = self._get_valid_token()
        if not token:
            return False, None, "No valid access token available. Please authenticate via /ebay/oauth/auth-url"

        request_id = str(uuid.uuid4())[:8]
        url = f"{taxonomy_base_url}{endpoint}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Content-Language": "en-US",
        }

        params = {"category_id": category_id}

        try:
            logger.info(f"[Request {request_id}] GET {url}?category_id={category_id}")
            response = requests.request(
                method="GET",
                url=url,
                headers=headers,
                params=params,
                timeout=30
            )

            logger.info(f"[Request {request_id}] Status: {response.status_code}")

            if response.status_code == 200:
                response_json = response.json() if response.content else {}
                return True, response_json, None
            else:
                try:
                    error_data = response.json()
                    error_message = error_data.get("message", response.text[:500])
                    logger.error(f"[Request {request_id}] Error {response.status_code}: {error_message}")
                except Exception:
                    error_message = response.text[:500] if response.text else f"HTTP {response.status_code}"
                return False, None, error_message
        except Exception as e:
            logger.error(f"[Request {request_id}] Request exception: {e}")
            return False, None, f"Request failed: {str(e)}"

