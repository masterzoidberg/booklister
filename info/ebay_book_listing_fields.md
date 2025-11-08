# eBay API Book Listing Fields Reference

## Overview

This document outlines all fields available for listing books via eBay's Inventory API. Context7's OAuth clients don't contain specific listing field documentation, but eBay's official API documentation and web search reveal comprehensive book-specific fields.

---

## Field Categories

### 1. Core Listing Fields (Required)

| Field | API Field Name | Required | Description |
|-------|----------------|----------|-------------|
| **SKU** | `sku` | ✅ Yes | Unique identifier for inventory item |
| **Title** | `product.title` | ✅ Yes | Listing title (max 80 characters) |
| **Description** | `product.description` | ✅ Yes | Detailed item description |
| **Price** | `offer.pricing.price.value` | ✅ Yes | Selling price in USD |
| **Quantity** | `offer.quantity` | ✅ Yes | Number available for sale |
| **Category ID** | `offer.categoryId` | ✅ Yes | eBay category ID (e.g., 267 for Books) |
| **Condition** | `product.condition` | ✅ Yes | Item condition (see Condition IDs below) |
| **Images** | `product.imageUrls[]` | ✅ Yes | Array of image URLs (at least 1, max 12) |

---

## 2. Product Aspects (Item Specifics) - Books

**API Structure:** `product.aspects[]`

These are book-specific fields that enhance searchability and matching. All are optional but highly recommended:

### Product Identifiers

| Field | Aspect Name | Format | Description |
|-------|-------------|--------|-------------|
| **ISBN-13** | `ISBN` | String (13 digits) | International Standard Book Number |
| **ISBN-10** | `ISBN10` | String (10 digits) | Alternative ISBN format |
| **UPC** | `UPC` | String | Universal Product Code (if available) |

### Book Metadata

| Field | Aspect Name | Format | Description |
|-------|-------------|--------|-------------|
| **Author** | `Author` | String | Book author(s) name |
| **Publisher** | `Publisher` | String | Publishing company name |
| **Publication Year** | `PublicationYear` | String/Number | Year book was published |
| **Format** | `Format` | String | Book format (Hardcover, Paperback, etc.) |
| **Language** | `Language` | String | Book language (English, Spanish, etc.) |
| **Edition** | `Edition` | String | Edition information (1st Edition, etc.) |
| **Topic/Subject** | `Topic` | String | Subject matter or topic |
| **Genre** | `Genre` | String | Literary genre (Fiction, Nonfiction, etc.) |

### Book Attributes

| Field | Aspect Name | Format | Options |
|-------|-------------|--------|---------|
| **Signed** | `Signed` | String | "Yes" or "No" |
| **Inscribed** | `Inscribed` | String | "Yes" or "No" |
| **Features** | `Features` | Array[String] | Special features (Autographed, First Edition, etc.) |

---

## 3. Offer Fields (Required for Publishing)

**API Structure:** `offer`

| Field | API Field Name | Required | Description |
|-------|----------------|----------|-------------|
| **Marketplace ID** | `marketplaceId` | ✅ Yes | "EBAY_US" for US marketplace |
| **Category ID** | `categoryId` | ✅ Yes | eBay category (267 for Books) |
| **Format** | `format` | ✅ Yes | "FIXED_PRICE" for buy-it-now listings |
| **Pricing** | `pricing` | ✅ Yes | Price and currency |
| **Quantity** | `quantity` | ✅ Yes | Available quantity |
| **Listing Policies** | `fulfillmentPolicyId` | ✅ Yes | Fulfillment/Shipping policy ID |
| | `paymentPolicyId` | ✅ Yes | Payment policy ID |
| | `returnPolicyId` | ✅ Yes | Return policy ID |

---

## 4. Condition ID Mapping

eBay uses numeric condition IDs. Mapping for your current system:

| Your Condition | eBay Condition ID | eBay Condition Name |
|----------------|-------------------|---------------------|
| Brand New | 1000 | New |
| Like New | 2750 | Like New |
| Very Good | 4000 | Very Good |
| Good | 5000 | Good |
| Acceptable | 6000 | Acceptable |

---

## 5. Additional Optional Fields

### Inventory Item Level

| Field | API Field Name | Description |
|-------|----------------|-------------|
| **Location** | `availability.shipToLocationAvailability.quantity` | Physical location (optional) |
| **Brand** | `product.brand` | Can use publisher as brand |
| **MPN** | `product.mpn` | Manufacturer Part Number (not typically used for books) |

### Offer Level

| Field | API Field Name | Description |
|-------|----------------|-------------|
| **Listing Duration** | `listingPolicies.listingDuration` | "GTC" (Good Till Canceled) or specific days |
| **Best Offer Enabled** | `pricing.price.value` + `bestOffer` | Allow buyers to make offers |
| **Buy It Now** | `format` | "FIXED_PRICE" format |

---

## Current CSV Export vs. Inventory API Mapping

Based on your current `exporter.py`:

