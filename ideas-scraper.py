import sys
from types import ModuleType

# Universal mock for mcp and mcp.types to bypass LiteLLM internal imports
class MagicMockType(ModuleType):
    def __getattr__(self, name):
        return object

mcp_mock = MagicMockType("mcp")
mcp_types_mock = MagicMockType("mcp.types")

sys.modules["mcp"] = mcp_mock
sys.modules["mcp.types"] = mcp_types_mock

import os
import json
import re
import urllib.request
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from github import Github, GithubException
from pydantic import BaseModel, Field

load_dotenv()

from crewai import Agent, Crew, Process, Task, TaskOutput, LLM
from crewai.tools import tool

# Set up xAI Grok LLM
grok_llm = LLM(
    model=os.getenv("MODEL"),
    base_url=os.getenv("XAI_API_BASE"),
    api_key=os.getenv("XAI_API_KEY"),
    # A full Tailwind landing page runs 15-30 KB; leave headroom so pages are not cut off mid-file.
    max_tokens=int(os.getenv("LLM_MAX_TOKENS", "16000"))
)

# Resolve output paths against this file so the script works from any working directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IDEAS_DIR = os.path.join(BASE_DIR, "ideas")
NUM_IDEAS = 10
MIN_PAGE_BYTES = 1500
PAGE_GUARDRAIL_RETRIES = 3

# ---------------------------------------------------------------------------
# 1. ENHANCED SCRAPERS WITH PAIN-POINT FILTERING
# ---------------------------------------------------------------------------

@tool("High-Quality Reddit Pain-Point Scraper")
def scrape_reddit_quality(subreddit: str = "SaaS") -> str:
    """Scrapes Reddit for posts containing explicit user complaints, tool requests, or workflows that suck."""
    url = f"https://www.reddit.com/r/{subreddit}/search.json?q=wish+there+was+OR+alternative+to+OR+hate+when+OR+looking+for+tool&restrict_sr=1&sort=relevance&limit=25"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            posts = data['data']['children']
            results = []
            for post in posts:
                pdata = post['data']
                # Skip pinned posts, empty text, or auto-mod threads
                if pdata.get('stickied') or not pdata.get('selftext') or len(pdata.get('selftext')) < 40:
                    continue
                title = pdata['title']
                text = pdata['selftext'][:400].replace('\n', ' ')
                score = pdata.get('score', 0)
                comments = pdata.get('num_comments', 0)
                results.append(f"### [Reddit - r/{subreddit}] {title} (Upvotes: {score}, Comments: {comments})\nPain Detail: {text}\n")
            
            return "\n".join(results[:12]) if results else "No actionable pain points found on Reddit."
    except Exception as e:
        return f"Error scraping Reddit: {str(e)}"


@tool("High-Quality Hacker News Scraper")
def scrape_hacker_news_quality(query: str = "Ask HN") -> str:
    """Scrapes Hacker News discussions for real user complaints, software gaps, and manual workflow complaints."""
    url = f"https://hn.algolia.com/api/v1/search?query={query}&tags=story&numericFilters=num_comments>10&hitsPerPage=20"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            hits = response.json().get('hits', [])
            results = []
            for item in hits:
                title = item.get('title', '')
                num_comments = item.get('num_comments', 0)
                points = item.get('points', 0)
                story_url = item.get('url', '')
                
                # Filter for problem-focused threads
                if any(kw in title.lower() for kw in ['ask hn', 'why is', 'what do you use', 'alternative', 'how to']):
                    results.append(f"### [Hacker News] {title} (Points: {points}, Comments: {num_comments})\nLink: {story_url}\n")
            
            return "\n".join(results[:10]) if results else "No high-comment HN discussions found."
        return f"Hacker News API returned status {response.status_code}"
    except Exception as e:
        return f"Error scraping Hacker News: {str(e)}"


@tool("Product Hunt Gap Scraper")
def scrape_product_hunt_quality() -> str:
    """Scrapes top trending products from Product Hunt RSS feed to find gaps and derivative software concepts."""
    url = "https://www.producthunt.com/feed"
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'xml')
            entries = soup.find_all('entry')[:20]
            results = []
            for entry in entries:
                title = entry.title.text if entry.title else ""
                summary = entry.summary.text if entry.summary else ""
                # Clean up HTML tags in summary
                clean_summary = BeautifulSoup(summary, "html.parser").get_text()[:300]
                if len(clean_summary) > 50:
                    results.append(f"### [Product Hunt Launch] {title}\nSummary: {clean_summary}\n")
            return "\n".join(results[:10]) if results else "No Product Hunt items found."
        return f"Product Hunt RSS returned status {response.status_code}"
    except Exception as e:
        return f"Error scraping Product Hunt: {str(e)}"

