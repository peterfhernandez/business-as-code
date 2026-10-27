import Stripe from "npm:stripe@17.7.0";
import { SupabaseClient } from "npm:@supabase/supabase-js@2.45.4";
import { env } from "./common.ts";

/**
 * Returns a Stripe client, or null while payments are switched off.
 * Human gate: a live-mode key is refused unless STRIPE_LIVE_APPROVED=true.
 */
export function stripeClient(): Stripe | null {
  if (env("PAYMENTS_ENABLED", "false") !== "true") return null;
  const key = env("STRIPE_SECRET_KEY");
  if (key.startsWith("sk_live_") && env("STRIPE_LIVE_APPROVED", "false") !== "true") {
    throw new Error("Live Stripe key set without STRIPE_LIVE_APPROVED=true");
  }
  return new Stripe(key, {
    apiVersion: "2024-12-18.acacia",
    httpClient: Stripe.createFetchHttpClient(),
  });
}

/** Finds or creates the customer row and its Stripe customer. */
export async function ensureCustomer(
  client: SupabaseClient,
  stripe: Stripe,
  email: string,
): Promise<{ id: string; stripe_customer_id: string }> {
  const { data: existing } = await client
    .from("customers")
    .select("id, stripe_customer_id")
    .eq("email", email)
    .maybeSingle();
  if (existing?.stripe_customer_id) return existing;

  const customer = await stripe.customers.create({ email });
  const { data, error } = await client
    .from("customers")
    .upsert({ email, stripe_customer_id: customer.id }, { onConflict: "email" })
    .select("id, stripe_customer_id")
    .single();
  if (error) throw error;
  return data;
}
