"""
Policy Settings Service - Manages eBay business policy defaults.

Supports storing policy selections (ID or name) per marketplace and resolving to IDs.
"""

import logging
from typing import Optional, Dict, Any, Tuple
from sqlmodel import Session
from datetime import datetime, timedelta

from models import Setting
from integrations.ebay.client import EBayClient

logger = logging.getLogger(__name__)

# Settings keys for policy defaults per marketplace
SETTINGS_KEY_POLICY_DEFAULTS = "ebay_policy_defaults"  # Nested: {marketplace_id: {payment: {id, name}, return: {id, name}, fulfillment: {id, name}}}

# Cache for resolved policies (TTL = 10 minutes)
_policy_cache: Dict[str, Tuple[Dict[str, str], datetime]] = {}
POLICY_CACHE_TTL_SECONDS = 600  # 10 minutes


class PolicySettingsService:
    """Service for managing eBay business policy defaults."""

    def __init__(self, session: Session):
        """
        Initialize policy settings service.

        Args:
            session: Database session
        """
        self.session = session
        self.client = EBayClient(session)

    def get_defaults(self, marketplace_id: str = "EBAY_US") -> Dict[str, Any]:
        """
        Get saved policy defaults for a marketplace.

        Args:
            marketplace_id: eBay marketplace ID

        Returns:
            Dict with payment_policy, return_policy, fulfillment_policy (each with id/name if set)
        """
        setting = self.session.get(Setting, SETTINGS_KEY_POLICY_DEFAULTS)
        if not setting or not setting.value:
            return {
                "payment_policy": None,
                "return_policy": None,
                "fulfillment_policy": None
            }

        # Navigate nested structure: {marketplace_id: {payment: {...}, return: {...}, fulfillment: {...}}}
        marketplace_defaults = setting.value.get(marketplace_id, {})

        return {
            "payment_policy": marketplace_defaults.get("payment"),
            "return_policy": marketplace_defaults.get("return"),
            "fulfillment_policy": marketplace_defaults.get("fulfillment")
        }

    def set_defaults(
        self,
        marketplace_id: str,
        payment_policy: Optional[Dict[str, str]] = None,
        return_policy: Optional[Dict[str, str]] = None,
        fulfillment_policy: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Save policy defaults for a marketplace.

        Args:
            marketplace_id: eBay marketplace ID
            payment_policy: Dict with 'id' and/or 'name'
            return_policy: Dict with 'id' and/or 'name'
            fulfillment_policy: Dict with 'id' and/or 'name'
        """
        # Get existing settings or create new
        setting = self.session.get(Setting, SETTINGS_KEY_POLICY_DEFAULTS)
        if not setting:
            setting = Setting(
                key=SETTINGS_KEY_POLICY_DEFAULTS,
                value={}
            )
            self.session.add(setting)

        # Ensure value is a dict
        if not isinstance(setting.value, dict):
            setting.value = {}

        # Get or create marketplace entry
        if marketplace_id not in setting.value:
            setting.value[marketplace_id] = {}

        # Update policies
        if payment_policy:
            setting.value[marketplace_id]["payment"] = payment_policy
        if return_policy:
            setting.value[marketplace_id]["return"] = return_policy
        if fulfillment_policy:
            setting.value[marketplace_id]["fulfillment"] = fulfillment_policy

        # Clear cache for this marketplace
        cache_key = f"{marketplace_id}_resolved"
        if cache_key in _policy_cache:
            del _policy_cache[cache_key]

        self.session.add(setting)
        self.session.commit()
        logger.info(f"[Policies] Saved defaults for {marketplace_id}")

    def get_resolved_ids(self, marketplace_id: str = "EBAY_US") -> Dict[str, str]:
        """
        Get resolved policy IDs (payment_policy_id, return_policy_id, fulfillment_policy_id).

        Uses cache to avoid repeated API calls. If ID is stored, uses it directly.
        If only name is stored, resolves via eBay API and caches result.

        Args:
            marketplace_id: eBay marketplace ID

        Returns:
            Dict with payment_policy_id, return_policy_id, fulfillment_policy_id (or None if not set/resolvable)
        """
        cache_key = f"{marketplace_id}_resolved"

        # Check cache
        if cache_key in _policy_cache:
            cached_ids, cached_at = _policy_cache[cache_key]
            if datetime.now() - cached_at < timedelta(seconds=POLICY_CACHE_TTL_SECONDS):
                logger.debug(f"[Policies] Cache hit for {marketplace_id}")
                return cached_ids
            else:
                logger.debug(f"[Policies] Cache expired for {marketplace_id}, refreshing")

        # Get saved defaults
        defaults = self.get_defaults(marketplace_id)
        logger.debug(
            f"[Policies] Fetched defaults for {marketplace_id}: "
            f"payment={defaults['payment_policy']}, "
            f"return={defaults['return_policy']}, "
            f"fulfillment={defaults['fulfillment_policy']}"
        )

        resolved = {
            "payment_policy_id": None,
            "return_policy_id": None,
            "fulfillment_policy_id": None
        }

        # Resolve payment policy
        if defaults["payment_policy"]:
            policy_id = defaults["payment_policy"].get("id")
            policy_name = defaults["payment_policy"].get("name")
            if policy_id:
                resolved["payment_policy_id"] = policy_id
                logger.debug(f"[Policies] Payment policy resolved from ID: {policy_id}")
            elif policy_name:
                logger.debug(f"[Policies] Payment policy resolving name '{policy_name}' to ID via API")
                resolved["payment_policy_id"] = self._resolve_policy_name_to_id(
                    "payment", policy_name, marketplace_id
                )
            else:
                logger.warning(f"[Policies] Payment policy has neither ID nor name: {defaults['payment_policy']}")
        else:
            logger.warning(f"[Policies] No payment policy saved for {marketplace_id}")

        # Resolve return policy
        if defaults["return_policy"]:
            policy_id = defaults["return_policy"].get("id")
            policy_name = defaults["return_policy"].get("name")
            if policy_id:
                resolved["return_policy_id"] = policy_id
                logger.debug(f"[Policies] Return policy resolved from ID: {policy_id}")
            elif policy_name:
                logger.debug(f"[Policies] Return policy resolving name '{policy_name}' to ID via API")
                resolved["return_policy_id"] = self._resolve_policy_name_to_id(
                    "return", policy_name, marketplace_id
                )
            else:
                logger.warning(f"[Policies] Return policy has neither ID nor name: {defaults['return_policy']}")
        else:
            logger.warning(f"[Policies] No return policy saved for {marketplace_id}")

        # Resolve fulfillment policy
        if defaults["fulfillment_policy"]:
            policy_id = defaults["fulfillment_policy"].get("id")
            policy_name = defaults["fulfillment_policy"].get("name")
            if policy_id:
                resolved["fulfillment_policy_id"] = policy_id
                logger.debug(f"[Policies] Fulfillment policy resolved from ID: {policy_id}")
            elif policy_name:
                logger.debug(f"[Policies] Fulfillment policy resolving name '{policy_name}' to ID via API")
                resolved["fulfillment_policy_id"] = self._resolve_policy_name_to_id(
                    "fulfillment", policy_name, marketplace_id
                )
            else:
                logger.warning(f"[Policies] Fulfillment policy has neither ID nor name: {defaults['fulfillment_policy']}")
        else:
            logger.warning(f"[Policies] No fulfillment policy saved for {marketplace_id}")

        # Cache result
        _policy_cache[cache_key] = (resolved, datetime.now())

        logger.info(
            f"[Policies] Resolved IDs for {marketplace_id}: "
            f"payment={resolved['payment_policy_id']}, "
            f"return={resolved['return_policy_id']}, "
            f"fulfillment={resolved['fulfillment_policy_id']}"
        )

        return resolved

    def _resolve_policy_name_to_id(
        self,
        policy_type: str,
        policy_name: str,
        marketplace_id: str
    ) -> Optional[str]:
        """
        Resolve policy name to ID by fetching from eBay API.

        Args:
            policy_type: 'payment', 'return', or 'fulfillment'
            policy_name: Policy name to resolve
            marketplace_id: eBay marketplace ID

        Returns:
            Policy ID if found, None otherwise
        """
        try:
            # Fetch policies from eBay
            if policy_type == "payment":
                success, data, error = self.client.get_payment_policies(marketplace_id)
                policies_key = "paymentPolicies"
                id_key = "paymentPolicyId"
            elif policy_type == "return":
                success, data, error = self.client.get_return_policies(marketplace_id)
                policies_key = "returnPolicies"
                id_key = "returnPolicyId"
            elif policy_type == "fulfillment":
                success, data, error = self.client.get_fulfillment_policies(marketplace_id)
                policies_key = "fulfillmentPolicies"
                id_key = "fulfillmentPolicyId"
            else:
                logger.error(f"[Policies] Invalid policy type: {policy_type}")
                return None

            if not success or not data:
                logger.error(f"[Policies] Failed to fetch {policy_type} policies: {error}")
                return None

            # Extract policies list
            policies_list = data.get(policies_key, [])
            if not policies_list and isinstance(data, list):
                policies_list = data

            # Find policy by name
            for policy in policies_list:
                if policy.get("name") == policy_name:
                    policy_id = policy.get(id_key)
                    logger.info(f"[Policies] Resolved {policy_type} policy '{policy_name}' → ID={policy_id}")
                    return policy_id

            logger.warning(f"[Policies] Could not find {policy_type} policy named '{policy_name}'")
            return None

        except Exception as e:
            logger.error(f"[Policies] Error resolving {policy_type} policy name: {e}", exc_info=True)
            return None


def get_policy_settings(session: Session) -> PolicySettingsService:
    """Get policy settings service instance."""
    return PolicySettingsService(session)
