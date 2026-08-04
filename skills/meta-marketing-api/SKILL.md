---
name: meta-marketing-api
description: Create and operate Meta (Facebook/Instagram) ad campaigns through the Marketing Graph API — campaigns, ad sets, ads and creatives, image upload, pixel-event optimization, EU DSA fields and UTM tracking. Use whenever the user wants to build, duplicate, edit or pull insights from a Meta ad account programmatically, or asks why a Marketing API call behaves differently from the Ads Manager UI.
---

# Meta Marketing API

Operating notes for building Meta campaigns through the API rather than the UI.
The parts that are painful to work out from the documentation alone.

## Authentication model

A **System User token**, issued by the owning Business Manager, authenticates
everything. Three layers must all line up before a write succeeds:

1. **Asset assignment** — the System User must be assigned to the Page, ad
   account and pixel in Business Manager. A valid token is not enough.
2. **Token scopes** — `ads_management`, `ads_read`, `business_management`,
   `pages_manage_ads`.
3. **IDs** — account, page and pixel IDs address an asset. They are not secrets
   and carry no permissions on their own.

When a call returns a permission error, check assignment before you suspect the
token. `verify_token()` in the helper shows scopes and expiry.

## Building a campaign

Five POSTs, in order. Each returns an id the next one needs.

| # | Endpoint | Notes |
|---|---|---|
| 1 | `/{account}/campaigns` | `objective`, `status`, `special_ad_categories` |
| 2 | `/{account}/adsets` | `campaign_id`, budget in account-currency cents, `optimization_goal`, `promoted_object`, `targeting`, DSA fields |
| 3 | `/{account}/adimages` | multipart upload, returns a reusable `hash` |
| 4 | `/{account}/adcreatives` | `object_story_spec`, plus `link_data` **or** `asset_feed_spec` |
| 5 | `/{account}/ads` | `adset_id`, `creative={creative_id: X}` |

Create everything as `status: PAUSED`. Review in the UI, then activate.

## What is immutable

Meta locks down more than you would expect. Editing these is not possible —
you rebuild and re-point:

| Field | Path |
|---|---|
| Name, status, schedule, budget, targeting | `POST /{id}` works in place |
| Campaign `objective` | never changeable |
| Ad set `promoted_object`, `optimization_goal` | new ad set, re-attach ads |
| Creative body, image, title | new creative, swap the ad's `creative_id` |
| Creative `url_tags` | must be set at creation — a later POST returns `success: true` and silently drops the value |

When in doubt between editing and rebuilding, rebuild. It is faster than
fighting the immutability errors.

## Three rules that shape everything

- **`asset_feed_spec` and `object_story_spec.link_data` are mutually
  exclusive.** Pick one per creative. There is no migration between them, only
  a rebuild.
- **Placement customization rules are priority-based, not exhaustive.** Give
  the specific case priority 1 and leave an empty spec as the catch-all.
  Enumerating placements breaks as soon as Meta ships a new one.
- **`success: true` is not proof of a write.** For fields that do not belong on
  that object, the API accepts the call and discards the value. Read back what
  actually persisted.

The general shape of the problem: the API accepts calls the UI would never
send, and silently drops writes it does not support. Build it once in the UI,
read the JSON back, then mirror that shape.

## UTM tracking

Set `url_tags` at creative creation time. Meta expands the macros at impression
time:

```
utm_source={{site_source_name}}&utm_medium={{adset.name}}
&utm_campaign={{campaign.name}}&utm_content={{ad.name}}
```

Campaign and ad set names flow into the URL, so pipes and spaces arrive encoded
as `%7C` and `+`. Keep names short and clean if anything downstream has to
parse them.

## Helper

`scripts/meta_helper.py` — env loading, `g()` / `post()` / `delete()`,
`upload_image()`, `promoted_object` builders and the DSA fields.
