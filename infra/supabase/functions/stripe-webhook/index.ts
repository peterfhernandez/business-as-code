// Stripe -> Supabase subscription sync. Point a Stripe webhook endpoint at
// <FUNCTIONS_URL>/stripe-webhook with the customer.subscription.* events.
import Stripe from "npm:stripe@17.7.0";
import { db, env, json, sendTemplate } from "../_shared/common.ts";

const HANDLED = new Set([
  "customer.subscription.created",
  "customer.subscription.updated",
  "customer.subscription.deleted",
]);

Deno.serve(async (req) => {
  const key = env("STRIPE_SECRET_KEY");
  if (key.startsWith("sk_live_") && env("STRIPE_LIVE_APPROVED", "false") !== "true") {
    return json({ error: "Live mode not approved" }, 503);
  }
  const stripe = new Stripe(key, {
    apiVersion: "2024-12-18.acacia",
    httpClient: Stripe.createFetchHttpClient(),
  });

  let event: Stripe.Event;
  try {
    event = await stripe.webhooks.constructEventAsync(
      await req.text(),
      req.headers.get("stripe-signature") ?? "",
      env("STRIPE_WEBHOOK_SECRET"),
      undefined,
      Stripe.createSubtleCryptoProvider(),
    );
  } catch {
    return json({ error: "Invalid signature" }, 400);
  }

  const client = db();
  const { data: seen } = await client.from("stripe_events").select("id").eq("id", event.id)
    .maybeSingle();
  if (seen || !HANDLED.has(event.type)) return json({ received: true });

  const sub = event.data.object as Stripe.Subscription;
  const stripeCustomerId = typeof sub.customer === "string" ? sub.customer : sub.customer.id;

  let { data: customer } = await client
    .from("customers")
    .select("id, email")
    .eq("stripe_customer_id", stripeCustomerId)
    .maybeSingle();

  // Subscriptions created in the Stripe dashboard have no customer row yet.
  if (!customer) {
    const sc = await stripe.customers.retrieve(stripeCustomerId);
    if (sc.deleted || !sc.email) return json({ received: true, skipped: "no email" });
    const { data, error } = await client
      .from("customers")
      .upsert({ email: sc.email.toLowerCase(), stripe_customer_id: stripeCustomerId }, {
        onConflict: "email",
      })
      .select("id, email")
      .single();
    if (error) return json({ error: error.message }, 500);
    customer = data;
  }

  const item = sub.items.data[0];
  const { error } = await client.from("subscriptions").upsert({
    stripe_subscription_id: sub.id,
    customer_id: customer.id,
    status: sub.status,
    price_lookup_key: item?.price.lookup_key ?? item?.price.id ?? null,
    current_period_end: new Date(sub.current_period_end * 1000).toISOString(),
    cancel_at_period_end: sub.cancel_at_period_end,
    updated_at: new Date().toISOString(),
  });
  // A 500 makes Stripe retry, so the event is only marked seen once stored.
  if (error) return json({ error: error.message }, 500);

  if (event.type === "customer.subscription.created") {
    await sendTemplate(client, "subscription_started", customer.email, {});
  } else if (event.type === "customer.subscription.deleted") {
    await sendTemplate(client, "subscription_canceled", customer.email, {});
  }

  await client.from("stripe_events").insert({ id: event.id, type: event.type });
  return json({ received: true });
});
