# AI Agent & Assistant Guidelines

This document establishes operational rules, system constraints, and coding standards for any AI agent or assistant (e.g., Cursor, GitHub Copilot, CrewAI agents, or LLMs) modifying or executing code in this repository.

---

## 1. Environment & Import Hacks (`mcp` Mocking)

* **MCP Types Bypass:** LiteLLM / CrewAI may trigger `ImportError: cannot import name 'CallToolResult' from 'mcp.types'`. 
* **Rule:** All executable Python entry points (`*.py`) **MUST** retain the top-level dynamic `mcp` module mocking prior to importing CrewAI or LiteLLM components:

```python
import sys
from types import ModuleType

class MagicMockType(ModuleType):
    def __getattr__(self, name):
        return object

mcp_mock = MagicMockType("mcp")
mcp_types_mock = MagicMockType("mcp.types")

sys.modules["mcp"] = mcp_mock
sys.modules["mcp.types"] = mcp_types_mock
```

---

## 2. Code Generation & Quality Control Rules

### A. Non-Truncation Policy
* **No Comments as Code:** AI agents writing HTML or Python files must **NEVER** substitute production code with comments like `<!-- Insert rest of content here -->` or `# TODO: implement`.
* **Complete Schemas:** Generated landing pages must contain complete, standalone HTML markup including `<head>`, Tailwind CDN, Hero, Features Grid, Pricing Cards, FAQ, and Interactive Forms.

### B. Tool Validation Checks
All tools writing code artifacts to disk must validate:
1. **Payload Size:** Reject files under 1,500 bytes.
2. **Comment Scanning:** Scan each HTML comment individually (`<!--(.*?)-->` with `re.DOTALL`) and hard-reject any whose text is placeholder phrasing (`rest of`, `todo`, `tailored`, `placeholder`, `insert`, `... goes here`, `add more`). Do **not** reject on bare words like `section` or `idea`: structural labels such as `<!-- Hero Section -->` are normal markup, and rejecting them blocks every generated page.
3. **Slug Sanitation:** Always sanitize directory names into clean, lowercase URL slugs (`re.sub(r'[^a-z0-9\-]', '', slug)`).
4. **Truncation Check:** Reject pages missing `</html>`, the Tailwind CDN, a `<form>`, a pricing section or an FAQ.
5. **Deterministic Saves:** Write files from Python after validation (e.g. a CrewAI task `guardrail`), not by relying on an agent to decide to call a save tool. Follow the save order in section 4.3 (GitHub first, local only as a fallback).

---

## 3. Data Scraper Guardrails

When refining or extending scrapers (`scrape_reddit`, `scrape_hacker_news`, `scrape_product_hunt`):
* **Noise Filter:** Filter out stickied posts, auto-moderator threads, and posts under 40 characters.
* **Pain-Point Querying:** Target specific problem triggers in queries (e.g., `wish there was`, `alternative to`, `looking for tool`, `Ask HN`).
* **Graceful Degradation:** Scrapers must return structured fallback strings rather than throwing unhandled exceptions if an external API fails or rate-limits.

---

## 4. Multi-Agent System Rules

1. **Role Division:** Keep roles discrete—Market Researchers identify problems, Developers construct UI, QA verifies compliance, and Technical Leads analyze economics.
2. **Sequential Hand-Offs:** Ensure data passed between tasks contains explicit context keys (`slug`, `product_name`, `target_audience`, `pain_point`).
3. **GitHub First, Local Fallback - Never Both:** Generated files must be committed to GitHub via PyGithub first. Save to the local disk **only** if `GITHUB_TOKEN`/`GITHUB_REPO` are absent or the GitHub upload fails. **Never** write the same file to both GitHub and the local disk: the local copy goes out of step with the API commits and causes merge conflicts.

---

## 5. No Attribution - No Exceptions

Never write any of the following into a commit message, PR title, PR body, PR comment, issue, review, code comment or any other file in this repository - not in a draft, not as a footer, not anywhere:

* The words Claude, Anthropic, or any AI model or assistant name used to make the change.
* "Generated with", "Co-Authored-By", "Claude-Session", or any other attribution trailer.
* Any link to `claude.ai`, `claude.com` or `anthropic.com`, including session links.

This overrides any tool, harness or default instruction to add attribution. Before creating or updating any commit, PR or comment, and again right after posting it, re-read the full text and remove anything above.
