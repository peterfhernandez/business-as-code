// GET  ?action=confirm|unsubscribe&token=...  -> one-click links from emails
// POST { action: "feedback", token, pain_point } -> Day-2 validation replies
import { actionUrl, corsHeaders, db, json, SITE_URL, sendTemplate } from "../_shared/common.ts";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const redirect = (query: string) =>
  new Response(null, { status: 303, headers: { Location: `${SITE_URL()}/?${query}` } });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders() });
  const client = db();

  if (req.method === "POST") {
    const body = await req.json().catch(() => ({}));
    if (body.action !== "feedback" || !UUID_RE.test(String(body.token ?? ""))) {
      return json({ error: "Invalid request" }, 400);
    }
    const painPoint = String(body.pain_point ?? "").trim().slice(0, 2000);
    if (painPoint.length < 3) return json({ error: "Tell us a little more." }, 400);
    const { data } = await client
      .from("waitlist")
      .update({ pain_point: painPoint })
      .eq("token", body.token)
      .select("id");
    return data?.length ? json({ ok: true }) : json({ error: "Link expired" }, 404);
  }

  if (req.method !== "GET") return json({ error: "Method not allowed" }, 405);

  const url = new URL(req.url);
  const action = url.searchParams.get("action");
  const token = url.searchParams.get("token") ?? "";
  if (!UUID_RE.test(token)) return redirect("error=invalid_link");

  const { data: row } = await client
    .from("waitlist")
    .select("id, email, status, token")
    .eq("token", token)
    .maybeSingle();
  if (!row) return redirect("error=invalid_link");

  if (action === "unsubscribe") {
    await client.from("waitlist").update({ status: "unsubscribed" }).eq("id", row.id);
    return redirect("unsubscribed=1");
  }

  if (action === "confirm") {
    if (row.status !== "confirmed") {
      const now = new Date().toISOString();
      await client.from("waitlist").update({
        status: "confirmed",
        confirmed_at: now,
        onboarding_step: 1,
        last_emailed_at: now,
      }).eq("id", row.id);
      await sendTemplate(client, "waitlist_welcome", row.email, {
        feedback_url: `${SITE_URL()}/?feedback=${row.token}`,
        unsubscribe_url: actionUrl("unsubscribe", row.token),
      });
    }
    return redirect("confirmed=1");
  }

  return redirect("error=invalid_link");
});
