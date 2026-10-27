# Launch runbook: inverse build

Build the storefront and delivery rails before any product code: domain, email,
landing page, waitlist database, automated onboarding, subscription management
and payments (prepared, switched off). Agents work in a sandbox branch; every
outbound or money-touching action waits for a human.

## What runs where

| Piece | Where | Who does it |
|---|---|---|
| Spec, pricing hypotheses, email copy, landing page, QA | `launch.py` (CrewAI) | Agents -> branch `launch/<slug>` |
| Waitlist, double opt-in, unsubscribe, feedback | `infra/supabase/functions/waitlist-*` | Deployed once, no per-product code |
| Onboarding drip (day 2 survey, day 5 early access) | `onboarding-drip` + `.github/workflows/onboarding-drip.yml` | Off until `DRIP_ENABLED=true` |
| Checkout (Stripe subscriptions) | `create-checkout` | Off until `PAYMENTS_ENABLED=true` |
| Subscription management (Stripe customer portal) | `billing-portal` (emailed signed link) | Works once payments are on |
| Subscription sync + receipts | `stripe-webhook` | Registered by `provision.py` |
| `hello@` / `support@` forwarding, sending domain, Stripe products | `provision.py` | Each step asks you to type `yes` |
| Register domain, deploy page, flip payments/drip, go live | You | Deliberately manual |

## Day 1 checklist

1. **Pick and register the domain** on Cloudflare Registrar (sold at cost, about
   $10.50/yr for `.com`, and it renews at the same price; avoid first-year promos
   that renew at $15-$40). Generic umbrella names that were unregistered at
   standard `.com` price on 2026-10-27 (re-check before buying):
   `oxbench.com`, `larchbench.com`, `tealbench.com`, `finchbench.com`,
   `heronbench.com`, `kestrelbench.com`, `rookbench.com`, `tallbench.com`,
   `basaltbench.com`, `larchstack.com`, `larchtools.com`.
2. **Accounts (all free tier):** Cloudflare, Supabase, Resend, Stripe (test mode).
   Copy `.env.example` to `.env` and fill it in.
3. **Database + functions:**
   ```bash
   supabase link --project-ref <ref> --workdir infra
   supabase db push --workdir infra
   supabase functions deploy --workdir infra
   ```
   `provision.py` prints the full `supabase secrets set` command for your brand.
4. **Generate the launch bundle** from one of the ideas:
   ```bash
   pip install -r requirements.txt
   python launch.py --brand "<Name>" --domain <name>.com --idea-file ideas/invoice-chaser/index.html
   ```
   Review `launch/<slug>/index.html`, `emails.json` and `brand.json` (plans + prices + QA report).
5. **Provision (human-gated):**
   ```bash
   python provision.py --bundle launch/<slug> --dry-run   # see every action first
   python provision.py --bundle launch/<slug>             # type 'yes' per step
   ```
6. **Deploy the page:** Cloudflare Pages, upload `launch/<slug>/`, attach the domain.
7. **Smoke test:** sign up with your own address, confirm, unsubscribe, sign up again.
   Check `select * from waitlist_signals;` in Supabase.

## Day 2: validate

- Turn on the drip (`supabase secrets set DRIP_ENABLED=true`) once the copy is approved.
- Pain-point replies land in `waitlist.pain_point`; email replies land in `hello@`.
- `waitlist_signals` shows which plan people clicked, which is your pricing signal
  before anyone pays.

## Before charging anyone

1. Run a full test checkout with card `4242 4242 4242 4242`, then cancel it through
   "Manage your subscription" and confirm both receipt emails arrive.
2. `supabase secrets set PAYMENTS_ENABLED=true`. The pricing buttons switch from
   "join the waitlist" to Stripe Checkout with no page change.
3. Going live: swap in `sk_live_` keys, set `STRIPE_LIVE_APPROVED=true`, and run
   `python provision.py --bundle launch/<slug> --only stripe --live`. It asks you to type
   the domain to confirm.
