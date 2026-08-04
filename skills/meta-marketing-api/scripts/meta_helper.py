"""
Meta Marketing API helper — the thin layer everything else sits on.

    from meta_helper import load_env, g, post, upload_image

    env = load_env(".env")
    acct = env["META_AD_ACCOUNT_ID"]
    info = g(env, acct, "name,account_status,currency,timezone_name")

Uses subprocess + curl rather than `requests`, so it runs in a throwaway script
with no pip install, and the payload shape matches Meta's own documentation
examples one to one. Adding "-v" to the curl args gives you the raw exchange
when something is off.
"""

import json
import os
import subprocess
import urllib.parse
from pathlib import Path

DEFAULT_ENV_PATH = os.environ.get("META_ENV_FILE", ".env")


def load_env(path: str | Path = DEFAULT_ENV_PATH) -> dict:
    """Read a .env file into a dict. Blank lines and comments are skipped.

    Resolution order: explicit `path` -> $META_ENV_FILE -> ./.env
    See `.env.example` for the expected keys.
    """
    out = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    if "META_ACCESS_TOKEN" not in out:
        raise RuntimeError(f"META_ACCESS_TOKEN missing from {path}")
    out.setdefault("META_API_VERSION", "v21.0")
    return out


def _base(env: dict) -> str:
    return f"https://graph.facebook.com/{env['META_API_VERSION']}"


def g(env: dict, path: str, fields: str = "", **extra_params) -> dict:
    """GET. `fields` is a comma-separated field list; anything else goes as kwargs.

        g(env, "act_000/insights",
          fields="spend,impressions,clicks",
          level="campaign", date_preset="last_30d")
    """
    params = {"access_token": env["META_ACCESS_TOKEN"]}
    if fields:
        params["fields"] = fields
    params.update({k: str(v) for k, v in extra_params.items()})
    url = f"{_base(env)}/{path}?{urllib.parse.urlencode(params)}"
    raw = subprocess.run(["curl", "-s", url], capture_output=True, text=True).stdout
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}


def post(env: dict, path: str, data: dict) -> dict:
    """POST as multipart form. dict/list values are JSON-encoded automatically."""
    form_data = {"access_token": env["META_ACCESS_TOKEN"]}
    for k, v in data.items():
        form_data[k] = json.dumps(v) if isinstance(v, (dict, list)) else str(v)

    args = ["curl", "-s", "-X", "POST", f"{_base(env)}/{path}"]
    for k, v in form_data.items():
        # --form-string, never -F: curl's -F treats ';' as a content-type
        # separator and '@' / '<' as file-read prefixes, which silently
        # truncates any ad copy containing those characters.
        args += ["--form-string", f"{k}={v}"]

    raw = subprocess.run(args, capture_output=True, text=True).stdout
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}


def delete(env: dict, path: str) -> dict:
    """DELETE. Permanent — there is no undelete."""
    url = f"{_base(env)}/{path}?access_token={env['META_ACCESS_TOKEN']}"
    raw = subprocess.run(["curl", "-s", "-X", "DELETE", url],
                         capture_output=True, text=True).stdout
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}


def upload_image(env: dict, ad_account_id: str, file_path: str | Path) -> str:
    """Upload an image and return its hash. Hashes are scoped to the ad account,
    so one upload can back many creatives in that account."""
    url = f"{_base(env)}/{ad_account_id}/adimages"
    args = [
        "curl", "-s", "-X", "POST", url,
        "-F", f"filename=@{file_path}",
        "-F", f"access_token={env['META_ACCESS_TOKEN']}",
    ]
    raw = subprocess.run(args, capture_output=True, text=True).stdout
    data = json.loads(raw)
    if "error" in data:
        raise RuntimeError(f"Upload failed: {data['error']}")
    return next(iter(data.get("images", {}).values()))["hash"]


def actions_get(actions: list | None, action_type: str, default: str = "0") -> str:
    """Pluck one value out of the insights `actions` array by action_type."""
    return next(
        (a["value"] for a in (actions or []) if a.get("action_type") == action_type),
        default,
    )


# ---------- Diagnostics ----------

def verify_token(env: dict) -> dict:
    """Inspect the configured token: scopes, expiry, app, system-user flag.
    First thing to run when a call returns a permission error."""
    return g(env, "debug_token", input_token=env["META_ACCESS_TOKEN"])


def list_ad_accounts(env: dict) -> dict:
    """Every ad account this token can see."""
    return g(env, "me/adaccounts", fields="name,account_id,currency,business")


def list_custom_conversions(env: dict, ad_account_id: str) -> dict:
    """Custom Conversions assigned to an ad account.

    Returns empty if the conversion is not explicitly assigned to this account
    in Business Manager — even when it is plainly visible in Events Manager.
    """
    return g(env, f"{ad_account_id}/customconversions",
             fields="name,id,custom_event_type,rule,pixel", limit=200)


# ---------- promoted_object builders ----------
#
# promoted_object tells Meta what to optimize for. It is immutable once the ad
# set is published: changing the optimization event means a new ad set with the
# ads re-attached, not an edit.

def promoted_custom_event(pixel_id: str, event_name: str) -> dict:
    """For custom pixel events, i.e. fbq('trackCustom', '<name>', ...)."""
    return {
        "pixel_id": pixel_id,
        "custom_event_type": "OTHER",
        "custom_event_str": event_name,
    }


def promoted_standard_event(pixel_id: str, event_type: str = "CONTENT_VIEW") -> dict:
    """For standard pixel events.

    The API enum names differ from the pixel-side names: `ViewContent` is
    `CONTENT_VIEW` here, not `VIEW_CONTENT`.
    """
    return {"pixel_id": pixel_id, "custom_event_type": event_type}


def promoted_custom_conversion(pixel_id: str, conversion_id: str) -> dict:
    """For URL-rule-based Custom Conversions defined in Events Manager."""
    return {"pixel_id": pixel_id, "custom_conversion_id": conversion_id}


# ---------- EU Digital Services Act ----------

def dsa_fields(legal_name: str, beneficiary: str | None = None) -> dict:
    """DSA ad-transparency fields for an ad set.

    Sets `dsa_payor` and `dsa_beneficiary` to the same legal entity, which is
    what shows on the served ad when payer and advertiser are identical. Always
    set both explicitly: some ad accounts auto-fill them from a Business
    Manager default and some do not, and on the latter, omitting them fails
    with error_subcode 3858081 ("No advertiser indicated").

        post(env, f"{acct}/adsets", {..., **dsa_fields("Example GmbH")})
    """
    return {
        "dsa_payor": legal_name,
        "dsa_beneficiary": beneficiary if beneficiary is not None else legal_name,
    }
