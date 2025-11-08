# eBay API Field Mappings - Complete Reference

This document maps all book listing fields to their corresponding eBay API calls and field paths, verified through Context7 and eBay Inventory API documentation.

---

## API Calls Overview

eBay uses two main API calls for creating book listings:

1. **`createOrReplaceInventoryItem`** - Creates/updates the inventory item (product details)
2. **`createOffer`** - Creates/updates the offer (pricing, quantity, policies)

---

## Field Mappings

### Inventory Item Fields (`createOrReplaceInventoryItem`)

These fields are part of the `product` object in the inventory item payload.

#### Core Product Fields

| Your Field | API Call | API Field Path | Required | Notes |
|------------|----------|----------------|----------|-------|
| **eBay Title** (Title) | `createOrReplaceInventoryItem` | `product.title` | ✅ Yes | Max 80 characters |
| **Physical Condition** (Condition) | `createOrReplaceInventoryItem` | `product.condition` | ✅ Yes | Numeric condition ID (see Condition IDs below) |
| **Description** | `createOrReplaceInventoryItem` | `product.description` | ✅ Yes | HTML supported, max 50,000 characters |
| **Images** | `createOrReplaceInventoryItem` | `product.imageUrls[]` | ✅ Yes | Array of HTTPS URLs (1-12 images) |

#### Product Aspects (Item Specifics)

All aspects are optional but highly recommended for better searchability and matching. These go in `product.aspects{}`:

| Your Field | API Call | API Field Path | Type | Notes |
|------------|----------|----------------|------|-------|
| **Author** | `createOrReplaceInventoryItem` | `product.aspects.Author` | String | Book author(s) name |
| **Book Title** (Title/Book Title) | `createOrReplaceInventoryItem` | `product.aspects.Book Title` | String | Original book title (separate from listing title) |
| **Language** | `createOrReplaceInventoryItem` | `product.aspects.Language` | String | e.g., "English", "Spanish" |
| **ISBN-13** | `createOrReplaceInventoryItem` | `product.aspects.ISBN` | String | 13-digit ISBN (preferred) |
| **ISBN-10** | `createOrReplaceInventoryItem` | `product.aspects.ISBN10` | String | 10-digit ISBN (alternative) |
| **Country/Region of Manufacture** | `createOrReplaceInventoryItem` | `product.aspects.Country/Region of Manufacture` | String | Country where book was manufactured |
| **Edition** | `createOrReplaceInventoryItem` | `product.aspects.Edition` | String | e.g., "1st Edition", "2nd Edition" |
| **Narrative Type** | `createOrReplaceInventoryItem` | `product.aspects.Narrative Type` | String | e.g., "Fiction", "Non-fiction" |
| **Signed** (Yes/No) | `createOrReplaceInventoryItem` | `product.aspects.Signed` | String | "Yes" or "No" |
| **Signed By** | `createOrReplaceInventoryItem` | `product.aspects.Signed By` | String | Name of person who signed the book |
| **Vintage** | `createOrReplaceInventoryItem` | `product.aspects.Vintage` | String | Year or date indicating vintage status |
| **Ex Libris** (Yes/No) | `createOrReplaceInventoryItem` | `product.aspects.Ex Libris` | String | "Yes" or "No" |
| **Inscribed** (Yes/No) | `createOrReplaceInventoryItem` | `product.aspects.Inscribed` | String | "Yes" or "No" |
| **Intended Audience** | `createOrReplaceInventoryItem` | `product.aspects.Intended Audience` | String | e.g., "Adult", "Children", "Young Adult" |
| **Format** | `createOrReplaceInventoryItem` | `product.aspects.Format` | String | e.g., "Hardcover", "Paperback", "eBook" |
| **Genre** | `createOrReplaceInventoryItem` | `product.aspects.Genre` | String | Literary genre (e.g., "Mystery", "Romance") |
| **Publication Year** (Year/Publication Date) | `createOrReplaceInventoryItem` | `product.aspects.Publication Year` | String | Year of publication (e.g., "2020") |
| **Publisher** | `createOrReplaceInventoryItem` | `product.aspects.Publisher` | String | Publishing company name |
| **Topic** (Subject) | `createOrReplaceInventoryItem` | `product.aspects.Topic` | String | Subject matter or topic |
| **Type** | `createOrReplaceInventoryItem` | `product.aspects.Type` | String | Book type classification |
| **Era** | `createOrReplaceInventoryItem` | `product.aspects.Era` | String | Historical era or period |
| **Illustrator** | `createOrReplaceInventoryItem` | `product.aspects.Illustrator` | String | Illustrator name |
| **Literary Movement** | `createOrReplaceInventoryItem` | `product.aspects.Literary Movement` | String | Literary movement (e.g., "Romanticism", "Modernism") |
| **Book Series** (Series Title) | `createOrReplaceInventoryItem` | `product.aspects.Book Series` | String | Series name if part of a series |
| **Features** | `createOrReplaceInventoryItem` | `product.aspects.Features` | Array[String] | Multiple values (e.g., ["First Edition", "Dust Jacket", "Illustrated"]) |

