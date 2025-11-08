# eBay API Integration - Setup Checklist

## What We Have ✅

- ✅ eBay Developer account created
- ✅ Client ID: `your_ebay_client_id` (stored in `info/api_info.md`)
- ✅ Client Secret: `your_ebay_client_secret` (stored in `info/api_info.md`)
- ✅ Dev ID: `67ff1ea2-05bf-42df-ab4e-a08d2bfef59a`
- ✅ Implementation plan ready

## What We Need From You ⚠️

### 1. OAuth Redirect URI Configuration

**For Local-First Development:**
This application uses a manual authorization code flow - no tunnel or callback server needed! The user manually copies the authorization code from the redirect URL.

**Action Required:**
Configure redirect URI in eBay Developer Console:
1. Go to: https://developer.ebay.com/my/keys
2. Click on **User Tokens** link for your app: **NicolasQ-Booklist-PRD**
3. In the "Get a Token from eBay via Your Application" section, click **Add eBay Redirect URL** button
4. A new blank row will appear with a blank, blue, underlined entry in the "RuName" column
5. **IMPORTANT**: Click on the blank, blue underlined "RuName" link to open the configuration form
   - If clicking the link doesn't work, look for an "Edit" or "Configure" button/icon in the Actions column on the far right of the row
6. In the form, enter:
   - **Display Title**: Booklister AI (or any descriptive name)
   - **Auth Accepted URL**: `http://localhost:3001/settings`
   - **Auth Declined URL**: `http://localhost:3001/settings` (can be the same or a different URL)
   - **Privacy Policy URL**: Your privacy policy URL (required field)
7. Ensure **OAuth Enabled** checkbox is selected
8. Click **Save** to save the configuration

**Note:** The redirect URI doesn't need to be active. User just manually copies the authorization code from the redirect URL.

---

### 2. Business Policy IDs

eBay requires Policy IDs (not just names) for publishing. You need to get these from your eBay Seller Hub.

**How to Get Policy IDs:**

**Method 1: From Seller Hub (Easiest)**
1. Log into eBay Seller Hub: https://www.ebay.com/sh/home
2. Go to: **Account > Business Policies** or **Settings > Site Preferences**
3. Find your Payment, Return, and Fulfillment policies
4. Click on each policy to view details
5. The Policy ID is usually in the URL or policy details

**Method 2: From Account API (Programmatic)**
- After OAuth is set up, we can add an endpoint to fetch policies programmatically
- Requires authenticated API call to Account API

**Policy Types Needed:**
- **Payment Policy ID**: Used for payment terms
- **Return Policy ID**: Used for return/refund terms  
- **Fulfillment Policy ID**: Used for shipping/handling time

**Action Required:**
1. Get these 3 Policy IDs from your Seller Hub
2. We'll store them in Settings or environment variables

**Questions for You:**
- Do you already have these policies set up in Seller Hub?
- Do you know your Policy IDs, or should we fetch them programmatically after OAuth works?

---

### 3. Environment Variables Setup

We need to create a `.env` file in the `backend/` directory with your eBay credentials.

**Action Required:**
1. Create `backend/.env` file (or add to existing one)
2. Add these variables:

```bash
# eBay Configuration
EBAY_ENV=production
EBAY_CLIENT_ID=your_ebay_client_id
EBAY_CLIENT_SECRET=your_ebay_client_secret
EBAY_REDIRECT_URI=https://<your-tunnel-domain>/ebay/oauth/callback
EBAY_SCOPES="sell.inventory sell.account sell.account.readonly"

# Optional - Policy IDs (if known)
# EBAY_PAYMENT_POLICY_ID=<your-payment-policy-id>
# EBAY_RETURN_POLICY_ID=<your-return-policy-id>
# EBAY_FULFILLMENT_POLICY_ID=<your-fulfillment-policy-id>

# Feature Flag
APP_FEATURE_EBAY_API=true
```

**Important:**
- Replace `<your-tunnel-domain>` with your actual tunnel domain
- Never commit `.env` to git (should be in `.gitignore`)
- `.env` file stays local only

**Questions for You:**
- Do you already have a `.env` file? (I can check and update it)
- Should I create it now with placeholder values, or wait for redirect URI?

---

### 4. eBay Category ID (Optional)

For books, eBay typically uses category `267` (Books > General). We can make this configurable.

**Action Required:**
- Confirm if you want to use category 267 for all books, or if you need category selection per book
- We'll store this in Settings table (default: "267")

**Questions for You:**
- Do all your books go into the same category, or do you need different categories?
- Any preference for category mapping?

---

## Quick Start Option

If you want me to start implementation now, I can:

1. ✅ Create `.env` file with placeholder redirect URI (you update later)
2. ✅ Create all database models and migrations
3. ✅ Implement OAuth flow (you configure redirect URI in eBay Console after)
4. ✅ You provide Policy IDs when ready (or we fetch them programmatically)

**This way you can:**
- See the OAuth flow working (with a temporary redirect URI)
- Test token exchange
- Get Policy IDs from Seller Hub while implementation is in progress
- Update redirect URI in eBay Console once tunnel is set up

---

## Summary

**Must Have Before Full Testing:**
1. ⚠️ OAuth Redirect URI configured in eBay Developer Console
2. ⚠️ Tunnel service set up for local development
3. ⚠️ `.env` file created with credentials and redirect URI

**Can Be Done During Implementation:**
1. ✅ Policy IDs (can fetch programmatically after OAuth works)
2. ✅ Category ID (can use default "267" for now)

**Questions for You:**
1. Which tunnel service do you prefer? (ngrok recommended for speed)
2. Do you want me to start implementation now with placeholders, or wait for redirect URI setup?
3. Do you already know your Policy IDs, or should we fetch them programmatically?

---

## Next Steps

Once you provide:
- Tunnel service choice (or existing public URL)
- Confirmation to start implementation

I can:
1. Create all necessary files and database models
2. Implement OAuth flow
3. Set up token management
4. Create publish pipeline

And you can:
1. Set up tunnel and configure redirect URI in parallel
2. Get Policy IDs from Seller Hub
3. Test OAuth flow once redirect URI is configured


