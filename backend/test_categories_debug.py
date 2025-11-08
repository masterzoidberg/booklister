"""
Debug script to test eBay Taxonomy API and category fetching.
Run: python test_categories_debug.py
"""
import sys
import logging
from integrations.ebay.app_auth import get_app_access_token
from integrations.ebay.config import get_oauth_config
from settings import ebay_settings
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)

def test_oauth():
    """Test OAuth client credentials flow."""
    print("\n=== Testing OAuth Client Credentials ===")
    print(f"Client ID: {ebay_settings.ebay_client_id[:20]}...")
    print(f"Environment: {ebay_settings.ebay_env}")
    print(f"OAuth Base: {ebay_settings.get_oauth_base_url()}")
    print(f"API Base: {ebay_settings.get_api_base_url()}")

    token = get_app_access_token()
    if token:
        print(f"[OK] OAuth token obtained (length={len(token)})")
        print(f"   Token preview: {token[:30]}...")
        return token
    else:
        print("[FAIL] Failed to obtain OAuth token")
        return None

def test_category_tree(token):
    """Test category tree endpoint."""
    print("\n=== Testing Category Tree API ===")
    url = f"{ebay_settings.get_api_base_url()}/commerce/taxonomy/v1/category_tree/0"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Language": "en-US"
    }

    print(f"GET {url}")
    response = requests.get(url, headers=headers, timeout=30)
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"[OK] Category tree fetched")
        print(f"   Tree ID: {data.get('categoryTreeId')}")
        print(f"   Version: {data.get('categoryTreeVersion')}")
        return data.get('categoryTreeId')
    else:
        print(f"[FAIL] Failed: {response.text[:200]}")
        return None

def test_category_subtree(token, tree_id, category_id="267"):
    """Test category subtree endpoint."""
    print(f"\n=== Testing Category Subtree API (category_id={category_id}) ===")
    url = f"{ebay_settings.get_api_base_url()}/commerce/taxonomy/v1/category_tree/{tree_id}/get_category_subtree"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Language": "en-US"
    }
    params = {"category_id": category_id}

    print(f"GET {url}")
    print(f"Params: {params}")
    response = requests.get(url, headers=headers, params=params, timeout=30)
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"[OK] Subtree fetched")
        print(f"   Raw response keys: {list(data.keys())}")
        print(f"   Raw response (first 500 chars): {str(data)[:500]}")

        # API returns "categorySubtreeNode" not "rootCategoryNode"
        root = data.get('categorySubtreeNode', {})
        category_info = root.get('category', {})
        print(f"   Root ID: {category_info.get('categoryId')}")
        print(f"   Root Name: {category_info.get('categoryName')}")
        print(f"   Is Leaf: {root.get('leafCategoryTreeNode')}")
        children = root.get('childCategoryTreeNodes', [])
        print(f"   Children count: {len(children)}")

        # Count leaf categories
        def count_leaves(node, depth=0):
            indent = "  " * depth
            is_leaf = node.get('leafCategoryTreeNode', False)
            category_info = node.get('category', {})
            cat_id = category_info.get('categoryId', 'N/A')
            cat_name = category_info.get('categoryName', 'N/A')

            if is_leaf:
                print(f"   {indent}[LEAF] {cat_id}: {cat_name}")
                return 1

            total = 0
            for child in node.get('childCategoryTreeNodes', []):
                total += count_leaves(child, depth + 1)
            return total

        leaf_count = count_leaves(root)
        print(f"\n   Total leaf categories: {leaf_count}")

        # Filter out accessories (same as backend)
        BOOK_ACCESSORY_IDS = {"45113", "45114", "48831", "120869", "162028"}
        print(f"\n   Excluding {len(BOOK_ACCESSORY_IDS)} accessory categories:")
        for acc_id in BOOK_ACCESSORY_IDS:
            print(f"     - {acc_id} (accessory)")

        filtered_count = leaf_count - len([x for x in BOOK_ACCESSORY_IDS if x in ["45113", "45114", "48831", "120869", "162028"]])
        print(f"\n   Final book categories count: {filtered_count}")

        return leaf_count
    else:
        print(f"[FAIL] Failed: {response.text[:200]}")
        return 0

def main():
    """Run all tests."""
    print("=" * 60)
    print("eBay Taxonomy API Debug Test")
    print("=" * 60)

    # Test 1: OAuth
    token = test_oauth()
    if not token:
        print("\n[FAIL] Cannot proceed without OAuth token")
        return 1

    # Test 2: Category Tree
    tree_id = test_category_tree(token)
    if not tree_id:
        print("\n[FAIL] Cannot proceed without category tree ID")
        return 1

    # Test 3: Category Subtree (Books category 267)
    leaf_count = test_category_subtree(token, tree_id, "267")

    print("\n" + "=" * 60)
    if leaf_count > 0:
        print(f"[SUCCESS] Found {leaf_count} leaf categories under Books (267)")
        print("=" * 60)
        return 0
    else:
        print("[FAILED] No leaf categories found")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
