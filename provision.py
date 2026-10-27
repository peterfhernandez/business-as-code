"""Inverse build - human-gated provisioning of the launch rails.

Reads the bundle written by launch.py and wires up, one approved step at a time:

  email      Cloudflare Email Routing: hello@ and support@ -> your inbox
  sending    Resend sending domain + its DNS records on Cloudflare
  templates  Onboarding email templates -> Supabase email_templates
  stripe     Stripe products/prices, customer portal and webhook (test mode)

    python provision.py --bundle launch/<slug> --branch launch/<slug> [--only stripe]

Nothing is changed without typing 'yes' at the prompt. --dry-run only prints.
Registering the domain, deploying the page and turning on payments or the drip
stay manual on purpose.
"""
import sys
from types import ModuleType


class MagicMockType(ModuleType):
    def __getattr__(self, name):
        return object


mcp_mock = MagicMockType("mcp")
mcp_types_mock = MagicMockType("mcp.types")

sys.modules["mcp"] = mcp_mock
sys.modules["mcp.types"] = mcp_types_mock

import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from launchkit.storage import load_file  # noqa: E402
from launchkit.validation import email_template_errors  # noqa: E402

load_dotenv()

STEPS = ("email", "sending", "templates", "stripe")
CF_API = "https://api.cloudflare.com/client/v4"
STRIPE_API = "https://api.stripe.com/v1"
DRY_RUN = False


class StepSkipped(Exception):
    pass


def approve(action: str, details: list[str] | None = None) -> bool:
    print(f"\n>>> {action}")
    for line in details or []:
        print(f"    {line}")
    if DRY_RUN:
        print("    (dry run - not executed)")
        return False
    return input("    Type 'yes' to proceed: ").strip().lower() == "yes"


def require_env(*names: str) -> dict[str, str]:
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        raise StepSkipped(f"set {', '.join(missing)} in .env")
    return {n: os.environ[n] for n in names}


# ---------------------------------------------------------------------------
# Cloudflare
# ---------------------------------------------------------------------------


def cf(method: str, path: str, **kwargs) -> dict:
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    res = requests.request(
        method, f"{CF_API}{path}", headers={"Authorization": f"Bearer {token}"},
        timeout=30, **kwargs,
    )
    body = res.json()
    if not body.get("success"):
        raise RuntimeError(f"Cloudflare {method} {path}: {body.get('errors')}")
    return body["result"]


def cf_zone(domain: str) -> dict:
    zones = cf("GET", "/zones", params={"name": domain})
    if not zones:
        raise StepSkipped(
            f"{domain} is not on Cloudflare yet. Register it at "
            "https://dash.cloudflare.com/?to=/:account/domains/register (at-cost pricing) "
            "or add it as a zone, then re-run."
        )
    return zones[0]


def step_email(brand: dict) -> None:
    env = require_env("CLOUDFLARE_API_TOKEN", "FORWARD_TO")
    domain = brand["domain"]
    zone = cf_zone(domain)
    aliases = list(brand["emails"].values())
    if not approve(
        f"Enable Cloudflare Email Routing on {domain}",
        [f"{a} -> {env['FORWARD_TO']}" for a in aliases]
        + ["Adds Cloudflare MX + SPF records; sends a verification email to the inbox."],
    ):
        return

    cf("POST", f"/zones/{zone['id']}/email/routing/dns")
    account_id = zone["account"]["id"]
    existing = {
        a["email"] for a in cf("GET", f"/accounts/{account_id}/email/routing/addresses")
    }
    if env["FORWARD_TO"] not in existing:
        cf("POST", f"/accounts/{account_id}/email/routing/addresses",
           json={"email": env["FORWARD_TO"]})
        print(f"    Verification email sent to {env['FORWARD_TO']} - click it.")

    rules = cf("GET", f"/zones/{zone['id']}/email/routing/rules")
    routed = {m.get("value") for r in rules for m in r.get("matchers", [])}
    for alias in aliases:
        if alias in routed:
            continue
        cf("POST", f"/zones/{zone['id']}/email/routing/rules", json={
            "name": f"Forward {alias}",
            "enabled": True,
            "matchers": [{"type": "literal", "field": "to", "value": alias}],
            "actions": [{"type": "forward", "value": [env["FORWARD_TO"]]}],
        })
        print(f"    Routed {alias}")


