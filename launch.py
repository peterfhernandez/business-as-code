"""Inverse build - Day 1 launch crew.

Inverse build: produce the storefront and delivery rails (landing page,
waitlist, onboarding emails, pricing plans) before any product code.

    python launch.py --brand "Acme" --domain acme.example \
        --idea-file ideas/invoice-chaser/index.html

Agents only write into a sandbox branch (launch/<slug>). Anything outbound -
DNS, Stripe, sending email, deploying - happens in provision.py behind
explicit human approval.
"""
import sys
from types import ModuleType


class MagicMockType(ModuleType):
    def __getattr__(self, name):
        return object


mcp_mock = MagicMockType("mcp")
mcp_types_mock = MagicMockType("mcp.types")

sys.modules["mcp"] = mcp_mock
sys.modules["mcp.types"] = mcp_types_mock

import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

from crewai import LLM, Agent, Crew, Process, Task  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from launchkit.storage import save_file  # noqa: E402
from launchkit.validation import (  # noqa: E402
    REQUIRED_EMAILS,
    email_template_errors,
    inject_runtime,
    landing_page_errors,
    slugify,
    strip_code_fences,
)

load_dotenv()

llm = LLM(model=os.getenv("MODEL"), api_key=os.getenv("XAI_API_KEY"))

# ---------------------------------------------------------------------------
# Structured hand-offs (CLAUDE.md 4.2: slug, product_name, target_audience,
# pain_point travel with every task)
# ---------------------------------------------------------------------------


class Plan(BaseModel):
    key: str = Field(description="lowercase plan id, letters only, e.g. starter, pro")
    name: str
    monthly_price_usd: float
    features: list[str]
    highlighted: bool = False


class FAQ(BaseModel):
    question: str
    answer: str


class ProductSpec(BaseModel):
    product_name: str
    slug: str
    tagline: str
    target_audience: str
    pain_point: str
    value_props: list[str]
    mvp_features: list[str]
    plans: list[Plan]
    faq: list[FAQ]


class EmailTemplate(BaseModel):
    key: str
    subject: str
    html: str


class EmailPack(BaseModel):
    templates: list[EmailTemplate]


class QAReport(BaseModel):
    approved: bool
    issues: list[str]


# ---------------------------------------------------------------------------
# Guardrails: deterministic Python checks between hand-offs
# ---------------------------------------------------------------------------


def spec_guardrail(result):
    spec: ProductSpec = result.pydantic
    problems = []
    if not 2 <= len(spec.plans) <= 3:
        problems.append("Offer exactly 2 or 3 plans.")
    for plan in spec.plans:
        if not re.fullmatch(r"[a-z]{2,20}", plan.key):
            problems.append(f"Plan key '{plan.key}' must be 2-20 lowercase letters.")
        if plan.monthly_price_usd <= 0:
            problems.append(f"Plan '{plan.key}' needs a positive monthly price.")
    if len(spec.faq) < 4:
        problems.append("Write at least 4 FAQ entries.")
    if problems:
        return False, " ".join(problems)
    return True, result.pydantic


def email_templates(pack: "EmailPack") -> dict[str, dict]:
    # Agents write [[token]] because CrewAI treats {...} in task text as inputs;
    # the edge functions render {{token}}.
    def mustache(s: str) -> str:
        return re.sub(r"\[\[\s*(\w+)\s*\]\]", r"{{\1}}", s)

    return {
        t.key: {"subject": mustache(t.subject), "html": mustache(t.html)}
        for t in pack.templates
    }


def email_guardrail(result):
    errors = email_template_errors(email_templates(result.pydantic))
    return (False, " ".join(errors)) if errors else (True, result.pydantic)


def landing_guardrail(result):
    html = strip_code_fences(result.raw)
    errors = landing_page_errors(html)
    return (False, " ".join(errors)) if errors else (True, html)


# ---------------------------------------------------------------------------
# Agent swarm: discrete roles (CLAUDE.md 4.1)
# ---------------------------------------------------------------------------

