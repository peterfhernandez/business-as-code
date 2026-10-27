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

# ---------------------------------------------------------------------------
# 2. SAVE TOOL WITH MANDATORY QUALITY CHECKS
# ---------------------------------------------------------------------------

@tool("Save and Validate Landing Page")
def save_and_validate_page(folder_name: str, html_content: str) -> str:
    """
    Saves an index.html file locally and to GitHub ONLY if it passes content validation checks:
    - Rejects pages under 1,500 bytes.
    - Rejects pages containing HTML comment placeholders like <!-- ... -->.
    - Rejects pages with empty body tags.
    """
    clean_slug = re.sub(r'[^a-z0-9\-]', '', folder_name.lower().replace(' ', '-'))
    
    # QA CHECK 1: File Size Check
    if len(html_content.encode('utf-8')) < 1500:
        return f"REJECTED BY QA: Generated HTML for '{clean_slug}' is too short ({len(html_content)} chars). You must provide FULL HTML code with all sections."

    # QA CHECK 2: Comment Placeholder Check
    if re.search(r'<!--.*(?:tailored|section|rest of|todo|idea).*-->', html_content, re.IGNORECASE):
        return f"REJECTED BY QA: Generated HTML for '{clean_slug}' contains comment placeholders! Write actual HTML content instead of comments."

    # QA CHECK 3: Empty Body Check
    if "<body></body>" in html_content.replace(" ", ""):
        return f"REJECTED BY QA: Generated HTML for '{clean_slug}' has an empty body tag!"

    try:
        # 1. Local Save
        local_dir = os.path.join("ideas", clean_slug)
        os.makedirs(local_dir, exist_ok=True)
        local_file_path = os.path.join(local_dir, "index.html")
        
        with open(local_file_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # 2. GitHub Push
        github_token = os.getenv("GITHUB_TOKEN")
        github_repo_name = os.getenv("GITHUB_REPO")
        
        if not github_token or not github_repo_name:
            return f"PASSED QA & Saved locally to `{local_file_path}` (GitHub sync skipped: missing credentials)."

        gh = Github(github_token)
        repo = gh.get_repo(github_repo_name)
        repo_file_path = f"ideas/{clean_slug}/index.html"
        commit_message = f"Add full high-converting landing page for: {clean_slug}"

        try:
            contents = repo.get_contents(repo_file_path)
            repo.update_file(contents.path, commit_message, html_content, contents.sha)
            status_msg = "Updated existing page on GitHub."
        except Exception:
            repo.create_file(repo_file_path, commit_message, html_content)
            status_msg = "Created new page on GitHub."

        return f"PASSED QA! Saved locally (`{local_file_path}`) and synced to GitHub (`{repo_file_path}`): {status_msg}"
    except Exception as e:
        return f"Saved locally to ideas/{folder_name}/index.html, but GitHub sync failed: {str(e)}"

# ---------------------------------------------------------------------------
# 3. AGENTS WITH QA ENFORCEMENT
# ---------------------------------------------------------------------------

idea_hunter = Agent(
    role="Principal Market Researcher",
    goal="Scrape community sources and filter out noise to generate 10 deeply validated, high-demand SaaS ideas.",
    backstory="You are a seasoned startup founder who finds explicit user pain points and feature requests online.",
    tools=[scrape_reddit_quality, scrape_hacker_news_quality, scrape_product_hunt_quality],
    llm=grok_llm,
    verbose=True
)

developer_agent = Agent(
    role="Lead Frontend Engineer",
    goal="Write complete, non-truncated HTML index files for each idea and save them using `Save and Validate Landing Page`.",
    backstory=(
        "You are a full-stack engineer who builds complete landing pages using Tailwind CSS CDN. "
        "You write full HTML code for every section and NEVER use HTML comment placeholders."
    ),
    tools=[save_and_validate_page],
    llm=grok_llm,
    verbose=True
)

qa_auditor = Agent(
    role="Quality Assurance Inspector",
    goal="Verify that all 10 files in the `ideas/` directory contain full HTML markup and zero placeholder comments.",
    backstory="You verify that files rendered in `ideas/` have real HTML content and valid page structures.",
    llm=grok_llm,
    verbose=True
)

# ---------------------------------------------------------------------------
# 4. TASKS
# ---------------------------------------------------------------------------

task_find_10_quality_ideas = Task(
    description=(
        "1. Execute all 3 scraper tools.\n"
        "2. Extract EXACTLY 10 distinct, specific SaaS/software concepts with real community demand.\n"
        "3. Provide a list of 10 items, each containing: `slug`, `product_name`, `target_audience`, `pain_point`, and `key_features`."
    ),
    expected_output="A list of 10 validated product briefs with folder slugs.",
    agent=idea_hunter
)

task_build_10_quality_pages = Task(
    description=(
        "FOR EACH OF THE 10 BUSINESS IDEAS:\n"
        "1. Construct a COMPLETE standalone `index.html` file with full Tailwind CSS markup.\n"
        "2. Required sections: Hero with Waitlist Input, Problem vs. Solution Grid, 3 Feature Cards, Pricing Tiers, FAQ.\n"
        "3. Call `Save and Validate Landing Page` with the folder slug and HTML code.\n"
        "4. IF THE TOOL RETURNS 'REJECTED BY QA', FIX THE HTML AND CALL THE TOOL AGAIN until all 10 ideas are saved successfully."
    ),
    expected_output="All 10 landing pages successfully passed QA validation and saved.",
    agent=developer_agent
)

task_verify_ideas_dir = Task(
    description=(
        "Inspect the `ideas/` folder on disk to confirm that 10 subdirectories exist and each `index.html` "
        "has a file size greater than 1,500 bytes with valid HTML markup inside."
    ),
    expected_output="A QA status log confirming all 10 pages are non-empty and deployed.",
    agent=qa_auditor
)

# ---------------------------------------------------------------------------
# 5. EXECUTE THE SWARM
# ---------------------------------------------------------------------------

swarm = Crew(
    agents=[idea_hunter, developer_agent, qa_auditor],
    tasks=[task_find_10_quality_ideas, task_build_10_quality_pages, task_verify_ideas_dir],
    process=Process.sequential,
    verbose=True
)

if __name__ == "__main__":
    result = swarm.kickoff()
    print("\n\n================ QUALITY CONTROL SWARM OUTPUT ================\n")
    print(result)