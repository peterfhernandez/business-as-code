// POST { email, plan } -> { url } of a Stripe Checkout session for that plan.
// `plan` is a Stripe price lookup key created by provision.py,
// e.g. "acme_pro_monthly". While PAYMENTS_ENABLED is off this returns
// { payments_enabled: false } and the landing page joins the waitlist instead.
import { corsHeaders, db, env, json, normalizeEmail, SITE_URL } from "../_shared/common.ts";
import { ensureCustomer, stripeClient } from "../_shared/stripe.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders() });
  if (req.method !== "POST") return json({ error: "Method not allowed" }, 405);

  const stripe = stripeClient();
  if (!stripe) return json({ payments_enabled: false });

  const body = await req.json().catch(() => ({}));
  const email = normalizeEmail(body.email);
  const plan = typeof body.plan === "string" ? body.plan : "";
  if (!email) return json({ error: "Please enter a valid email address." }, 400);
  if (!/^[a-z0-9_]{3,80}$/.test(plan)) return json({ error: "Unknown plan." }, 400);

  const prices = await stripe.prices.list({ lookup_keys: [plan], active: true, limit: 1 });
  const price = prices.data[0];
  if (!price) return json({ error: "Unknown plan." }, 400);

  const customer = await ensureCustomer(db(), stripe, email);
  const trialDays = Number(env("TRIAL_DAYS", "0"));

  const session = await stripe.checkout.sessions.create({
    mode: "subscription",
    customer: customer.stripe_customer_id,
    line_items: [{ price: price.id, quantity: 1 }],
    allow_promotion_codes: true,
    subscription_data: trialDays > 0 ? { trial_period_days: trialDays } : undefined,
    success_url: `${SITE_URL()}/?checkout=success`,
    cancel_url: `${SITE_URL()}/?checkout=cancelled#pricing`,
  });

  return json({ payments_enabled: true, url: session.url });
});
