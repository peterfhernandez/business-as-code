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
# 1. DEFINE TOOLS FOR READING & REPORTING
# ---------------------------------------------------------------------------

@tool("Fetch Local Ideas Folder")
def list_local_ideas() -> str:
    """Reads all generated ideas and landing page summaries from the local `ideas/` directory."""
    ideas_dir = "ideas"
    if not os.path.exists(ideas_dir):
        return "No local `ideas/` directory found. Please run ideas-scraper.py first."

    ideas_summary = []
    for folder in os.listdir(ideas_dir):
        folder_path = os.path.join(ideas_dir, folder)
        if os.path.isdir(folder_path):
            index_path = os.path.join(folder_path, "index.html")
            if os.path.exists(index_path):
                with open(index_path, "r", encoding="utf-8") as f:
                    content = f.read()[:500]  # Read header/hero context
                ideas_summary.append(f"### Slug: {folder}\nHTML Preview:\n{content}\n")

    return "\n---\n".join(ideas_summary) if ideas_summary else "No ideas found in directory."


@tool("Save Validation Matrix Report")
def save_validation_report(report_md: str) -> str:
    """Saves the final validation report locally to `ideas_validation_report.md` and pushes it to GitHub."""
    report_filename = "ideas_validation_report.md"
    
    # 1. Local Save
    with open(report_filename, "w", encoding="utf-8") as f:
        f.write(report_md)

    # 2. GitHub Push
    github_token = os.getenv("GITHUB_TOKEN")
    github_repo_name = os.getenv("GITHUB_REPO")

    if not github_token or not github_repo_name:
        return f"Report saved locally to `{report_filename}` (GitHub sync skipped: missing credentials)."

    try:
        gh = Github(github_token)
        repo = gh.get_repo(github_repo_name)
        
        try:
            contents = repo.get_contents(report_filename)
            repo.update_file(contents.path, "Update Market Validation Report", report_md, contents.sha)
            status = "Updated existing report on GitHub."
        except Exception:
            repo.create_file(report_filename, "Add Market Validation Report", report_md)
            status = "Created new report on GitHub."

        return f"Report saved locally and pushed to GitHub (`{report_filename}`): {status}"
    except Exception as e:
        return f"Saved locally to `{report_filename}`, but GitHub push failed: {str(e)}"

# ---------------------------------------------------------------------------
# 2. DEFINE AGENTS
# ---------------------------------------------------------------------------

market_validator = Agent(
    role="Market & Monetization Analyst",
    goal="Evaluate buyer willingness-to-pay, market demand, and pricing potential for all the scraped ideas.",
    backstory=(
        "You are a SaaS market analyst. You analyze customer pain severity, evaluate B2B/B2C willingness to pay, "
        "and assign market interest scores based on economic value and problem urgency."
    ),
    tools=[list_local_ideas],
    llm=grok_llm,
    verbose=True
)

tech_estimator = Agent(
    role="Technical Lead & Cost Estimator",
    goal="Determine build difficulty, developer time, and monthly infrastructure running costs (LLMs, databases, hosting).",
    backstory=(
        "You are a Cloud Solutions Architect and Full-Stack Lead. You calculate implementation difficulty, "
        "estimate MVP dev hours, and break down expected API/hosting operating costs."
    ),
    llm=grok_llm,
    verbose=True
)

# ---------------------------------------------------------------------------
# 3. DEFINE TASKS
# ---------------------------------------------------------------------------

task_market_analysis = Task(
    description=(
        "1. Call `list_local_ideas` to load all the scraped product ideas.\n"
        "2. For each idea, evaluate:\n"
        "   - **Market Interest Score (0-100)**\n"
        "   - **Willingness to Pay**: Is the target market willing to pay? Estimated monthly price range (e.g., $19/mo or $99/mo B2B).\n"
        "   - **Target Customer Segment & Urgency**\n"
    ),
    expected_output="A structured market valuation for all the concepts found.",
    agent=market_validator
)

task_tech_and_ranking = Task(
    description=(
        "1. Combine market evaluations with technical architecture estimates for each idea.\n"
        "2. For each idea, detail:\n"
        "   - **Build Difficulty (1-10 Scale)**\n"
        "   - **Est. MVP Development Time** (e.g., 8 hours, 3 days, 2 weeks)\n"
        "   - **Est. Monthly Running Costs** (Breakdown: Cloud hosting, database, LLM API calls per 1k users)\n"
        "3. Rank all the scraped ideas from #1 (Highest ROI / Easiest Win) to lowest.\n"
        "4. Call `save_validation_report` to write `ideas_validation_report.md` locally and push to GitHub."
    ),
    expected_output="A ranked markdown report containing full market, tech, difficulty, and cost metrics saved to GitHub.",
    agent=tech_estimator
)

# ---------------------------------------------------------------------------
# 4. EXECUTE THE SWARM
# ---------------------------------------------------------------------------

swarm = Crew(
    agents=[market_validator, tech_estimator],
    tasks=[task_market_analysis, task_tech_and_ranking],
    process=Process.sequential,
    verbose=True
)

if __name__ == "__main__":
    result = swarm.kickoff()
    print("\n\n================ VALIDATION REPORT ================\n")
    print(result)