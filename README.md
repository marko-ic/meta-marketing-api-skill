# Meta Marketing API — Skill

An agent skill for building and operating Meta (Facebook/Instagram) ad campaigns
through the Marketing Graph API instead of the Ads Manager UI.

This is a stripped extract from a larger private toolkit: the operating notes
and the helper module, without the reference catalogue and client examples.

```
skills/meta-marketing-api/
  SKILL.md              when it applies, the five-POST build order,
                        what Meta treats as immutable, the traps
  scripts/meta_helper.py  the HTTP layer everything else sits on
```

## What it does

Automates the path from finished assets to a live campaign: upload the image,
create campaign, ad set, creative and ad, set the optimization event, attach UTM
tracking and the EU DSA transparency fields. What is otherwise a long click-path
through Ads Manager becomes one script run.

The interesting part is not the HTTP calls — it is knowing which fields Meta
refuses to change after creation, and which writes it accepts and then silently
discards. That is what `SKILL.md` records.

## Use

Drop `skills/meta-marketing-api/` into your agent's skills directory, or use the
helper on its own:

```python
from meta_helper import load_env, g, post, upload_image, promoted_custom_event

env  = load_env(".env")
acct = env["META_AD_ACCOUNT_ID"]

img = upload_image(env, acct, "creative.jpg")
ad_set = post(env, f"{acct}/adsets", {
    "name": "Example ad set",
    "campaign_id": campaign_id,
    "daily_budget": 2000,                      # account currency, in cents
    "optimization_goal": "OFFSITE_CONVERSIONS",
    "billing_event": "IMPRESSIONS",
    "promoted_object": promoted_custom_event(pixel_id, "YourEventName"),
    "status": "PAUSED",
})
```

No dependencies — the helper shells out to `curl`, so it runs anywhere Python
and curl exist.

## Setup

```sh
cp .env.example .env     # System User token + asset ids
```

The token needs `ads_management`, `ads_read`, `business_management` and
`pages_manage_ads`, and the System User must be assigned to the page, ad account
and pixel in Business Manager.

## License

MIT — see [LICENSE](LICENSE).