#### Additional Product Fields

| Your Field | API Call | API Field Path | Required | Notes |
|------------|----------|----------------|----------|-------|
| **Publisher** (as Brand) | `createOrReplaceInventoryItem` | `product.brand` | ❌ Optional | Can use publisher as brand |

---

### Offer Fields (`createOffer`)

These fields are part of the offer payload (separate from inventory item).

| Your Field | API Call | API Field Path | Required | Notes |
|------------|----------|----------------|----------|-------|
| **Starting Price** (Start Price/StartPrice) | `createOffer` | `pricing.price.value` | ✅ Yes | Starting/selling price |
| **Currency** | `createOffer` | `pricing.price.currency` | ✅ Yes | Typically "USD" |
| **Quantity** | `createOffer` | `quantity` | ✅ Yes | Number available for sale |
| **Category ID** | `createOffer` | `categoryId` | ✅ Yes | eBay category ID (267 for Books) |
| **Marketplace ID** | `createOffer` | `marketplaceId` | ✅ Yes | "EBAY_US" for US marketplace |
| **Format** | `createOffer` | `format` | ✅ Yes | "FIXED_PRICE" for buy-it-now |
| **Floor Price** (Reserve Price/Minimum Price) | `createOffer` | `pricing.minimumAdvertisedPrice.value` | ❌ Optional | Minimum acceptable price |
| **Payment Policy ID** | `createOffer` | `paymentPolicyId` | ✅ Yes | Required policy ID |
| **Return Policy ID** | `createOffer` | `returnPolicyId` | ✅ Yes | Required policy ID |
| **Fulfillment Policy ID** | `createOffer` | `fulfillmentPolicyId` | ✅ Yes | Required policy ID (shipping) |

---

## Condition ID Mapping

Physical Condition maps to numeric IDs in `product.condition`:

| Your Condition | eBay Condition ID | eBay Condition Name |
|----------------|-------------------|---------------------|
| Brand New | `1000` | New |
| Like New | `2750` | Like New |
| Very Good | `4000` | Very Good |
| Good | `5000` | Good |
| Acceptable | `6000` | Acceptable |

---

## Complete API Payload Structure

### Inventory Item Payload (`createOrReplaceInventoryItem`)

```json
{
  "sku": "<book_id>",
  "product": {
    "title": "<eBay Title>",
    "description": "<Description>",
    "imageUrls": ["<image_url_1>", "<image_url_2>", ...],
    "condition": "<condition_id>",
    "brand": "<Publisher>",
    "aspects": {
      "Author": "<Author>",
      "Book Title": "<Book Title>",
      "Language": "<Language>",
      "ISBN": "<ISBN-13>",
      "ISBN10": "<ISBN-10>",
      "Country/Region of Manufacture": "<Country/Region>",
      "Edition": "<Edition>",
      "Narrative Type": "<Narrative Type>",
      "Signed": "<Yes/No>",
      "Signed By": "<Signed By>",
      "Vintage": "<Vintage>",
      "Ex Libris": "<Yes/No>",
      "Inscribed": "<Yes/No>",
      "Intended Audience": "<Intended Audience>",
      "Format": "<Format>",
      "Genre": "<Genre>",
      "Publication Year": "<Publication Year>",
      "Publisher": "<Publisher>",
      "Topic": "<Topic>",
      "Type": "<Type>",
      "Era": "<Era>",
      "Illustrator": "<Illustrator>",
      "Literary Movement": "<Literary Movement>",
      "Book Series": "<Book Series>",
      "Features": ["<Feature1>", "<Feature2>", ...]
    }
  }
}
```

### Offer Payload (`createOffer`)

```json
{
  "sku": "<book_id>",
  "marketplaceId": "EBAY_US",
  "format": "FIXED_PRICE",
  "categoryId": "267",
  "pricing": {
    "price": {
      "value": "<Starting Price>",
      "currency": "USD"
    },
    "minimumAdvertisedPrice": {
      "value": "<Floor Price>",
      "currency": "USD"
    }
  },
  "quantity": <quantity>,
  "paymentPolicyId": "<payment_policy_id>",
  "returnPolicyId": "<return_policy_id>",
  "fulfillmentPolicyId": "<fulfillment_policy_id>"
}
```

