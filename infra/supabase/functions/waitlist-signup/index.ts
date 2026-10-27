// POST { email, plan_interest?, source?, utm?, website? } -> stores the signup
// and sends the double opt-in email. `website` is a honeypot field.
import { actionUrl, corsHeaders, db, json, normalizeEmail, sendTemplate } from "../_shared/common.ts";

const RESEND_COOLDOWN_MS = 10 * 60 * 1000;
const clip = (v: unknown, max = 100) => (typeof v === "string" ? v.slice(0, max) : null);

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders() });
  if (req.method !== "POST") return json({ error: "Method not allowed" }, 405);

  const body = await req.json().catch(() => ({}));
  // Bots fill every field; humans never see this one.
  if (body.website) return json({ ok: true });

  const email = normalizeEmail(body.email);
  if (!email) return json({ error: "Please enter a valid email address." }, 400);

  const utm = typeof body.utm === "object" && body.utm !== null
    ? Object.fromEntries(
      Object.entries(body.utm).slice(0, 10).map(([k, v]) => [k.slice(0, 40), clip(v)]),
    )
    : {};

  const client = db();
  const { data: existing } = await client
    .from("waitlist")
    .select("id, status, token, last_emailed_at")
    .eq("email", email)
    .maybeSingle();

  if (existing?.status === "confirmed") {
    return json({ ok: true, status: "confirmed", message: "You're already on the list." });
  }

  let row = existing;
  if (!row) {
    const { data, error } = await client
      .from("waitlist")
      .insert({
        email,
        plan_interest: clip(body.plan_interest, 40),
        source: clip(body.source),
        utm,
      })
      .select("id, status, token, last_emailed_at")
      .single();
    if (error) return json({ error: "Could not save your signup. Please try again." }, 500);
    row = data;
  } else if (existing.status === "unsubscribed") {
    await client.from("waitlist").update({ status: "pending" }).eq("id", existing.id);
  }

  // Avoid turning the form into a way to spam someone's inbox.
  const recentlyEmailed = row.last_emailed_at &&
    Date.now() - new Date(row.last_emailed_at).getTime() < RESEND_COOLDOWN_MS;
  if (!recentlyEmailed) {
    const sent = await sendTemplate(client, "waitlist_confirm", email, {
      confirm_url: actionUrl("confirm", row.token),
      unsubscribe_url: actionUrl("unsubscribe", row.token),
    });
    if (sent) {
      await client.from("waitlist").update({ last_emailed_at: new Date().toISOString() })
        .eq("id", row.id);
    }
  }

  return json({ ok: true, status: "pending", message: "Check your inbox to confirm your spot." });
});
