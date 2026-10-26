import os
import json
import urllib.request
import requests
from bs4 import BeautifulSoup
from crewai import Agent, Crew, Process, Task, LLM
from crewai.tools import tool

# Set up xAI Grok LLM
grok_llm = LLM(
    model="xai/grok-2",
    api_key=os.getenv("XAI_API_KEY")
)

# ---------------------------------------------------------------------------
# 1. DEFINE THE 3 SCRAPER TOOLS
# ---------------------------------------------------------------------------

@tool("Reddit Pain-Point Scraper")
def scrape_reddit(subreddit: str = "SaaS") -> str:
    """Scrapes recent posts from target subreddits to find product requests and user pain points."""
    url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=10"
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
    url = f"https://hn.algolia.com/api/v1/search_by_date?query={query}&tags=story&hitsPerPage=10"
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
            entries = soup.find_all('entry')[:10]
            results = []
            for entry in entries:
                title = entry.title.text if entry.title else "No Title"
                content = entry.summary.text[:200] if entry.summary else "No Summary"
                results.append(f"- **Product Hunt:** {title}\n  **Summary:** {content}\n")
            return "\n".join(results) if results else "No Product Hunt items found."
        return f"Product Hunt RSS returned status {response.status_code}"
    except Exception as e:
        return f"Error scraping Product Hunt: {str(e)}"

# ---------------------------------------------------------------------------
# 2. DEFINE THE IDEA HUNTER AGENT
# ---------------------------------------------------------------------------

idea_hunter = Agent(
    role="Trend & Problem Hunter",
    goal="Scrape Reddit, Hacker News, and Product Hunt to discover user pain points and pick a high-demand MVP business idea.",
    backstory=(
        "You are an expert market research agent. You troll online forums and launch sites, "
        "analyze what users are complaining about or asking for, and extract a highly feasible "
        "software concept that can be built by developers in under 3 days."
    ),
    tools=[scrape_reddit, scrape_hacker_news, scrape_product_hunt],
    llm=grok_llm,
    verbose=True
)

chief_coordinator = Agent(
    role="Chief Coordinator",
    goal="Take the selected business idea from the Idea Hunter and translate it into strict dev specs.",
    backstory="You are the technical project manager who scopes out the build and manages task handoffs.",
    llm=grok_llm,
    verbose=True
)

developer_agent = Agent(
    role="Lead Developer",
    goal="Build the landing page and waitlist integration for the chosen business idea.",
    backstory="You write production-ready HTML, Tailwind CSS, and JS code.",
    llm=grok_llm,
    verbose=True
)

# ---------------------------------------------------------------------------
# 3. DEFINE TASKS
# ---------------------------------------------------------------------------

task_find_idea = Task(
    description=(
        "Use your 3 scraper tools (Reddit, Hacker News, and Product Hunt) to search for real user problems and trending software gaps. "
        "Synthesize the findings and pick the SINGLE BEST business idea that an AI agent team can build in 3 days. "
        "Output the idea title, core target audience, key features, and why it was selected."
    ),
    expected_output="A structured Business Brief containing the winning business concept with market validation context.",
    agent=idea_hunter
)

task_scope = Task(
    description="Take the selected business idea from the Idea Hunter and create a 1-page feature spec and technical architecture.",
    expected_output="A technical requirement document ready for development.",
    agent=chief_coordinator
)

task_build = Task(
    description="Build an `index.html` file with Tailwind CSS styling and a waitlist form for the selected business idea.",
    expected_output="Clean HTML code for the product landing page.",
    agent=developer_agent
)

# ---------------------------------------------------------------------------
# 4. EXECUTE THE SWARM
# ---------------------------------------------------------------------------

swarm = Crew(
    agents=[idea_hunter, chief_coordinator, developer_agent],
    tasks=[task_find_idea, task_scope, task_build],
    process=Process.sequential,
    verbose=True
)

if __name__ == "__main__":
    result = swarm.kickoff()
    print("\n\n================ SWARM OUTPUT ================\n")
    print(result)