### Currently Exported (CSV):
✅ SKU  
✅ Title  
✅ Description  
✅ CategoryID (empty currently)  
✅ ConditionID  
✅ Price  
✅ Quantity  
✅ PictureURL  
✅ ISBN  
✅ Author  
✅ BookTitle  
✅ Publisher  
✅ PublicationYear  
✅ Format  
✅ Language  
✅ Edition  
✅ Signed  
✅ Inscribed  
✅ Features  
✅ Topic  
✅ Genre  
✅ PaymentPolicyName  
✅ ShippingPolicyName  
✅ ReturnPolicyName  

### Inventory API Equivalent:

**Inventory Item (`createOrReplaceInventoryItem`):**
```json
{
  "sku": "<book.id>",
  "product": {
    "title": "<title_ai or title>",
    "description": "<description_ai>",
    "imageUrls": ["<image_url_1>", "<image_url_2>", ...],
    "aspects": {
      "ISBN": "<isbn13>",
      "Author": "<author>",
      "Publisher": "<publisher>",
      "PublicationYear": "<year>",
      "Format": "<format>",
      "Language": "<language>",
      "Edition": "<edition>",
      "Topic": "<topic>",
      "Genre": "<genre>",
      "Signed": "No",
      "Inscribed": "No"
    },
    "condition": "<condition_id>",
    "brand": "<publisher>" // Optional
  }
}
```

**Offer (`createOffer`):**
```json
{
  "sku": "<book.id>",
  "marketplaceId": "EBAY_US",
  "format": "FIXED_PRICE",
  "categoryId": "267", // Books category
  "pricing": {
    "price": {
      "value": "<price_suggested>",
      "currency": "USD"
    }
  },
  "quantity": <quantity>,
  "fulfillmentPolicyId": "<fulfillment_policy_id>",
  "paymentPolicyId": "<payment_policy_id>",
  "returnPolicyId": "<return_policy_id>"
}
```

---

## Required vs. Optional Summary

### Required for Inventory Item:
1. ✅ SKU
2. ✅ Product title
3. ✅ Product description
4. ✅ At least 1 image URL
5. ✅ Condition

### Required for Offer:
1. ✅ SKU (must match inventory item)
2. ✅ Marketplace ID ("EBAY_US")
3. ✅ Category ID (267 for Books)
4. ✅ Format ("FIXED_PRICE")
5. ✅ Price (with currency)
6. ✅ Quantity
7. ✅ Payment Policy ID
8. ✅ Return Policy ID
9. ✅ Fulfillment Policy ID

### Highly Recommended (but Optional):
- ISBN (enables catalog matching)
- Author
- Publisher
- Publication Year
- Format (Hardcover/Paperback)
- Language

### Optional Enhancement:
- Edition
- Topic/Genre
- Signed/Inscribed indicators
- Features array

---

## Field Limitations

| Field | Max Length | Notes |
|-------|------------|-------|
| Title | 80 characters | eBay enforces strict limit |
| Description | 50,000 characters | HTML supported |
| SKU | 50 characters | Alphanumeric + hyphens/underscores |
| Images | 12 URLs max | At least 1 required |
| Aspects | Varies | Each aspect has its own limits |

---

## Implementation Notes

### For BookLister AI:

**Already Available in Book Model:**
- ✅ Title (`title_ai` or `title`)
- ✅ Description (`description_ai`)
- ✅ ISBN (`isbn13`)
- ✅ Author (`author`)
- ✅ Publisher (`publisher`)
- ✅ Year (`year`)
- ✅ Format (`format`)
- ✅ Language (`language`)
- ✅ Edition (`edition`)
- ✅ Condition (`condition_grade`)
- ✅ Price (`price_suggested`)
- ✅ Quantity (`quantity`)
- ✅ Images (`images[]`)
- ✅ Specifics (`specifics_ai` - contains topic, genre, features)

**Mapping Strategy:**
1. Use `book.id` as SKU (or generate deterministic SKU)
2. Map `condition_grade` to eBay condition IDs
3. Extract aspects from `specifics_ai` dict
4. Use policy IDs from settings/env vars
5. Map images to full URLs

---

## Official eBay Documentation References

- **Inventory API:** https://developer.ebay.com/api-docs/sell/inventory/overview.html
- **Create Inventory Item:** https://developer.ebay.com/api-docs/sell/inventory/resources/inventory_item/methods/createOrReplaceInventoryItem
- **Create Offer:** https://developer.ebay.com/api-docs/sell/inventory/resources/offer/methods/createOffer
- **Product Aspects:** https://developer.ebay.com/api-docs/sell/inventory/types/slr:Product
- **Required Fields:** https://www.edp.ebay.com/api-docs/sell/static/inventory/publishing-offers.html

---

## Summary

**Context7 Status:** ✅ OAuth clients don't contain listing field details, but official eBay API documentation provides comprehensive field listings.

**Key Takeaway:** Your current CSV export fields align well with Inventory API requirements. Most fields are already captured in your Book model and can be directly mapped to Inventory API structures.

**Next Step:** Implement field mapping in `integrations/ebay/publish.py` to convert Book model data to Inventory API format.