# ---------------------------------------------------------------------------
# 2. VALIDATION & SAVE (plain Python - the save no longer depends on an agent choosing to call a tool)
# ---------------------------------------------------------------------------

# Matches one HTML comment at a time (non-greedy, may span lines) so `<!-- Hero -->` ... `-->` is never
# treated as a single giant comment.
HTML_COMMENT_RE = re.compile(r'<!--(.*?)-->', re.DOTALL)

# Placeholder phrasing inside a comment. Structural labels such as `<!-- Hero Section -->` or
# `<!-- Features -->` are normal markup and must NOT be rejected; only stand-ins for missing content are.
PLACEHOLDER_RE = re.compile(
    r'(?:rest of|todo|tailored|placeholder|insert|same as above|repeat(?:ed)? for|'
    r'(?:content|code|markup|copy|html|sections?|cards?|items?|tiers?)\s+(?:goes\s+|go\s+)?here|'
    r'add (?:more|your|the|remaining)|\.\.\.|…)',
    re.IGNORECASE,
)


def sanitize_slug(folder_name: str) -> str:
    """Turns any folder name into a clean, lowercase URL slug."""
    slug = folder_name.lower().strip().replace(' ', '-').replace('_', '-')
    slug = re.sub(r'[^a-z0-9\-]', '', slug)
    return re.sub(r'-{2,}', '-', slug).strip('-')


def extract_html(raw: str) -> str:
    """Pulls the HTML document out of an LLM answer (drops markdown fences and any chatter around it)."""
    text = raw.strip()
    fenced = re.search(r'```(?:html)?\s*(.*?)```', text, re.DOTALL | re.IGNORECASE)
    if fenced and '<html' in fenced.group(1).lower():
        text = fenced.group(1).strip()
    start = re.search(r'<!DOCTYPE html|<html', text, re.IGNORECASE)
    if start:
        text = text[start.start():]
    end = text.lower().rfind('</html>')
    if end != -1:
        text = text[:end + len('</html>')]
    return text


def validate_html(html_content: str) -> list[str]:
    """Returns a list of QA problems with the page. An empty list means the page passed."""
    problems = []
    size = len(html_content.encode('utf-8'))
    lowered = html_content.lower()

    if size < MIN_PAGE_BYTES:
        problems.append(f"Page is too short ({size} bytes, minimum {MIN_PAGE_BYTES}). Provide FULL HTML for every section.")
    if not lowered.lstrip().startswith(('<!doctype html', '<html')):
        problems.append("Page must start with `<!DOCTYPE html>`.")
    if '</html>' not in lowered:
        problems.append("Page is truncated: closing `</html>` tag is missing. Output the complete document.")
    if '<head' not in lowered:
        problems.append("Page is missing a `<head>` section.")
    if 'cdn.tailwindcss.com' not in lowered:
        problems.append("Page must load Tailwind CSS from `https://cdn.tailwindcss.com`.")
    if re.search(r'<body[^>]*>\s*</body>', lowered):
        problems.append("Page has an empty `<body>` tag.")
    if '<form' not in lowered:
        problems.append("Page needs an interactive waitlist `<form>`.")
    for section in ('pricing', 'faq'):
        if section not in lowered:
            problems.append(f"Page is missing the {section.upper()} section.")

    placeholders = [c.strip() for c in HTML_COMMENT_RE.findall(html_content) if PLACEHOLDER_RE.search(c)]
    if placeholders:
        shown = "; ".join(f"<!-- {c[:60]} -->" for c in placeholders[:3])
        problems.append(f"Page contains placeholder comments instead of real content: {shown}. Replace them with actual HTML.")

    return problems


