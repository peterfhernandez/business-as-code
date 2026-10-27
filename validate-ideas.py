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

load_dotenv()

from crewai import Agent, Crew, Process, Task, LLM
from crewai.tools import tool

# Set up xAI Grok LLM
grok_llm = LLM(
    model=os.getenv("MODEL"),
    base_url=os.getenv("XAI_API_BASE"),
    api_key=os.getenv("XAI_API_KEY")
)

# Resolve paths against this file so the script works from any working directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IDEAS_DIR = os.path.join(BASE_DIR, "ideas")
REPORT_FILENAME = "ideas_validation_report.md"

# ---------------------------------------------------------------------------
# 1. DEFINE TOOLS FOR READING & REPORTING
# ---------------------------------------------------------------------------

@tool("Fetch Local Ideas Folder")
def list_local_ideas() -> str:
    """Reads all generated ideas and landing page summaries from the local `ideas/` directory."""
    if not os.path.exists(IDEAS_DIR):
        return "No local `ideas/` directory found. Please run ideas-scraper.py first."

    ideas_summary = []
    for folder in sorted(os.listdir(IDEAS_DIR)):
        folder_path = os.path.join(IDEAS_DIR, folder)
        if os.path.isdir(folder_path):
            index_path = os.path.join(folder_path, "index.html")
            if os.path.exists(index_path):
                with open(index_path, "r", encoding="utf-8") as f:
                    content = f.read()[:500]  # Read header/hero context
                ideas_summary.append(f"### Slug: {folder}\nHTML Preview:\n{content}\n")

    return "\n---\n".join(ideas_summary) if ideas_summary else "No ideas found in directory."


def extract_markdown(raw: str) -> str:
    """Drops a markdown code fence the LLM may have wrapped the whole report in."""
    text = raw.strip()
    fenced = re.fullmatch(r'```(?:markdown|md)?\s*(.*?)```', text, re.DOTALL | re.IGNORECASE)
    return fenced.group(1).strip() if fenced else text


def save_validation_report(report_md: str) -> str:
    """Commits ideas/ideas_validation_report.md to GitHub; only if that is not possible, writes it locally instead.
    The report is never written to both places."""
    repo_file_path = f"ideas/{REPORT_FILENAME}"
    github_token = os.getenv("GITHUB_TOKEN")
    github_repo_name = os.getenv("GITHUB_REPO")
    if not github_token or not github_repo_name:
        fallback_reason = "GITHUB_TOKEN or GITHUB_REPO not set"
    else:
        try:
            repo = Github(github_token).get_repo(github_repo_name)
            try:
                contents = repo.get_contents(repo_file_path)
                repo.update_file(contents.path, "Update Market Validation Report", report_md, contents.sha)
                status_msg = "updated existing file"
            except GithubException as e:
                if e.status != 404:
                    raise
                repo.create_file(repo_file_path, "Add Market Validation Report", report_md)
                status_msg = "created new file"
            return f"Report saved to GitHub {github_repo_name}/{repo_file_path} ({status_msg})."
        except Exception as e:
            fallback_reason = f"GitHub save failed: {e}"

    report_path = os.path.join(IDEAS_DIR, REPORT_FILENAME)
    try:
        os.makedirs(IDEAS_DIR, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_md)
    except OSError as e:
        return f"FAILED: {fallback_reason}, and could not write {report_path}: {e}"
    return f"Report saved locally to {report_path} ({fallback_reason})."

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
        "4. Return the complete ranked report as markdown. Your final answer is saved to disk as-is, "
        "so do not include any commentary outside the report."
    ),
    expected_output="A complete ranked markdown report containing full market, tech, difficulty, and cost metrics for every idea.",
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
    # Saved from Python rather than via an agent tool call, so the report is always written.
    save_status = save_validation_report(extract_markdown(result.raw))
    print("\n\n================ VALIDATION REPORT ================\n")
    print(result.raw)
    print(f"\n{save_status}")
