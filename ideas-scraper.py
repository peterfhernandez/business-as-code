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
from github import Github

from dotenv import load_dotenv

load_dotenv()

from crewai import Agent, Crew, Process, Task, LLM
from crewai.tools import tool

# Set up xAI Grok LLM
grok_llm = LLM(
    model=os.getenv("MODEL"),
    base_url=os.getenv("XAI_API_BASE"),
    api_key=os.getenv("XAI_API_KEY")
)

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


@tool("Save Landing Page and Sync to GitHub")
def save_and_push_idea(folder_name: str, html_content: str) -> str:
    """Saves an index.html landing page inside `ideas/<folder_name>/index.html` locally and on GitHub."""
    try:
        # Sanitize folder name slug
        clean_slug = re.sub(r'[^a-z0-9\-]', '', folder_name.lower().replace(' ', '-'))
        
        # 1. Local Save
        local_dir = os.path.join("ideas", clean_slug)
        os.makedirs(local_dir, exist_ok=True)
        local_file_path = os.path.join(local_dir, "index.html")
        
        with open(local_file_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # 2. GitHub Push
        github_token = os.getenv("GITHUB_TOKEN")
        github_repo_name = os.getenv("GITHUB_REPO_NAME")
        
        if not github_token or not github_repo_name:
            return f"Saved locally to {local_file_path} (GitHub sync skipped: missing credentials)."

        gh = Github(github_token)
        repo = gh.get_repo(github_repo_name)
        repo_file_path = f"ideas/{clean_slug}/index.html"
        commit_message = f"Add high-converting MVP landing page for: {clean_slug}"

        try:
            contents = repo.get_contents(repo_file_path)
            repo.update_file(contents.path, commit_message, html_content, contents.sha)
            status_msg = "Updated existing page on GitHub."
        except Exception:
            repo.create_file(repo_file_path, commit_message, html_content)
            status_msg = "Created new page on GitHub."

        return f"Successfully saved locally (`{local_file_path}`) and synced to GitHub (`{repo_file_path}`): {status_msg}"
    except Exception as e:
        return f"Saved locally to ideas/{folder_name}/index.html, but GitHub sync failed: {str(e)}"

@tool("Batch Save 10 Landing Pages")
def batch_save_ideas(ideas_json_str: str) -> str:
    """
    Accepts a JSON string array of 10 landing page objects and writes all 10 files locally and to GitHub.
    Expected JSON schema for ideas_json_str:
    [
        {"folder_name": "slug-1", "html_content": "<!DOCTYPE html>..."},
        {"folder_name": "slug-2", "html_content": "<!DOCTYPE html>..."}
    ]
    """
    try:
        ideas = json.loads(ideas_json_str)
        if not isinstance(ideas, list):
            return "Error: Input must be a JSON array of objects."
        
        results = []
        for item in ideas:
            folder_name = item.get("folder_name")
            html_content = item.get("html_content")
            if folder_name and html_content:
                res = save_and_push_idea.func(folder_name, html_content)
                results.append(f"[{folder_name}]: {res}")
        
        return "\n".join(results)
    except Exception as e:
        return f"Error parsing JSON or saving batch: {str(e)}"

# ---------------------------------------------------------------------------
# 2. AGENTS WITH QUALITY ASSURANCE GATEWAY
# ---------------------------------------------------------------------------

idea_hunter = Agent(
    role="Principal Market Researcher",
    goal="Scrape community sources and filter out noise to generate 10 deeply validated, high-demand SaaS ideas.",
    backstory=(
        "You are a seasoned startup finder. You ignore fluff posts and hunt for explicit user pain points "
        "(e.g., manual workarounds, tools people complain about, missing features). "
        "You demand concrete evidence before selecting a software concept."
    ),
    tools=[scrape_reddit_quality, scrape_hacker_news_quality, scrape_product_hunt_quality],
    llm=grok_llm,
    verbose=True
)

developer_agent = Agent(
    role="Lead Frontend Engineer",
    goal="Build high-converting, professional landing pages using Tailwind CSS for all 10 ideas.",
    backstory=(
        "You build slick, modern SaaS landing pages using HTML5, Tailwind CSS, and simple JS interactive forms. "
        "Every page you generate includes custom copy, hero visuals, problem breakdown, features, pricing, and FAQ. "
        "You NEVER use placeholders or incomplete HTML boilerplate."
    ),
    tools=[save_and_push_idea, batch_save_ideas],
    llm=grok_llm,
    verbose=True
)

qa_auditor = Agent(
    role="Design & QA Director",
    goal="Audit generated landing page files to ensure they meet visual, copy, and completeness criteria.",
    backstory=(
        "You are a strict product reviewer. You verify that landing pages have full text, modern Tailwind styling, "
        "no broken markup, functional call-to-actions, and distinct value propositions."
    ),
    llm=grok_llm,
    verbose=True
)

# ---------------------------------------------------------------------------
# 3. TASKS WITH QUALITY ENFORCEMENT
# ---------------------------------------------------------------------------

task_find_10_quality_ideas = Task(
    description=(
        "1. Execute all 3 scrapers (`High-Quality Reddit Scraper`, `High-Quality Hacker News Scraper`, and `Product Hunt Gap Scraper`).\n"
        "2. Analyze the extracted data and pick EXACTLY 10 distinct, highly specific SaaS/software business concepts.\n"
        "3. Reject generic ideas like 'AI Todo App' or 'Simple Blog Builder'. Pick specific high-value solutions.\n"
        "4. For each idea, produce:\n"
        "   - `slug`: clean folder name (e.g. `b2b-invoice-reconciler`)\n"
        "   - `title`: Catchy product name\n"
        "   - `target_audience`: Specific buyer persona\n"
        "   - `pain_point`: Real problem scraped from the forums\n"
        "   - `core_features`: 3 key capabilities\n"
    ),
    expected_output="A structured list of 10 fully validated product briefs derived directly from forum data.",
    agent=idea_hunter
)

task_build_10_quality_pages = Task(
    description=(
        "For EACH of the 10 ideas passed by the Market Researcher:\n"
        "1. Create a complete, standalone `index.html` file using Tailwind CSS CDN (`<script src='https://cdn.tailwindcss.com'></script>`).\n"
        "2. Mandatory Page Structure:\n"
        "   - **Hero Section**: Headline, subheadline, CTA button, and interactive email waitlist form.\n"
        "   - **Problem vs Solution Grid**: Explicitly contrasting current manual pain with your solution.\n"
        "   - **Features Section**: 3-4 distinct benefit cards with Lucide/Heroicon style SVG icons.\n"
        "   - **Pricing Section**: 2-3 pricing tiers with clear feature bullet points.\n"
        "   - **FAQ Section**: 3 accordion-style common questions answered.\n"
        "   - **Footer**: Branding and copyright.\n"
        "3. DO NOT use generic filler text or lorem ipsum. Tailor all copy directly to the specific business idea.\n"
        "4. Call `Batch Save 10 Landing Pages` to save all 10 ideas, passing their slugs and HTML strings.\n"
    ),
    expected_output="Confirmation that all 10 index.html pages were rendered with full copy and saved to GitHub.",
    agent=developer_agent
)

task_audit_and_verify = Task(
    description=(
        "Review the generated output from the Lead Frontend Engineer.\n"
        "1. Confirm that 10 distinct landing pages were generated and saved using the GitHub tool.\n"
        "2. Verify that none of the saved pages contain placeholder text, broken HTML, or unstyled elements.\n"
        "3. Produce a Quality Report summarizing the status of all 10 generated landing pages."
    ),
    expected_output="A QA Approval Report verifying the high-quality generation of all 10 landing pages.",
    agent=qa_auditor
)

# ---------------------------------------------------------------------------
# 4. EXECUTE THE SWARM
# ---------------------------------------------------------------------------

swarm = Crew(
    agents=[idea_hunter, developer_agent, qa_auditor],
    tasks=[task_find_10_quality_ideas, task_build_10_quality_pages, task_audit_and_verify],
    process=Process.sequential,
    verbose=True
)

if __name__ == "__main__":
    result = swarm.kickoff()
    print("\n\n================ QUALITY CONTROL SWARM OUTPUT ================\n")
    print(result)