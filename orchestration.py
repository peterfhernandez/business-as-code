import sys
from types import ModuleType

class MagicMockType(ModuleType):
    def __getattr__(self, name):
        return object

mcp_mock = MagicMockType("mcp")
mcp_types_mock = MagicMockType("mcp.types")

sys.modules["mcp"] = mcp_mock
sys.modules["mcp.types"] = mcp_types_mock

import os
import subprocess
from github import Github, GithubException
from crewai import Agent, Crew, Process, Task, LLM
from crewai.tools import tool

# Set access to Github
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "your-github-personal-access-token")
GITHUB_REPO = os.getenv("GITHUB_REPO") or os.getenv("GITHUB_REPO_NAME")  # "username/repo"

# Configure xAI LLM
grok_llm = LLM(
    model=os.getenv("MODEL"),  # 'xai/' prefix routes through xAI Grok
    api_key=os.getenv("XAI_API_KEY")
)

# ---------------------------------------------------------------------------
# 1. DEFINE CUSTOM AGENT TOOLS (Terminal Execution & GitHub Actions)
# ---------------------------------------------------------------------------

@tool("Terminal Command Runner")
def execute_terminal_command(command: str) -> str:
    """Executes a terminal/shell command on the local machine or cloud runner.
    Use this to run tests, build projects, or install dependencies.
    """
    # Safety Check: Prevent destructive global operations
    forbidden_commands = ["rm -rf /", "mkfs", "dd"]
    if any(forbidden in command for forbidden in forbidden_commands):
        return "Error: Command rejected due to safety policy."

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            return f"Command Output:\n{result.stdout}"
        else:
            return f"Command Failed (Exit Code {result.returncode}):\n{result.stderr}"
    except Exception as e:
        return f"Execution Error: {str(e)}"


@tool("GitHub Commit and Pull Request Creator")
def create_github_pull_request(branch_name: str, file_path: str, file_content: str, commit_message: str, pr_title: str) -> str:
    """Pushes code directly to a GitHub repository branch and opens a Pull Request."""
    if not GITHUB_TOKEN or GITHUB_TOKEN == "your-github-personal-access-token":
        return "Error: Valid GITHUB_TOKEN environment variable is required."
    if not GITHUB_REPO:
        return "Error: GITHUB_REPO (or GITHUB_REPO_NAME) environment variable is required, in the format 'username/repo'."

    try:
        gh = Github(GITHUB_TOKEN)
        repo = gh.get_repo(GITHUB_REPO)
        default_branch = repo.default_branch
        
        # 1. Create a new branch off main
        main_ref = repo.get_git_ref(f"heads/{default_branch}")
        try:
            repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=main_ref.object.sha)
        except GithubException as e:
            if e.status != 422:
                raise
            # 422: branch already exists

        # 2. Update or Create the File
        try:
            existing_file = repo.get_contents(file_path, ref=branch_name)
            repo.update_file(
                path=file_path,
                message=commit_message,
                content=file_content,
                sha=existing_file.sha,
                branch=branch_name
            )
        except GithubException as e:
            if e.status != 404:
                raise
            repo.create_file(
                path=file_path,
                message=commit_message,
                content=file_content,
                branch=branch_name
            )

        # 3. Create Pull Request
        pr = repo.create_pull(
            title=pr_title,
            body=f"Automated PR submitted by Agent Swarm.\n\nChanges made to `{file_path}`.",
            head=branch_name,
            base=default_branch
        )
        return f"Successfully created Pull Request #{pr.number}: {pr.html_url}"

    except Exception as e:
        return f"GitHub Integration Error: {str(e)}"

# ---------------------------------------------------------------------------
# 2. ASSIGN TOOLS TO AGENTS
# ---------------------------------------------------------------------------

developer_agent = Agent(
    role="Lead Developer",
    goal="Write production-ready code and commit changes directly to GitHub via PRs.",
    backstory="You are a senior full-stack developer who builds modular apps and manages Git version control.",
    tools=[execute_terminal_command, create_github_pull_request],
    llm=grok_llm,
    verbose=True
)

qa_agent = Agent(
    role="QA Auditor & Automation Engineer",
    goal="Run terminal tests, verify code execution, and check GitHub PRs for security or code bugs.",
    backstory="You are a strict QA engineer who runs automated test suites in the terminal to verify builds before deployment.",
    tools=[execute_terminal_command],
    llm=grok_llm,
    verbose=True
)

chief_coordinator = Agent(
    role="Chief Coordinator",
    goal="Organize tasks and ensure work gets successfully pushed to GitHub.",
    backstory="You supervise the team, making sure code passes QA checks before requesting human launch sign-off.",
    llm=grok_llm,
    verbose=True
)

# ---------------------------------------------------------------------------
# 3. EXECUTION TASKS
# ---------------------------------------------------------------------------

task_dev = Task(
    description=(
        "Create an HTML landing page file `index.html` with Tailwind CSS styling and a waitlist form. "
        "Use the 'GitHub Commit and Pull Request Creator' tool to push the code to a new branch called 'feature/landing-page' "
        "and open a Pull Request."
    ),
    expected_output="URL to the created GitHub Pull Request.",
    agent=developer_agent
)

task_test = Task(
    description=(
        "Use the 'Terminal Command Runner' tool to execute 'git status' and check local workspace files, "
        "then run any syntax or validation checks on the code."
    ),
    expected_output="Terminal test output report confirming build integrity.",
    agent=qa_agent
)

swarm = Crew(
    agents=[chief_coordinator, developer_agent, qa_agent],
    tasks=[task_dev, task_test],
    process=Process.sequential,
    verbose=True
)

if __name__ == "__main__":
    result = swarm.kickoff()
    print("\n\n================ SWARM OUTPUT ================\n")
    print(result)