product_lead = Agent(
    role="Product Lead",
    goal="Turn a rough idea into a sharp, testable launch spec with pricing hypotheses.",
    backstory=(
        "You have launched dozens of micro-SaaS products. You define the smallest "
        "offer that proves people will pay, and you price for validation, not perfection."
    ),
    llm=llm,
    verbose=True,
)

copywriter = Agent(
    role="Marketing & Copywriter",
    goal="Write plain, specific onboarding emails that earn a reply.",
    backstory=(
        "You write short, warm transactional email. No hype, no filler. Every email has "
        "one job and one link."
    ),
    llm=llm,
    verbose=True,
)

frontend_dev = Agent(
    role="Frontend Developer",
    goal="Build a complete, fast, accessible single-file landing page.",
    backstory=(
        "You ship production HTML with Tailwind. You never leave stubs or comments in "
        "place of real markup."
    ),
    llm=llm,
    verbose=True,
)

qa_inspector = Agent(
    role="QA Inspector",
    goal="Block anything misleading, broken, insecure or legally risky before staging.",
    backstory=(
        "You review launch pages for honesty (no fake testimonials, user counts or logos), "
        "accessibility, broken anchors and leaked secrets."
    ),
    llm=llm,
    verbose=True,
)

# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

task_spec = Task(
    description=(
        "Brand name: {brand}. Domain: {domain}.\n"
        "Rough idea:\n{idea}\n\n"
        "Write the launch spec. Use the brand name as product_name and a URL slug of it. "
        "Name one narrow target audience and their single sharpest pain point. List 3-5 "
        "MVP features only. Propose 2-3 monthly plans with prices that test willingness "
        "to pay (mark one highlighted). Write 4-6 FAQ entries answering real objections, "
        "including what happens before launch (waitlist, nothing charged)."
    ),
    expected_output="A ProductSpec.",
    output_pydantic=ProductSpec,
    guardrail=spec_guardrail,
    guardrail_max_retries=3,
    agent=product_lead,
)

email_keys = "\n".join(
    f"- {key}: must contain {', '.join('[[' + v + ']]' for v in vars_) or 'no links'}"
    for key, vars_ in REQUIRED_EMAILS.items()
)
task_emails = Task(
    description=(
        "Write the automated onboarding emails for {brand} using the spec. One template "
        "per key below. Use [[brand_name]] for the product name. Links must use the exact "
        "[[token]] placeholders shown - they are filled in at send time. html is a "
        "short inline-styled HTML fragment (no <html> wrapper, no images). Every "
        "marketing email ends with an unsubscribe link.\n"
        f"{email_keys}\n\n"
        "Purpose of each: waitlist_confirm = confirm the signup (double opt-in); "
        "waitlist_welcome = thank them and ask what hurts most; onboarding_survey "
        "(day 2) = ask one question about the pain point and current workaround; "
        "onboarding_early_access (day 5) = offer locked-in launch pricing; "
        "billing_portal_link = link to manage the subscription (expires in 24h); "
        "subscription_started / subscription_canceled = receipts in plain words, and "
        "say replies reach a human at {support_email}."
    ),
    expected_output="An EmailPack with one template per required key.",
    output_pydantic=EmailPack,
    guardrail=email_guardrail,
    guardrail_max_retries=3,
    context=[task_spec],
    agent=copywriter,
)

task_landing = Task(
    description=(
        "Build the complete landing page for {brand} ({domain}) from the spec. Output only "
        "the HTML document.\n"
        "Requirements:\n"
        "- Full document with <head>, <script src=\"https://cdn.tailwindcss.com\"></script>, "
        "meta description and Open Graph tags.\n"
        "- Hero with the pain point, tagline and the waitlist form: "
        "<form id=\"waitlist-form\"> with <input type=\"email\" name=\"email\" required> "
        "and a submit button. Do not add action/onsubmit or any JavaScript for forms; it "
        "is wired up automatically.\n"
        "- Features grid from the MVP features.\n"
        "- <section id=\"pricing\"> with one card per plan; each card's button has "
        "data-plan=\"<plan key>\" and says 'Reserve launch price'.\n"
        "- <section id=\"faq\"> with every FAQ entry.\n"
        "- <footer> with links to mailto:{support_email} and mailto:{hello_email}.\n"
        "- No testimonials, logos, user counts or claims you cannot back up."
    ),
    expected_output="A complete standalone HTML document.",
    guardrail=landing_guardrail,
    guardrail_max_retries=3,
    context=[task_spec],
    agent=frontend_dev,
)