---

## Field Requirements Summary

### Required for Inventory Item (`createOrReplaceInventoryItem`):
1. ✅ `sku` - Unique identifier
2. ✅ `product.title` - Listing title (max 80 chars)
3. ✅ `product.description` - Item description
4. ✅ `product.imageUrls[]` - At least 1 image URL (HTTPS)
5. ✅ `product.condition` - Condition ID

### Required for Offer (`createOffer`):
1. ✅ `sku` - Must match inventory item SKU
2. ✅ `marketplaceId` - "EBAY_US"
3. ✅ `format` - "FIXED_PRICE"
4. ✅ `categoryId` - "267" for Books
5. ✅ `pricing.price.value` - Starting price
6. ✅ `pricing.price.currency` - "USD"
7. ✅ `quantity` - >= 1
8. ✅ `paymentPolicyId` - Payment policy
9. ✅ `returnPolicyId` - Return policy
10. ✅ `fulfillmentPolicyId` - Fulfillment/shipping policy

### Highly Recommended (Optional but Important):
- All aspects for better searchability and catalog matching
- ISBN (especially ISBN-13) for catalog matching
- Author, Publisher, Publication Year for discoverability

---

## Implementation Notes

### Current Implementation Status

Based on `backend/integrations/ebay/mapping.py`:

**Currently Implemented:**
- ✅ Title (`product.title`)
- ✅ Description (`product.description`)
- ✅ Images (`product.imageUrls[]`)
- ✅ Condition (`product.condition`)
- ✅ ISBN (`product.aspects.ISBN`)
- ✅ Author (`product.aspects.Author`)
- ✅ Publisher (`product.aspects.Publisher` and `product.brand`)
- ✅ Publication Year (`product.aspects.PublicationYear`)
- ✅ Format (`product.aspects.Format`)
- ✅ Language (`product.aspects.Language`)
- ✅ Edition (`product.aspects.Edition`)
- ✅ Topic (`product.aspects.Topic`)
- ✅ Genre (`product.aspects.Genre`)
- ✅ Signed (`product.aspects.Signed`)
- ✅ Inscribed (`product.aspects.Inscribed`)
- ✅ Features (`product.aspects.Features` - array)
- ✅ Starting Price (`pricing.price.value`)
- ✅ Quantity (`quantity`)

**Not Yet Implemented (Available in API):**
- ⚠️ Book Title (`product.aspects.Book Title`) - separate from listing title
- ⚠️ ISBN-10 (`product.aspects.ISBN10`)
- ⚠️ Country/Region of Manufacture (`product.aspects.Country/Region of Manufacture`)
- ⚠️ Narrative Type (`product.aspects.Narrative Type`)
- ⚠️ Signed By (`product.aspects.Signed By`)
- ⚠️ Vintage (`product.aspects.Vintage`)
- ⚠️ Ex Libris (`product.aspects.Ex Libris`)
- ⚠️ Intended Audience (`product.aspects.Intended Audience`)
- ⚠️ Type (`product.aspects.Type`)
- ⚠️ Era (`product.aspects.Era`)
- ⚠️ Illustrator (`product.aspects.Illustrator`)
- ⚠️ Literary Movement (`product.aspects.Literary Movement`)
- ⚠️ Book Series (`product.aspects.Book Series`)
- ⚠️ Floor Price (`pricing.minimumAdvertisedPrice.value`)

---

## References

- **eBay Inventory API Documentation:** https://developer.ebay.com/api-docs/sell/inventory/overview.html
- **Create Inventory Item:** https://developer.ebay.com/api-docs/sell/inventory/resources/inventory_item/methods/createOrReplaceInventoryItem
- **Create Offer:** https://developer.ebay.com/api-docs/sell/inventory/resources/offer/methods/createOffer
- **Product Aspects:** https://developer.ebay.com/api-docs/sell/inventory/types/slr:Product
- **Current Implementation:** `backend/integrations/ebay/mapping.py`

---

## Summary

All requested fields are supported by eBay's Inventory API. Most map to `product.aspects{}` in the `createOrReplaceInventoryItem` call, while pricing fields (Starting Price, Floor Price) map to the `createOffer` call's `pricing` object.

The current implementation covers most commonly used fields, with additional fields available for future enhancement if needed.

