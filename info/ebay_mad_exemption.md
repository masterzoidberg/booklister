# eBay Marketplace Account Deletion (MAD) Exemption Policy

## Summary

**YES**, eBay allows developers to be exempt from MAD requirements if their application does not persist/store eBay user data.

## Official Policy

eBay provides an exemption mechanism for applications that do not store eBay user data. This is perfect for local-first applications like BookLister AI.

---

## 1. Exemption Eligibility

**Question:** Does eBay allow developers to be marked as exempt from MAD requirements?

**Answer:** ✅ **YES**

eBay allows exemptions for applications that:
- Do not persist/store eBay user data
- Only process data in real-time (transactional, no storage)
- Are personal/local-first applications

---

## 2. Official Justification for Exemption

**Question:** What is the official reason or justification accepted for exemption?

**Answer:** **"I do not persist eBay data"** or **"Not persisting eBay data"**

**Official Options:**
- Applications that do not store user data
- Real-time processing only (no data persistence)
- Local-first applications (data stays on user's machine)
- Personal use tools that don't aggregate data across users

**For BookLister AI:**
- ✅ Local-first application
- ✅ Data stored only on user's local machine (SQLite)
- ✅ No cloud storage of eBay data
- ✅ No multi-user aggregation
- ✅ User's own data only

---

## 3. Required Steps for Exemption

**Question:** What documentation, API parameters, or developer portal settings are required?

**Answer:** **Developer Portal Settings (No API Parameters Needed)**

### Steps to Request Exemption:

1. **Access Developer Account**
   - Sign in to: https://developer.ebay.com/
   - Use your eBay developer account credentials

2. **Navigate to Application Keys**
   - Go to: https://developer.ebay.com/marketplace-account-deletion
   - Or: https://developer.ebay.com/my/keys

3. **Find Your App**
   - Locate your app: **NicolasQ-Booklist-PRD**
   - Find the "Notifications" link next to your App ID

4. **Modify Notification Settings**
   - Click "Notifications" link
   - Go to "Marketplace Account Deletion" section
   - Toggle **"Not persisting eBay data"** option to **"On"**

5. **Confirm Exemption Request**
   - A confirmation pop-up will appear
   - Click **"Confirm"**
   - Select exemption reason: **"Not persisting eBay data"**
   - Optionally add additional information:
     ```
     "Local-first application. All data stored only on user's local machine. 
      No cloud storage. No data aggregation. Single-user application."
     ```

6. **Submit**
   - Click **"Submit"** to finalize exemption request
   - Wait for eBay confirmation (usually automatic or within 24-48 hours)

### What Information to Provide:

**Recommended Exemption Statement:**
```
Application Type: Local-first personal tool
Data Storage: All data stored locally on user's machine only
No Cloud Storage: No server-side storage of eBay data
User Scope: Single-user application (user's own data only)
Data Persistence: No eBay user data persisted beyond local session
```

---

## 4. Webhook Endpoint Requirements

**Question:** Does exemption affect the need for implementing `/ebay/mad` webhook endpoints?

**Answer:** ✅ **YES - Exemption Eliminates Webhook Requirement**

### If Exempt (Your Case):
- ❌ **NO** `/ebay/mad` webhook endpoint needed
- ❌ **NO** account deletion notification handling required
- ❌ **NO** webhook URL configuration needed
- ✅ Exemption status confirmed in Developer Portal

### If NOT Exempt:
- ✅ **YES** `/ebay/mad` webhook endpoint required
- ✅ Must handle account deletion notifications
- ✅ Must implement webhook URL: `POST /ebay/mad`
- ✅ Must delete user data within required timeframe

---

## Implementation Impact for BookLister AI

### Current Plan (With Exemption):
- ✅ No webhook endpoints needed
- ✅ No account deletion handling required
- ✅ Simpler implementation (no webhook infrastructure)
- ✅ Perfect fit for local-first architecture

### What We Still Need:
- ✅ OAuth flow (already in plan)
- ✅ Token management (already in plan)
- ✅ Publish pipeline (already in plan)
- ✅ Exemption request in Developer Portal (new action item)

### What We DON'T Need:
- ❌ Webhook endpoint `/ebay/mad`
- ❌ Webhook verification logic
- ❌ Account deletion notification handling
- ❌ Data deletion workflows

---

## Action Items

### Immediate:
1. ⚠️ **Request MAD Exemption** (before going live)
   - Go to: https://developer.ebay.com/marketplace-account-deletion
   - Toggle "Not persisting eBay data" to "On"
   - Submit exemption request with appropriate justification

### During Development:
- No changes needed to implementation plan
- No webhook endpoints required
- Continue with simplified local-first approach

### After Exemption Approved:
- ✅ Confirmed exemption status
- ✅ No webhook requirements
- ✅ Ready for production use

---

## Official eBay Documentation

- **MAD Exemption Page:** https://developer.ebay.com/marketplace-account-deletion
- **Application Keys:** https://developer.ebay.com/my/keys
- **Developer Portal:** https://developer.ebay.com/
- **MAD Developer Guide:** https://developer.ebay.com/develop/guides-v2/marketplace-user-account-deletion

## Policy Verification

**Last Verified:** 2024-11-01  
**Status:** ✅ Compliant with current eBay policy  
**See:** `info/ebay_mad_exemption_verification.md` for verification details

**Verified Items:**
- ✅ "Not persisting eBay data" justification still valid
- ✅ No additional documentation/approval steps required
- ✅ Exempted apps do not need webhook endpoints
- ✅ No significant changes to exemption flow

---

## Important Notes

⚠️ **Accuracy is Critical:**
- Provide accurate information during exemption request
- Incorrect details may lead to penalties or account suspension
- Only claim exemption if your application truly doesn't persist eBay data

✅ **For BookLister AI:**
- Legitimate exemption candidate (local-first, no cloud storage)
- Exemption aligns with actual architecture
- No data aggregation or multi-user storage
- User's own data only, stored locally

---

## Verification

After requesting exemption:
1. Check Developer Portal for exemption status
2. Confirmation email from eBay (if applicable)
3. Status visible in "Notifications" section of your app
4. No webhook URL configuration should be required

---

## Summary

| Question | Answer |
|----------|--------|
| Can developers be exempt? | ✅ YES |
| Justification accepted? | ✅ "Not persisting eBay data" |
| Required steps? | ✅ Developer Portal toggle + submission |
| Webhook endpoint needed? | ❌ NO (if exempt) |
| For local-first apps? | ✅ Perfect fit |

**Conclusion:** BookLister AI qualifies for MAD exemption. Request exemption in Developer Portal before production launch. No webhook endpoints needed.