task_qa = Task(
    description=(
        "Review the landing page and onboarding emails. Reject (approved=false) for: fake "
        "social proof, promises the MVP spec does not cover, broken in-page anchors, "
        "missing alt text or labels, secrets or API keys, or anything that charges money "
        "before launch. List each issue concretely."
    ),
    expected_output="A QAReport.",
    output_pydantic=QAReport,
    context=[task_spec, task_emails, task_landing],
    agent=qa_inspector,
)


def idea_text(args) -> str:
    if args.idea:
        return args.idea
    raw = Path(args.idea_file).read_text(encoding="utf-8")
    raw = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)).strip()[:6000]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--brand", required=True)
    parser.add_argument("--domain", required=True)
    idea = parser.add_mutually_exclusive_group(required=True)
    idea.add_argument("--idea")
    idea.add_argument("--idea-file")
    args = parser.parse_args()

    domain = args.domain.lower().strip()
    inputs = {
        "brand": args.brand,
        "domain": domain,
        "idea": idea_text(args),
        "support_email": f"support@{domain}",
        "hello_email": f"hello@{domain}",
    }

    crew = Crew(
        agents=[product_lead, copywriter, frontend_dev, qa_inspector],
        tasks=[task_spec, task_emails, task_landing, task_qa],
        process=Process.sequential,
        verbose=True,
    )
    crew.kickoff(inputs=inputs)

    spec: ProductSpec = task_spec.output.pydantic
    emails: EmailPack = task_emails.output.pydantic
    qa: QAReport = task_qa.output.pydantic
    slug = slugify(spec.slug or spec.product_name)
    spec.slug = slug
    branch = f"launch/{slug}"
    plan_prefix = slug.replace("-", "_") + "_"

    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    page = inject_runtime(
        strip_code_fences(task_landing.output.raw),
        {
            "functionsUrl": f"{supabase_url}/functions/v1" if supabase_url else "/functions/v1",
            "anonKey": os.getenv("SUPABASE_ANON_KEY", ""),
            "planPrefix": plan_prefix,
        },
    )

    brand = {
        "brand": args.brand,
        "domain": domain,
        "slug": slug,
        "emails": {"hello": inputs["hello_email"], "support": inputs["support_email"]},
        "spec": spec.model_dump(),
        "stripe_prices": [
            {
                "lookup_key": f"{plan_prefix}{p.key}_monthly",
                "product_name": f"{args.brand} {p.name}",
                "unit_amount": round(p.monthly_price_usd * 100),
                "currency": "usd",
                "interval": "month",
            }
            for p in spec.plans
        ],
        "qa": qa.model_dump(),
    }

    base = f"launch/{slug}"
    saved = [
        save_file(f"{base}/index.html", page, f"Add {args.brand} landing page", branch),
        save_file(
            f"{base}/emails.json",
            json.dumps(email_templates(emails), indent=2),
            f"Add {args.brand} onboarding emails",
            branch,
        ),
        save_file(
            f"{base}/brand.json",
            json.dumps(brand, indent=2),
            f"Add {args.brand} launch spec and pricing",
            branch,
        ),
    ]

    print("\n================ LAUNCH BUNDLE ================")
    for location in saved:
        print(f"  {location}")
    print(f"\nQA: {'APPROVED' if qa.approved else 'CHANGES REQUESTED'}")
    for issue in qa.issues:
        print(f"  - {issue}")
    print(
        f"\nNext: review the bundle, then run\n"
        f"  python provision.py --bundle {base} --branch {branch}\n"
        "Every outbound step there asks for your approval."
    )
    return 0 if qa.approved else 1


if __name__ == "__main__":
    sys.exit(main())
