"""Quality gates for generated artifacts (CLAUDE.md section 2B)."""
import json
import re
from pathlib import Path

MIN_BYTES = 1500
PLACEHOLDER_RE = re.compile(
    r"rest of|todo|tailored|placeholder|insert|goes here|add more", re.IGNORECASE
)

# Every onboarding email and the variables it must use.
REQUIRED_EMAILS = {
    "waitlist_confirm": ["confirm_url", "unsubscribe_url"],
    "waitlist_welcome": ["feedback_url", "unsubscribe_url"],
    "onboarding_survey": ["feedback_url", "unsubscribe_url"],
    "onboarding_early_access": ["pricing_url", "unsubscribe_url"],
    "billing_portal_link": ["portal_url"],
    "subscription_started": [],
    "subscription_canceled": [],
}

RUNTIME_JS = Path(__file__).with_name("runtime.js")


def slugify(value: str) -> str:
    slug = re.sub(r"\s+", "-", value.strip().lower())
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    return re.sub(r"-{2,}", "-", slug).strip("-")


def placeholder_comments(html: str) -> list[str]:
    return [
        c.strip()
        for c in re.findall(r"<!--(.*?)-->", html, re.DOTALL)
        if PLACEHOLDER_RE.search(c)
    ]


def landing_page_errors(html: str) -> list[str]:
    errors = []
    if len(html.encode("utf-8")) < MIN_BYTES:
        errors.append(f"Page is under {MIN_BYTES} bytes; it looks truncated.")
    lowered = html.lower()
    checks = {
        "</html>": "Missing closing </html> tag.",
        "cdn.tailwindcss.com": "Missing the Tailwind CDN script.",
        "<form": "Missing a <form>.",
        'id="waitlist-form"': 'The waitlist form must have id="waitlist-form".',
        'name="email"': 'The waitlist form needs an input with name="email".',
        'id="pricing"': 'Missing a pricing section with id="pricing".',
        'id="faq"': 'Missing an FAQ section with id="faq".',
        "data-plan=": "Pricing buttons need data-plan attributes.",
    }
    errors += [msg for needle, msg in checks.items() if needle not in lowered]
    for comment in placeholder_comments(html):
        errors.append(f"Placeholder comment found: <!--{comment[:60]}-->")
    return errors


def email_template_errors(templates: dict[str, dict]) -> list[str]:
    errors = []
    for key, variables in REQUIRED_EMAILS.items():
        tpl = templates.get(key)
        if not tpl:
            errors.append(f"Missing email template '{key}'.")
            continue
        for var in variables:
            if f"{{{{{var}}}}}" not in tpl.get("html", "").replace(" ", ""):
                errors.append(f"Template '{key}' must link {{{{{var}}}}}.")
        if placeholder_comments(tpl.get("html", "")) or PLACEHOLDER_RE.search(
            tpl.get("subject", "")
        ):
            errors.append(f"Template '{key}' contains placeholder text.")
    return errors


def strip_code_fences(text: str) -> str:
    match = re.search(r"```(?:html)?\s*(.*?)```", text, re.DOTALL)
    return (match.group(1) if match else text).strip()


def inject_runtime(html: str, config: dict) -> str:
    """Wires the page to the edge functions so agents never hand-write API calls."""
    script = (
        f"<script>window.LAUNCH_CONFIG = {json.dumps(config)};</script>\n"
        f"<script>\n{RUNTIME_JS.read_text()}\n</script>\n"
    )
    index = html.lower().rfind("</body>")
    if index == -1:
        index = html.lower().rfind("</html>")
    return html[:index] + script + html[index:]