def step_sending(brand: dict) -> None:
    env = require_env("CLOUDFLARE_API_TOKEN", "RESEND_API_KEY")
    domain = brand["domain"]
    zone = cf_zone(domain)
    headers = {"Authorization": f"Bearer {env['RESEND_API_KEY']}"}

    domains = requests.get("https://api.resend.com/domains", headers=headers, timeout=30).json()
    match = next((d for d in domains.get("data", []) if d["name"] == domain), None)
    if not approve(
        f"Set up {domain} as a Resend sending domain",
        ["Adds Resend's DKIM, SPF and bounce MX records (on the send. subdomain) to Cloudflare."],
    ):
        return

    if match is None:
        match = requests.post("https://api.resend.com/domains", headers=headers,
                              json={"name": domain}, timeout=30).json()
    records = requests.get(f"https://api.resend.com/domains/{match['id']}",
                           headers=headers, timeout=30).json().get("records", [])

    existing = {(r["type"], r["name"]) for r in cf("GET", f"/zones/{zone['id']}/dns_records",
                                                    params={"per_page": 500})}
    for rec in records:
        name = rec["name"] if rec["name"].endswith(domain) else f"{rec['name']}.{domain}"
        if (rec["type"], name) in existing:
            continue
        payload = {"type": rec["type"], "name": name, "content": rec["value"], "ttl": 1}
        if rec["type"] == "MX":
            payload["priority"] = int(rec.get("priority", 10))
        cf("POST", f"/zones/{zone['id']}/dns_records", json=payload)
        print(f"    Added {rec['type']} {name}")

    requests.post(f"https://api.resend.com/domains/{match['id']}/verify",
                  headers=headers, timeout=30)
    print("    Verification requested; Resend usually confirms within minutes.")


# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------


