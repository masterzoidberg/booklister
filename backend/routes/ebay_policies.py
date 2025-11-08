"""
eBay Policies Routes - Endpoints for fetching eBay business policies.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlmodel import Session
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from db import get_session
from integrations.ebay.client import EBayClient
from integrations.ebay.token_store import TokenStore, get_encryption
from services.policy_settings import get_policy_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ebay/policies", tags=["ebay-policies"])


class Policy(BaseModel):
    """Policy model."""
    policy_id: str
    name: str
    description: Optional[str] = None
    category_types: Optional[List[str]] = None
    marketplace_id: Optional[str] = None


class PoliciesResponse(BaseModel):
    """Response containing all policy types."""
    payment_policies: List[Policy] = []
    fulfillment_policies: List[Policy] = []
    return_policies: List[Policy] = []
    error: Optional[str] = None


class PolicyDefault(BaseModel):
    """Policy default (ID and/or name)."""
    id: Optional[str] = None
    name: Optional[str] = None


class PolicyDefaultsRequest(BaseModel):
    """Request to set policy defaults."""
    marketplace_id: str = "EBAY_US"
    payment_policy: Optional[PolicyDefault] = None
    return_policy: Optional[PolicyDefault] = None
    fulfillment_policy: Optional[PolicyDefault] = None


class PolicyDefaultsResponse(BaseModel):
    """Response containing saved policy defaults."""
    marketplace_id: str
    payment_policy: Optional[PolicyDefault] = None
    return_policy: Optional[PolicyDefault] = None
    fulfillment_policy: Optional[PolicyDefault] = None


def _extract_policy_info(policy_data: Dict[str, Any], policy_type: str) -> Policy:
    """Extract policy information from eBay API response."""
    # eBay API uses different field names for policy ID depending on type
    policy_id = ""
    if policy_type == "fulfillment":
        policy_id = policy_data.get("fulfillmentPolicyId", "")
    elif policy_type == "payment":
        policy_id = policy_data.get("paymentPolicyId", "")
    elif policy_type == "return":
        policy_id = policy_data.get("returnPolicyId", "")
    
    # Fallback: try to find any ID field
    if not policy_id:
        policy_id = policy_data.get("fulfillmentPolicyId") or policy_data.get("paymentPolicyId") or policy_data.get("returnPolicyId") or ""
    
    # Extract category types - eBay returns them as list of dicts with 'name' and 'default' fields
    category_types_raw = policy_data.get("categoryTypes", [])
    category_types = None
    if category_types_raw:
        if isinstance(category_types_raw, list):
            # Extract names from dict objects if they exist
            if len(category_types_raw) > 0 and isinstance(category_types_raw[0], dict):
                category_types = [item.get("name", "") for item in category_types_raw if isinstance(item, dict) and item.get("name")]
            elif len(category_types_raw) > 0 and isinstance(category_types_raw[0], str):
                # Already strings
                category_types = category_types_raw
    
    return Policy(
        policy_id=policy_id,
        name=policy_data.get("name", "Unnamed Policy"),
        description=policy_data.get("description"),
        category_types=category_types,
        marketplace_id=policy_data.get("marketplaceId")
    )


@router.get("", response_model=PoliciesResponse)
async def get_policies(
    marketplace_id: str = Query("EBAY_US", description="eBay marketplace ID"),
    session: Session = Depends(get_session)
):
    """
    Fetch all payment, fulfillment, and return policies from eBay account.
    
    Requires OAuth authentication to be set up.
    Returns policies available for the specified marketplace.
    """
    try:
        # Check if OAuth token exists
        encryption = get_encryption()
        token_store = TokenStore(session, encryption)
        token = token_store.get_valid_token("ebay")
        
        if not token:
            raise HTTPException(
                status_code=401,
                detail="No valid OAuth token. Please authenticate via /ebay/oauth/auth-url"
            )
        
        # Create eBay client
        client = EBayClient(session)
        
        # Fetch all policy types
        payment_success, payment_data, payment_error = client.get_payment_policies(marketplace_id)
        fulfillment_success, fulfillment_data, fulfillment_error = client.get_fulfillment_policies(marketplace_id)
        return_success, return_data, return_error = client.get_return_policies(marketplace_id)
        
        # Extract policies from responses
        # eBay API may return policies directly as a list or nested in a key
        payment_policies = []
        if payment_success and payment_data:
            try:
                # Try different possible response structures
                policies_list = payment_data.get("paymentPolicies", [])
                if not policies_list and isinstance(payment_data, list):
                    policies_list = payment_data
                if isinstance(policies_list, list):
                    for p in policies_list:
                        try:
                            payment_policies.append(_extract_policy_info(p, "payment"))
                        except Exception as e:
                            logger.warning(f"Failed to extract payment policy: {e}, policy_data: {p}")
            except Exception as e:
                logger.error(f"Failed to parse payment policies: {e}, response: {payment_data}")
        
        fulfillment_policies = []
        if fulfillment_success and fulfillment_data:
            try:
                policies_list = fulfillment_data.get("fulfillmentPolicies", [])
                if not policies_list and isinstance(fulfillment_data, list):
                    policies_list = fulfillment_data
                if isinstance(policies_list, list):
                    for p in policies_list:
                        try:
                            fulfillment_policies.append(_extract_policy_info(p, "fulfillment"))
                        except Exception as e:
                            logger.warning(f"Failed to extract fulfillment policy: {e}, policy_data: {p}")
            except Exception as e:
                logger.error(f"Failed to parse fulfillment policies: {e}, response: {fulfillment_data}")
        
        return_policies = []
        if return_success and return_data:
            try:
                policies_list = return_data.get("returnPolicies", [])
                if not policies_list and isinstance(return_data, list):
                    policies_list = return_data
                if isinstance(policies_list, list):
                    for p in policies_list:
                        try:
                            return_policies.append(_extract_policy_info(p, "return"))
                        except Exception as e:
                            logger.warning(f"Failed to extract return policy: {e}, policy_data: {p}")
            except Exception as e:
                logger.error(f"Failed to parse return policies: {e}, response: {return_data}")
        
        # Collect any errors
        errors = []
        if not payment_success:
            errors.append(f"Payment policies: {payment_error}")
        if not fulfillment_success:
            errors.append(f"Fulfillment policies: {fulfillment_error}")
        if not return_success:
            errors.append(f"Return policies: {return_error}")
        
        error_msg = "; ".join(errors) if errors else None
        
        return PoliciesResponse(
            payment_policies=payment_policies,
            fulfillment_policies=fulfillment_policies,
            return_policies=return_policies,
            error=error_msg
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch policies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch policies: {str(e)}")


@router.get("/defaults", response_model=PolicyDefaultsResponse)
async def get_policy_defaults(
    marketplace_id: str = Query("EBAY_US", description="eBay marketplace ID"),
    session: Session = Depends(get_session)
):
    """
    Get saved default policy selections for a marketplace.

    Returns the saved payment, return, and fulfillment policy defaults.
    Each policy includes ID and/or name if set.
    """
    try:
        policy_service = get_policy_settings(session)
        defaults = policy_service.get_defaults(marketplace_id)

        return PolicyDefaultsResponse(
            marketplace_id=marketplace_id,
            payment_policy=PolicyDefault(**defaults["payment_policy"]) if defaults["payment_policy"] else None,
            return_policy=PolicyDefault(**defaults["return_policy"]) if defaults["return_policy"] else None,
            fulfillment_policy=PolicyDefault(**defaults["fulfillment_policy"]) if defaults["fulfillment_policy"] else None
        )
    except Exception as e:
        logger.error(f"Failed to get policy defaults: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get policy defaults: {str(e)}")


@router.post("/defaults")
async def set_policy_defaults(
    request: PolicyDefaultsRequest,
    session: Session = Depends(get_session)
):
    """
    Save default policy selections for a marketplace.

    Stores the selected payment, return, and fulfillment policies.
    Each policy can include ID and/or name.
    """
    try:
        policy_service = get_policy_settings(session)

        # Convert Pydantic models to dicts
        payment_dict = request.payment_policy.dict() if request.payment_policy else None
        return_dict = request.return_policy.dict() if request.return_policy else None
        fulfillment_dict = request.fulfillment_policy.dict() if request.fulfillment_policy else None

        policy_service.set_defaults(
            marketplace_id=request.marketplace_id,
            payment_policy=payment_dict,
            return_policy=return_dict,
            fulfillment_policy=fulfillment_dict
        )

        return {
            "success": True,
            "message": f"Policy defaults saved for {request.marketplace_id}"
        }
    except Exception as e:
        logger.error(f"Failed to set policy defaults: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to set policy defaults: {str(e)}")

