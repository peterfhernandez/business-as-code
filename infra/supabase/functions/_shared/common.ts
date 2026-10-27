import { createClient, SupabaseClient } from "npm:@supabase/supabase-js@2.45.4";

export const env = (name: string, fallback?: string): string => {
  const value = Deno.env.get(name) ?? fallback;
  if (value === undefined) throw new Error(`Missing env var ${name}`);
  return value;
};

// Public URL of the landing page, e.g. https://example.com
export const SITE_URL = () => env("SITE_URL").replace(/\/$/, "");
// Public base URL of the edge functions, e.g. https://<ref>.supabase.co/functions/v1
export const FUNCTIONS_URL = () =>
  env("FUNCTIONS_URL", `${env("SUPABASE_URL")}/functions/v1`).replace(/\/$/, "");

export const db = (): SupabaseClient =>
  createClient(env("SUPABASE_URL"), env("SUPABASE_SERVICE_ROLE_KEY"), {
    auth: { persistSession: false },
  });

export const corsHeaders = () => ({
  "Access-Control-Allow-Origin": env("ALLOWED_ORIGIN", "*"),
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
});

export const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders(), "Content-Type": "application/json" },
  });

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export const normalizeEmail = (raw: unknown): string | null => {
  if (typeof raw !== "string") return null;
  const email = raw.trim().toLowerCase();
  return email.length <= 254 && EMAIL_RE.test(email) ? email : null;
};

const escapeHtml = (s: string) =>
  s.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!
  );

const render = (template: string, vars: Record<string, string>, html = true) =>
  template.replace(/\{\{\s*(\w+)\s*\}\}/g, (_, key) => {
    const value = vars[key] ?? "";
    return html ? escapeHtml(value) : value;
  });

/**
 * Sends a stored email template through Resend and records it in email_log.
 * Returns false (never throws) so a mail outage cannot lose a signup.
 */
export async function sendTemplate(
  client: SupabaseClient,
  key: string,
  to: string,
  vars: Record<string, string>,
): Promise<boolean> {
  const { data: tpl, error } = await client
    .from("email_templates")
    .select("subject, html")
    .eq("key", key)
    .maybeSingle();

  if (error || !tpl) {
    await client.from("email_log").insert({
      email: to, template_key: key, error: `template missing: ${error?.message ?? key}`,
    });
    return false;
  }

  const allVars = { brand_name: env("BRAND_NAME"), site_url: SITE_URL(), ...vars };
  try {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env("RESEND_API_KEY")}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: env("EMAIL_FROM"),
        reply_to: env("EMAIL_REPLY_TO", env("EMAIL_FROM")),
        to: [to],
        subject: render(tpl.subject, allVars, false),
        html: render(tpl.html, allVars),
      }),
    });
    const body = await res.json().catch(() => ({}));
    await client.from("email_log").insert({
      email: to,
      template_key: key,
      provider_id: body?.id ?? null,
      error: res.ok ? null : JSON.stringify(body).slice(0, 500),
    });
    return res.ok;
  } catch (e) {
    await client.from("email_log").insert({ email: to, template_key: key, error: String(e) });
    return false;
  }
}

export const actionUrl = (action: string, token: string) =>
  `${FUNCTIONS_URL()}/waitlist-action?action=${action}&token=${token}`;