def step_templates(brand: dict, emails: dict) -> None:
    env = require_env("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
    errors = email_template_errors(emails)
    if errors:
        raise StepSkipped("email templates failed validation: " + " ".join(errors))
    if not approve(f"Upsert {len(emails)} email templates into Supabase", sorted(emails)):
        return
    res = requests.post(
        f"{env['SUPABASE_URL'].rstrip('/')}/rest/v1/email_templates",
        headers={
            "apikey": env["SUPABASE_SERVICE_ROLE_KEY"],
            "Authorization": f"Bearer {env['SUPABASE_SERVICE_ROLE_KEY']}",
            "Prefer": "resolution=merge-duplicates",
        },
        json=[{"key": k, "subject": t["subject"], "html": t["html"]} for k, t in emails.items()],
        timeout=30,
    )
    res.raise_for_status()
    print("    Templates saved.")


# ---------------------------------------------------------------------------
# Stripe
# ---------------------------------------------------------------------------


def stripe(method: str, path: str, data: dict | list | None = None) -> dict:
    payload = {"params": data} if method == "GET" else {"data": data}
    res = requests.request(
        method, f"{STRIPE_API}{path}", auth=(os.environ["STRIPE_SECRET_KEY"], ""),
        timeout=30, **payload,
    )
    body = res.json()
    if res.status_code >= 400:
        raise RuntimeError(f"Stripe {method} {path}: {body.get('error', {}).get('message')}")
    return body


def step_stripe(brand: dict, live: bool) -> None:
    env = require_env("STRIPE_SECRET_KEY", "SUPABASE_URL")
    if env["STRIPE_SECRET_KEY"].startswith("sk_live_"):
        if not live:
            raise StepSkipped("live Stripe key found; use a test key (sk_test_) or pass --live")
        if DRY_RUN or input(f"    LIVE MODE. Type the domain ({brand['domain']}) to confirm: ") \
                != brand["domain"]:
            raise StepSkipped("live mode not confirmed")

    prices = brand["stripe_prices"]
    if approve(
        "Create Stripe products and monthly prices",
        [f"{p['lookup_key']}: {p['unit_amount'] / 100:.2f} {p['currency'].upper()}/month"
         for p in prices],
    ):
        for p in prices:
            found = stripe("GET", "/prices", [("lookup_keys[]", p["lookup_key"])])["data"]
            if found:
                print(f"    {p['lookup_key']} already exists")
                continue
            product = stripe("POST", "/products", {"name": p["product_name"]})
            stripe("POST", "/prices", {
                "product": product["id"],
                "unit_amount": p["unit_amount"],
                "currency": p["currency"],
                "recurring[interval]": p["interval"],
                "lookup_key": p["lookup_key"],
            })
            print(f"    Created {p['lookup_key']}")

    site = f"https://{brand['domain']}"
    if approve(
        "Create the Stripe customer portal configuration",
        ["Customers can update cards, see invoices, switch plans and cancel at period end."],
    ):
        plan_prices: dict[str, list[str]] = {}
        for p in prices:
            for price in stripe("GET", "/prices", [("lookup_keys[]", p["lookup_key"])])["data"]:
                plan_prices.setdefault(price["product"], []).append(price["id"])
        data = [
            ("business_profile[headline]", f"Manage your {brand['brand']} subscription"),
            ("default_return_url", site),
            ("features[invoice_history][enabled]", "true"),
            ("features[payment_method_update][enabled]", "true"),
            ("features[subscription_cancel][enabled]", "true"),
            ("features[subscription_cancel][mode]", "at_period_end"),
            ("features[subscription_update][enabled]", "true" if plan_prices else "false"),
            ("features[subscription_update][default_allowed_updates][]", "price"),
            ("features[subscription_update][proration_behavior]", "create_prorations"),
        ]
        for i, (product, ids) in enumerate(plan_prices.items()):
            data.append((f"features[subscription_update][products][{i}][product]", product))
            data += [(f"features[subscription_update][products][{i}][prices][]", x) for x in ids]
        config = stripe("POST", "/billing_portal/configurations", data)
        print(f"    supabase secrets set STRIPE_PORTAL_CONFIG={config['id']}")

    hook_url = f"{env['SUPABASE_URL'].rstrip('/')}/functions/v1/stripe-webhook"
    if approve("Register the Stripe webhook endpoint", [hook_url]):
        hooks = stripe("GET", "/webhook_endpoints", {"limit": 100})["data"]
        if any(h["url"] == hook_url for h in hooks):
            print("    Webhook already registered (its secret is only shown at creation).")
        else:
            hook = stripe("POST", "/webhook_endpoints", [
                ("url", hook_url),
                ("enabled_events[]", "customer.subscription.created"),
                ("enabled_events[]", "customer.subscription.updated"),
                ("enabled_events[]", "customer.subscription.deleted"),
            ])
            print(f"    supabase secrets set STRIPE_WEBHOOK_SECRET={hook['secret']}")


# ---------------------------------------------------------------------------


def print_manual_steps(brand: dict) -> None:
    domain = brand["domain"]
    print(f"""
================ MANUAL / HUMAN-GATED STEPS ================
1. Supabase (once):
     supabase link --project-ref <ref> --workdir infra
     supabase db push --workdir infra
     supabase secrets set --workdir infra \\
       SITE_URL=https://{domain} BRAND_NAME="{brand['brand']}" \\
       EMAIL_FROM="{brand['brand']} <{brand['emails']['hello']}>" \\
       EMAIL_REPLY_TO={brand['emails']['support']} ALLOWED_ORIGIN=https://{domain} \\
       RESEND_API_KEY=... STRIPE_SECRET_KEY=sk_test_... \\
       CRON_SECRET=$(openssl rand -hex 32) LINK_SIGNING_SECRET=$(openssl rand -hex 32)
     supabase functions deploy --workdir infra
2. Deploy the page: Cloudflare Pages -> upload launch/{brand['slug']}/ -> custom domain {domain}.
3. Drip emails: set the repo variable FUNCTIONS_URL and secret CRON_SECRET, then
     supabase secrets set DRIP_ENABLED=true            (approve bulk sending)
4. Payments: after a test checkout works end to end,
     supabase secrets set PAYMENTS_ENABLED=true        (pricing buttons switch to checkout)
   Going live needs sk_live_ keys, STRIPE_LIVE_APPROVED=true and a re-run of
     python provision.py --bundle launch/{brand['slug']} --only stripe --live
""")


def main():
    global DRY_RUN
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", required=True, help="e.g. launch/acme")
    parser.add_argument("--branch", help="branch launch.py saved to (when saved to GitHub)")
    parser.add_argument("--only", help=f"comma-separated subset of: {','.join(STEPS)}")
    parser.add_argument("--live", action="store_true", help="allow a live Stripe key")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    DRY_RUN = args.dry_run

    bundle = args.bundle.rstrip("/")
    branch = args.branch or bundle
    brand_raw = load_file(f"{bundle}/brand.json", branch)
    emails_raw = load_file(f"{bundle}/emails.json", branch)
    if not brand_raw or not emails_raw:
        sys.exit(f"Could not find {bundle}/brand.json and emails.json locally or on {branch}.")
    brand, emails = json.loads(brand_raw), json.loads(emails_raw)

    if not brand.get("qa", {}).get("approved"):
        print("WARNING: QA did not approve this bundle:")
        for issue in brand.get("qa", {}).get("issues", []):
            print(f"  - {issue}")

    selected = args.only.split(",") if args.only else list(STEPS)
    runners = {
        "email": lambda: step_email(brand),
        "sending": lambda: step_sending(brand),
        "templates": lambda: step_templates(brand, emails),
        "stripe": lambda: step_stripe(brand, args.live),
    }
    for name in selected:
        if name not in runners:
            sys.exit(f"Unknown step '{name}'. Choose from {', '.join(STEPS)}.")
        try:
            runners[name]()
        except StepSkipped as e:
            print(f"\n--- {name}: skipped ({e})")

    print_manual_steps(brand)


if __name__ == "__main__":
    main()
