// POST { email }  -> emails a signed "manage subscription" link (same reply
//                    whether or not the email is a customer).
// GET  ?t=<token>  -> verifies the link and redirects to the Stripe Customer
//                    Portal, where customers upgrade, cancel or update cards.
import { corsHeaders, db, env, FUNCTIONS_URL, json, normalizeEmail, SITE_URL, sendTemplate } from "../_shared/common.ts";
import { stripeClient } from "../_shared/stripe.ts";

const LINK_TTL_MS = 24 * 60 * 60 * 1000;
const enc = new TextEncoder();
const b64url = (bytes: Uint8Array) =>
  btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function sign(payload: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw", enc.encode(env("LINK_SIGNING_SECRET")),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  return b64url(new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(payload))));
}

async function makeToken(customerId: string): Promise<string> {
  const payload = `${customerId}.${Date.now() + LINK_TTL_MS}`;
  return `${payload}.${await sign(payload)}`;
}

async function readToken(token: string): Promise<string | null> {
  const [customerId, expires, sig] = token.split(".");
  if (!customerId || !expires || !sig) return null;
  if (Number(expires) < Date.now()) return null;
  const expected = await sign(`${customerId}.${expires}`);
  if (expected.length !== sig.length) return null;
  let diff = 0;
  for (let i = 0; i < sig.length; i++) diff |= expected.charCodeAt(i) ^ sig.charCodeAt(i);
  return diff === 0 ? customerId : null;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders() });
  const stripe = stripeClient();
  const client = db();

  if (req.method === "POST") {
    const body = await req.json().catch(() => ({}));
    const email = normalizeEmail(body.email);
    if (!email) return json({ error: "Please enter a valid email address." }, 400);

    const reply = { ok: true, message: "If that email has a subscription, a link is on its way." };
    if (!stripe) return json(reply);

    const { data: customer } = await client
      .from("customers")
      .select("id, stripe_customer_id")
      .eq("email", email)
      .maybeSingle();
    if (customer?.stripe_customer_id) {
      await sendTemplate(client, "billing_portal_link", email, {
        portal_url: `${FUNCTIONS_URL()}/billing-portal?t=${await makeToken(customer.id)}`,
      });
    }
    return json(reply);
  }

  if (req.method !== "GET") return json({ error: "Method not allowed" }, 405);

  const customerId = await readToken(new URL(req.url).searchParams.get("t") ?? "");
  const fail = Response.redirect(`${SITE_URL()}/?error=billing_link_expired`, 303);
  if (!customerId || !stripe) return fail;

  const { data: customer } = await client
    .from("customers")
    .select("stripe_customer_id")
    .eq("id", customerId)
    .maybeSingle();
  if (!customer?.stripe_customer_id) return fail;

  const session = await stripe.billingPortal.sessions.create({
    customer: customer.stripe_customer_id,
    configuration: Deno.env.get("STRIPE_PORTAL_CONFIG") || undefined,
    return_url: SITE_URL(),
  });
  return Response.redirect(session.url, 303);
});
