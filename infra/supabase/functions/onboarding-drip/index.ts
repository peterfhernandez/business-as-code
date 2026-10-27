// Scheduled (hourly) by .github/workflows/onboarding-drip.yml.
// Moves confirmed waitlist members through the onboarding sequence.
// Human gate: nothing is sent unless DRIP_ENABLED=true is set as a secret.
import { actionUrl, db, env, json, SITE_URL, sendTemplate } from "../_shared/common.ts";

// step the member is on -> email to send next and days to wait since the last one
const SEQUENCE: Record<number, { template: string; afterDays: number }> = {
  1: { template: "onboarding_survey", afterDays: 2 },
  2: { template: "onboarding_early_access", afterDays: 3 },
};
const BATCH_SIZE = 50;

Deno.serve(async (req) => {
  if (req.headers.get("x-cron-secret") !== env("CRON_SECRET")) {
    return json({ error: "Unauthorized" }, 401);
  }
  if (env("DRIP_ENABLED", "false") !== "true") {
    return json({ ok: true, skipped: "DRIP_ENABLED is not true" });
  }

  const client = db();
  const results: Record<string, number> = {};

  for (const [step, { template, afterDays }] of Object.entries(SEQUENCE)) {
    const cutoff = new Date(Date.now() - afterDays * 86_400_000).toISOString();
    const { data: due } = await client
      .from("waitlist")
      .select("id, email, token")
      .eq("status", "confirmed")
      .eq("onboarding_step", Number(step))
      .lte("last_emailed_at", cutoff)
      .limit(BATCH_SIZE);

    let sent = 0;
    for (const row of due ?? []) {
      const ok = await sendTemplate(client, template, row.email, {
        feedback_url: `${SITE_URL()}/?feedback=${row.token}`,
        pricing_url: `${SITE_URL()}/#pricing`,
        unsubscribe_url: actionUrl("unsubscribe", row.token),
      });
      if (!ok) continue;
      sent++;
      await client.from("waitlist").update({
        onboarding_step: Number(step) + 1,
        last_emailed_at: new Date().toISOString(),
      }).eq("id", row.id);
    }
    results[template] = sent;
  }

  return json({ ok: true, sent: results });
});
