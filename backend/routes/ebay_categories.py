"""
eBay Categories Routes - Endpoints for fetching eBay category hierarchies.

Uses application-level OAuth (client credentials) which doesn't require
user authorization. This allows category/taxonomy queries without needing
users to connect their eBay accounts.
"""

import logging
import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel

from db import get_session
from integrations.ebay.app_auth import get_app_access_token
from settings import ebay_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ebay/categories", tags=["ebay-categories"])


def _make_taxonomy_request(
    endpoint: str,
    params: Optional[Dict[str, Any]] = None
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Make authenticated request to eBay Taxonomy API using app-level token.

    Args:
        endpoint: API endpoint path (e.g., "/commerce/taxonomy/v1/category_tree/0")
        params: Query parameters

    Returns:
        Tuple of (success, response_data, error_message)
    """
    try:
        # Get app-level access token
        logger.debug(f"[Taxonomy] Getting app-level access token...")
        access_token = get_app_access_token()
        if not access_token:
            logger.error(f"[Taxonomy] Failed to obtain app token")
            return False, None, "Failed to obtain application access token"

        logger.info(f"[Taxonomy] App token obtained (length={len(access_token)})")

        # Build full URL
        base_url = ebay_settings.get_api_base_url()
        url = f"{base_url}{endpoint}"

        # Make request
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Language": "en-US"
        }

        logger.info(f"[Taxonomy] GET {url} (params={params})")
        response = requests.get(url, headers=headers, params=params, timeout=30)
        logger.info(f"[Taxonomy] Response status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            logger.info(f"[Taxonomy] Success - response keys: {list(data.keys())}")
            return True, data, None
        else:
            error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            error_msg = error_data.get("error_description") or error_data.get("message") or response.text[:200]
            logger.error(f"[Taxonomy] API error {response.status_code}: {error_msg}")
            return False, None, f"API error {response.status_code}: {error_msg}"

    except requests.RequestException as e:
        logger.error(f"[Taxonomy] Network error: {e}", exc_info=True)
        return False, None, f"Network error: {str(e)}"
    except Exception as e:
        logger.error(f"[Taxonomy] Unexpected error: {e}", exc_info=True)
        return False, None, f"Unexpected error: {str(e)}"


class Category(BaseModel):
    """Category model."""
    category_id: str
    name: str
    level: int
    leaf_category: bool
    parent_category_id: Optional[str] = None


class CategoriesResponse(BaseModel):
    """Response containing leaf categories."""
    categories: List[Category] = []
    error: Optional[str] = None


def _extract_leaf_categories(category_node: Dict[str, Any], parent_id: Optional[str] = None, level: int = 0) -> List[Category]:
    """
    Recursively extract leaf categories from category tree.

    Args:
        category_node: Category node from eBay API response (categorySubtreeNode format)
        parent_id: Parent category ID
        level: Current level in tree

    Returns:
        List of Category objects (only leaf categories)
    """
    categories = []

    # Extract category info (nested under "category" key in API response)
    category_info = category_node.get("category", {})
    category_id = category_info.get("categoryId", "")
    category_name = category_info.get("categoryName", "")

    # Check if this is a leaf category
    leaf_category = category_node.get("leafCategoryTreeNode", False)

    # If this is a leaf category, add it
    if leaf_category and category_id:
        categories.append(Category(
            category_id=category_id,
            name=category_name,
            level=level,
            leaf_category=True,
            parent_category_id=parent_id
        ))

    # Recursively process children
    child_category_trees = category_node.get("childCategoryTreeNodes", [])
    for child in child_category_trees:
        categories.extend(_extract_leaf_categories(child, category_id, level + 1))

    return categories


@router.get("/leaf", response_model=CategoriesResponse)
async def get_leaf_categories(
    parent_category_id: str = Query("267", description="Parent category ID (default: 267 for Books)"),
    marketplace_id: str = Query("EBAY_US", description="eBay marketplace ID"),
    session: Session = Depends(get_session)
):
    """
    Fetch leaf categories under a parent category from eBay Taxonomy API.

    Uses application-level OAuth (doesn't require user authentication).
    Returns only leaf categories (categories where items can be listed).
    Defaults to Books category (267) if parent_category_id not specified.
    """
    try:
        logger.info(f"[Categories] Fetching leaf categories for parent={parent_category_id}, marketplace={marketplace_id}")

        # Step 1: Get category tree
        # Note: marketplace_id is mapped to category_tree_id (0 for US)
        category_tree_id = "0" if marketplace_id == "EBAY_US" else marketplace_id
        logger.info(f"[Categories] Using category_tree_id={category_tree_id}")

        tree_success, tree_data, tree_error = _make_taxonomy_request(
            f"/commerce/taxonomy/v1/category_tree/{category_tree_id}"
        )

        logger.info(f"[Categories] Tree request: success={tree_success}, data_keys={list(tree_data.keys()) if tree_data else None}, error={tree_error}")

        if not tree_success:
            logger.error(f"[Categories] Failed to fetch category tree: {tree_error}")
            return CategoriesResponse(
                categories=[],
                error=f"Failed to fetch category tree: {tree_error}"
            )

        # Extract category tree ID from response
        actual_tree_id = tree_data.get("categoryTreeId", category_tree_id)
        logger.info(f"[Categories] Actual tree ID from response: {actual_tree_id}")

        # Step 2: Get subtree for parent category
        subtree_success, subtree_data, subtree_error = _make_taxonomy_request(
            f"/commerce/taxonomy/v1/category_tree/{actual_tree_id}/get_category_subtree",
            params={"category_id": parent_category_id}
        )

        logger.info(f"[Categories] Subtree request: success={subtree_success}, data_keys={list(subtree_data.keys()) if subtree_data else None}, error={subtree_error}")

        if not subtree_success:
            logger.error(f"[Categories] Failed to fetch category subtree: {subtree_error}")
            return CategoriesResponse(
                categories=[],
                error=f"Failed to fetch category subtree: {subtree_error}"
            )

        # Step 3: Extract leaf categories
        # Note: API returns "categorySubtreeNode" not "rootCategoryNode"
        root_category = subtree_data.get("categorySubtreeNode", {})
        logger.info(f"[Categories] Root category node keys: {list(root_category.keys())}")

        # Extract category info (it's nested under "category" key)
        category_info = root_category.get("category", {})
        logger.info(f"[Categories] Root category: id={category_info.get('categoryId')}, name={category_info.get('categoryName')}, has_children={bool(root_category.get('childCategoryTreeNodes'))}")

        leaf_categories = _extract_leaf_categories(root_category)
        logger.info(f"[Categories] Extracted {len(leaf_categories)} leaf categories (before filtering)")

        # Step 4: Filter to only include actual book categories (exclude accessories)
        # Accessories to exclude: Book Covers, Bookmarks, Book Plates, Book Lights, Book Stands
        BOOK_ACCESSORY_IDS = {"45113", "45114", "48831", "120869", "162028"}
        filtered_categories = [
            cat for cat in leaf_categories
            if cat.category_id not in BOOK_ACCESSORY_IDS
        ]
        logger.info(f"[Categories] Filtered to {len(filtered_categories)} book categories (excluded {len(leaf_categories) - len(filtered_categories)} accessories)")

        return CategoriesResponse(
            categories=filtered_categories,
            error=None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch categories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch categories: {str(e)}")


class Aspect(BaseModel):
    """Normalized aspect model."""
    name: str
    localized_name: Optional[str] = None
    required: bool = False
    aspect_mode: Optional[str] = None  # e.g., FREE_TEXT, SELECTION_ONLY
    max_values: Optional[int] = None
    aspect_data_type: Optional[str] = None  # e.g., STRING, NUMBER
    recommended_values: Optional[List[str]] = None


class AspectsResponse(BaseModel):
    """Response containing aspects for a category."""
    category_id: str
    category_tree_id: str
    aspects: List[Aspect]
    error: Optional[str] = None


@router.get("/{category_id}/aspects", response_model=AspectsResponse)
async def get_category_aspects(
    category_id: str,
    marketplace_id: str = Query("EBAY_US", description="eBay marketplace ID"),
    session: Session = Depends(get_session)
):
    """
    Fetch item aspects for the given category using eBay Commerce Taxonomy API.

    Uses application-level OAuth (doesn't require user authentication).
    Returns all aspects (required and optional) for the specified category.
    """
    try:
        # Get category tree ID (0 for US marketplace)
        category_tree_id = "0" if marketplace_id == "EBAY_US" else marketplace_id

        # Fetch aspects using Taxonomy API
        asp_success, asp_data, asp_error = _make_taxonomy_request(
            f"/commerce/taxonomy/v1/category_tree/{category_tree_id}/get_item_aspects_for_category",
            params={"category_id": category_id}
        )

        if not asp_success or not asp_data:
            return AspectsResponse(
                category_id=category_id,
                category_tree_id=category_tree_id,
                aspects=[],
                error=f"Failed to fetch aspects: {asp_error}"
            )

        # Normalize aspects
        aspects_list: List[Aspect] = []
        for item in asp_data.get("aspects", []):
            try:
                # Extract aspect info
                aspect_constraint = item.get("aspectConstraint", {})
                aspect_required = aspect_constraint.get("aspectRequired", False)

                aspects_list.append(Aspect(
                    name=item.get("localizedAspectName") or item.get("aspectName", ""),
                    localized_name=item.get("localizedAspectName"),
                    required=bool(aspect_required),
                    aspect_mode=aspect_constraint.get("aspectMode"),
                    max_values=aspect_constraint.get("aspectMaxLength"),
                    aspect_data_type=item.get("aspectDataType"),
                    recommended_values=[
                        rv.get("value") or rv.get("localizedValue")
                        for rv in (item.get("aspectValues", []) or [])
                        if isinstance(rv, dict) and (rv.get("value") or rv.get("localizedValue"))
                    ]
                ))
            except Exception as e:
                logger.warning(f"Failed to normalize aspect: {e}; raw={item}")

        return AspectsResponse(
            category_id=category_id,
            category_tree_id=category_tree_id,
            aspects=aspects_list,
            error=None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch aspects: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch aspects: {str(e)}")