def save_landing_page(folder_name: str, html_content: str) -> str:
    """Writes ideas/<slug>/index.html locally, then commits it to GitHub when credentials are present."""
    clean_slug = sanitize_slug(folder_name)
    if not clean_slug:
        return f"FAILED: folder name '{folder_name}' does not produce a usable slug."

    local_dir = os.path.join(IDEAS_DIR, clean_slug)
    local_file_path = os.path.join(local_dir, "index.html")
    try:
        os.makedirs(local_dir, exist_ok=True)
        with open(local_file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
    except OSError as e:
        return f"FAILED: could not write {local_file_path}: {e}"

    github_token = os.getenv("GITHUB_TOKEN")
    github_repo_name = os.getenv("GITHUB_REPO")
    if not github_token or not github_repo_name:
        return f"Saved locally to {local_file_path} (GitHub sync skipped: GITHUB_TOKEN or GITHUB_REPO not set)."

    repo_file_path = f"ideas/{clean_slug}/index.html"
    commit_message = f"Add landing page for: {clean_slug}"
    try:
        repo = Github(github_token).get_repo(github_repo_name)
        try:
            contents = repo.get_contents(repo_file_path)
            repo.update_file(contents.path, commit_message, html_content, contents.sha)
            status_msg = "updated existing file"
        except GithubException as e:
            if e.status != 404:
                raise
            repo.create_file(repo_file_path, commit_message, html_content)
            status_msg = "created new file"
        return f"Saved locally to {local_file_path} and synced to GitHub {github_repo_name}/{repo_file_path} ({status_msg})."
    except Exception as e:
        return f"Saved locally to {local_file_path}, but GitHub sync failed: {e}"


def landing_page_guardrail(output: TaskOutput) -> tuple[bool, str]:
    """CrewAI task guardrail: on failure the agent is re-prompted with the problems listed here."""
    html_content = extract_html(output.raw)
    problems = validate_html(html_content)
    if problems:
        return False, "REJECTED BY QA:\n- " + "\n- ".join(problems)
    return True, html_content


@tool("Inspect Ideas Directory")
def inspect_ideas_directory() -> str:
    """Reads the local `ideas/` directory and reports every `index.html` with its size and QA result."""
    if not os.path.isdir(IDEAS_DIR):
        return f"No `ideas/` directory found at {IDEAS_DIR}."
    lines = []
    for folder in sorted(os.listdir(IDEAS_DIR)):
        if not os.path.isdir(os.path.join(IDEAS_DIR, folder)):
            continue  # e.g. ideas_validation_report.md written by validate-ideas.py
        page = os.path.join(IDEAS_DIR, folder, "index.html")
        if not os.path.isfile(page):
            lines.append(f"- {folder}: MISSING index.html")
            continue
        with open(page, encoding="utf-8") as f:
            problems = validate_html(f.read())
        status = "PASS" if not problems else "FAIL: " + " | ".join(problems)
        lines.append(f"- {folder}: {os.path.getsize(page)} bytes - {status}")
    return f"{len(lines)} folder(s) in {IDEAS_DIR}:\n" + "\n".join(lines) if lines else "The `ideas/` directory is empty."

# ---------------------------------------------------------------------------
# 3. STRUCTURED HAND-OFF BETWEEN RESEARCH AND BUILD
# ---------------------------------------------------------------------------

class IdeaBrief(BaseModel):
    slug: str = Field(description="Lowercase, hyphenated folder name, e.g. 'invoice-reconciler'")
    product_name: str
    target_audience: str
    pain_point: str = Field(description="The specific user complaint, with the source it came from")
    key_features: list[str] = Field(description="3-5 concrete features")


class IdeaList(BaseModel):
    ideas: list[IdeaBrief]

# ---------------------------------------------------------------------------
# 4. AGENTS
# ---------------------------------------------------------------------------

idea_hunter = Agent(
    role="Principal Market Researcher",
    goal=f"Scrape community sources and filter out noise to generate {NUM_IDEAS} deeply validated, high-demand SaaS ideas.",
    backstory="You are a seasoned startup founder who finds explicit user pain points and feature requests online.",
    tools=[scrape_reddit_quality, scrape_hacker_news_quality, scrape_product_hunt_quality],
    llm=grok_llm,
    verbose=True
)

developer_agent = Agent(
    role="Lead Frontend Engineer",
    goal="Write one complete, non-truncated, standalone HTML landing page for the product brief you are given.",
    backstory=(
        "You are a full-stack engineer who builds complete landing pages using Tailwind CSS CDN. "
        "You write full HTML code for every section and NEVER use HTML comment placeholders."
    ),
    llm=grok_llm,
    verbose=True
)

qa_auditor = Agent(
    role="Quality Assurance Inspector",
    goal="Verify from the real files on disk that every folder in `ideas/` contains a full, valid landing page.",
    backstory="You never assume a file exists - you inspect the `ideas/` directory with your tool and report exactly what is there.",
    tools=[inspect_ideas_directory],
    llm=grok_llm,
    verbose=True
)

# ---------------------------------------------------------------------------
# 5. TASKS
# ---------------------------------------------------------------------------

task_find_quality_ideas = Task(
    description=(
        "1. Execute all 3 scraper tools.\n"
        f"2. Extract EXACTLY {NUM_IDEAS} distinct, specific SaaS/software concepts with real community demand.\n"
        "3. For each idea provide: `slug`, `product_name`, `target_audience`, `pain_point`, and `key_features`."
    ),
    expected_output=f"{NUM_IDEAS} validated product briefs.",
    output_pydantic=IdeaList,
    agent=idea_hunter
)


def build_page_task(idea: IdeaBrief) -> Task:
    features = "\n".join(f"  - {f}" for f in idea.key_features)
    return Task(
        description=(
            "Build a COMPLETE standalone `index.html` landing page for this product:\n"
            f"- slug: {idea.slug}\n"
            f"- product_name: {idea.product_name}\n"
            f"- target_audience: {idea.target_audience}\n"
            f"- pain_point: {idea.pain_point}\n"
            f"- key_features:\n{features}\n\n"
            "Requirements:\n"
            "1. Full HTML5 document with `<head>` and Tailwind CSS from `<script src=\"https://cdn.tailwindcss.com\"></script>`.\n"
            "2. Sections: Hero with a waitlist `<form>`, Problem vs. Solution grid, 3 Feature cards, Pricing tiers, FAQ, footer.\n"
            "3. Write real, product-specific copy for every section. Never use placeholder comments such as "
            "`<!-- rest of content here -->`.\n"
            "4. Your final answer must be ONLY the HTML document, from `<!DOCTYPE html>` to `</html>`."
        ),
        expected_output="A single complete HTML document starting with <!DOCTYPE html> and ending with </html>.",
        agent=developer_agent,
        guardrail=landing_page_guardrail,
        guardrail_max_retries=PAGE_GUARDRAIL_RETRIES
    )


task_verify_ideas_dir = Task(
    description=(
        "Call `Inspect Ideas Directory` and report on every folder it lists. "
        "Only report what the tool returns - do not assume any file exists."
    ),
    expected_output="A QA status log listing each landing page with its size and PASS/FAIL result.",
    agent=qa_auditor
)

# ---------------------------------------------------------------------------
# 6. EXECUTE THE SWARM
# ---------------------------------------------------------------------------

def run_research() -> list[IdeaBrief]:
    crew = Crew(agents=[idea_hunter], tasks=[task_find_quality_ideas], process=Process.sequential, verbose=True)
    result = crew.kickoff()
    if result.pydantic is None:
        raise RuntimeError(f"Idea research did not return structured briefs. Raw output:\n{result.raw}")
    return result.pydantic.ideas[:NUM_IDEAS]


def build_pages(ideas: list[IdeaBrief]) -> list[str]:
    """Builds and saves one page per idea. One failed page never stops the others."""
    report = []
    for i, idea in enumerate(ideas, start=1):
        idea.slug = sanitize_slug(idea.slug)
        print(f"\n=== [{i}/{len(ideas)}] Building landing page: {idea.slug} ===")
        try:
            crew = Crew(agents=[developer_agent], tasks=[build_page_task(idea)], verbose=True)
            html_content = extract_html(crew.kickoff().raw)
            problems = validate_html(html_content)
            if problems:
                status = "REJECTED BY QA: " + " | ".join(problems)
            else:
                status = save_landing_page(idea.slug, html_content)
        except Exception as e:
            status = f"FAILED: {e}"
        print(f"[{idea.slug}] {status}")
        report.append(f"[{idea.slug}] {status}")
    return report


def run_qa() -> str:
    crew = Crew(agents=[qa_auditor], tasks=[task_verify_ideas_dir], process=Process.sequential, verbose=True)
    return crew.kickoff().raw


if __name__ == "__main__":
    ideas = run_research()
    print(f"\nResearch produced {len(ideas)} idea(s): {', '.join(i.slug for i in ideas)}")
    build_report = build_pages(ideas)
    qa_report = run_qa()

    print("\n\n================ BUILD REPORT ================\n")
    print("\n".join(build_report))
    print("\n================ QA AUDIT ================\n")
    print(qa_report)
