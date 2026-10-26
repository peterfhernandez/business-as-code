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
import urllib.request
import requests
from bs4 import BeautifulSoup
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
# 1. SCRAPER TOOLS & GITHUB SAVER TOOL
# ---------------------------------------------------------------------------

@tool("Reddit Pain-Point Scraper")
def scrape_reddit(subreddit: str = "SaaS") -> str:
    """Scrapes recent posts from target subreddits to find product requests and user pain points."""
    url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=25"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            posts = data['data']['children']
            results = []
            for post in posts:
                title = post['data']['title']
                text = post['data']['selftext'][:250]
                results.append(f"- **Reddit Title:** {title}\n  **Details:** {text}\n")
            return "\n".join(results) if results else "No posts found."
    except Exception as e:
        return f"Error scraping Reddit: {str(e)}"


@tool("Hacker News Scraper")
def scrape_hacker_news(query: str = "Ask HN: What tools") -> str:
    """Scrapes top stories and 'Ask HN' discussions from Hacker News via official Algolia API."""
    url = f"https://hn.algolia.com/api/v1/search_by_date?query={query}&tags=story&hitsPerPage=20"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            hits = response.json().get('hits', [])
            results = []
            for item in hits:
                title = item.get('title', 'No Title')
                story_url = item.get('url', item.get('story_url', 'No URL'))
                points = item.get('points', 0)
                results.append(f"- **HN Post:** {title} (Points: {points})\n  **Link:** {story_url}\n")
            return "\n".join(results) if results else "No Hacker News posts found."
        return f"Hacker News API returned status {response.status_code}"
    except Exception as e:
        return f"Error scraping Hacker News: {str(e)}"


@tool("Product Hunt Scraper")
def scrape_product_hunt() -> str:
    """Scrapes current trending products from Product Hunt RSS feed to identify market gaps."""
    url = "https://www.producthunt.com/feed"
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'xml')
            entries = soup.find_all('entry')[:15]
            results = []
            for entry in entries:
                title = entry.title.text if entry.title else "No Title"
                content = entry.summary.text[:200] if entry.summary else "No Summary"
                results.append(f"- **Product Hunt:** {title}\n  **Summary:** {content}\n")
            return "\n".join(results) if results else "No Product Hunt items found."
        return f"Product Hunt RSS returned status {response.status_code}"
    except Exception as e:
        return f"Error scraping Product Hunt: {str(e)}"


@tool("Save Landing Page and Sync to GitHub")
def save_and_push_idea(folder_name: str, html_content: str) -> str:
    """
    Saves an index.html landing page inside `ideas/<folder_name>/index.html` 
    both on the local workstation and pushes the file directly to the GitHub repository.
    """
    try:
        # 1. Local Filesystem Save
        local_dir = os.path.join("ideas", folder_name)
        os.makedirs(local_dir, exist_ok=True)
        local_file_path = os.path.join(local_dir, "index.html")
        
        with open(local_file_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # 2. GitHub Push
        github_token = os.getenv("GITHUB_TOKEN")
        github_repo_name = os.getenv("GITHUB_REPO_NAME")  # Format: "username/repo-name"
        
        if not github_token or not github_repo_name:
            return f"Saved locally to {local_file_path}, but GITHUB_TOKEN or GITHUB_REPO_NAME is missing in .env."

        gh = Github(github_token)
        repo = gh.get_repo(github_repo_name)
        repo_file_path = f"ideas/{folder_name}/index.html"
        commit_message = f"Add landing page MVP for idea: {folder_name}"

        try:
            # Check if file exists on GitHub to update, or create new
            contents = repo.get_contents(repo_file_path)
            repo.update_file(contents.path, commit_message, html_content, contents.sha)
            status_msg = "Updated existing file on GitHub."
        except Exception:
            repo.create_file(repo_file_path, commit_message, html_content)
            status_msg = "Created new file on GitHub."

        return f"Successfully saved locally at `{local_file_path}` and synced to GitHub (`{repo_file_path}`): {status_msg}"
    except Exception as e:
        return f"Saved locally to {folder_name}/index.html, but GitHub sync failed: {str(e)}"

# ---------------------------------------------------------------------------
# 2. AGENT DEFINITIONS
# ---------------------------------------------------------------------------

idea_hunter = Agent(
    role="Trend & Problem Hunter",
    goal="Scrape Reddit, Hacker News, and Product Hunt to discover user pain points and pick 10 distinct MVP business ideas.",
    backstory=(
        "You are an expert market analyst who identifies high-potential software gaps online. "
        "You extract 10 separate actionable product ideas that can be validated with landing pages."
    ),
    tools=[scrape_reddit, scrape_hacker_news, scrape_product_hunt],
    llm=grok_llm,
    verbose=True
)

developer_agent = Agent(
    role="Lead Web Developer",
    goal="Generate production-ready HTML index files for all 10 business ideas and save them to the repository.",
    backstory=(
        "You write clean HTML5, Tailwind CSS, and embedded JavaScript waitlist forms. "
        "You save each generated page into its designated GitHub/local path using your tool."
    ),
    tools=[save_and_push_idea],
    llm=grok_llm,
    verbose=True
)

# ---------------------------------------------------------------------------
# 3. TASK DEFINITIONS
# ---------------------------------------------------------------------------

task_find_10_ideas = Task(
    description=(
        "Run all scraper tools across Reddit, Hacker News, and Product Hunt. "
        "Analyze real community complaints, feature requests, and gaps. "
        "Select exactly 10 distinct MVP business concepts. "
        "For each idea, output: \n"
        "1. Unique folder slug (e.g., `ai-podcast-summarizer`)\n"
        "2. Product Name & Value Proposition\n"
        "3. Core Target Audience & Key Features\n"
    ),
    expected_output="A list of 10 fully scoped business concepts with folder slugs.",
    agent=idea_hunter
)

task_build_10_pages = Task(
    description=(
        "For EACH of the 10 business ideas identified by the Idea Hunter: \n"
        "1. Design a complete, beautiful HTML landing page using CDN Tailwind CSS (`<script src='https://cdn.tailwindcss.com'></script>`).\n"
        "2. Include a hero section, feature grid, pricing tier preview, and an interactive waitlist email capture form.\n"
        "3. Call the `Save Landing Page and Sync to GitHub` tool for EACH idea, passing its slug (folder_name) and full `index.html` string.\n"
        "Ensure all 10 ideas are saved in `ideas/<folder_slug>/index.html`."
    ),
    expected_output="Confirmation that all 10 index.html files have been written locally and pushed to GitHub.",
    agent=developer_agent
)

# ---------------------------------------------------------------------------
# 4. EXECUTE THE SWARM
# ---------------------------------------------------------------------------

swarm = Crew(
    agents=[idea_hunter, developer_agent],
    tasks=[task_find_10_ideas, task_build_10_pages],
    process=Process.sequential,
    verbose=True
)

if __name__ == "__main__":
    result = swarm.kickoff()
    print("\n\n================ SWARM OUTPUT ================\n")
    print(result)