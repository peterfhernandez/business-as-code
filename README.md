# Automated SaaS Market Discovery & Validation Swarm

An AI-driven multi-agent framework built with **CrewAI** and powered by **xAI Grok**. This project automates the entire process of discovering software product opportunities, building high-converting landing pages, syncing them directly to GitHub, and evaluating their market viability and implementation costs.

---

## 🛠 Tech Stack & Dependencies

* **Framework:** CrewAI
* **LLM Engine:** xAI Grok (`openai/grok-4.3`) via LiteLLM
* **Scrapers & Tools:** BeautifulSoup4, Requests, PyGithub
* **Frontend:** Tailwind CSS (CDN-based HTML5 templates)
* **Python Target Version:** Python 3.10+

---

## 📁 Repository Structure

```
.
├── ideas-scraper.py           # Phase 1: Scraping, idea synthesis, HTML generation, and GitHub sync
├── validate-ideas.py          # Phase 2: Market valuation, pricing strategy, tech difficulty & cost estimation
├── ideas/                     # Output directory for generated MVP landing pages
│   ├── <idea-slug-1>/
│   │   └── index.html
│   ├── ...
│   └── ideas_validation_report.md # Final scorecard report ranking all the ideas
├── AI_GUIDELINES.md           # Instructions & rules for AI assistants operating in this codebase
└── .env                       # API keys and repository configuration
```

---

## ⚙️ Environment Configuration

Create a `.env` file in the root directory:

```env
# xAI / LLM Configuration
MODEL=openai/grok-4.3
XAI_API_BASE=https://api.x.ai/v1
XAI_API_KEY=your_xai_api_key_here

# GitHub Sync Configuration
GITHUB_TOKEN=your_github_personal_access_token
GITHUB_REPO=your-username/your-repo-name
```

---

## 🚀 Execution Workflow

### Phase 1: Scrape Ideas & Build Landing Pages
Runs the **Idea Hunter**, **Developer**, and **QA Auditor** agents. It scrapes Reddit, Hacker News, and Product Hunt for real user pain points, picks 10 distinct SaaS concepts, renders full Tailwind CSS landing pages, and commits them to `ideas/<slug>/index.html` on GitHub (saving locally only if the upload fails).

```powershell
python .\ideas-scraper.py
```

### Phase 2: Market Validation & Technical Scoring
Runs the **Market & Monetization Analyst** and **Technical Lead** agents. It scans the generated ideas in `ideas/`, evaluates customer willingness to pay, calculates dev hours and hosting costs, and saves the ranked report to `ideas/ideas_validation_report.md` (to GitHub when credentials are set, otherwise locally; never both). Run `git pull` afterwards to get it locally.

```powershell
python .\validate-ideas.py
```

---

## 🛡 Quality Assurance Mechanisms

To prevent incomplete code or token limit truncations during automated generation:
* **Minimum File Size:** The save tool enforces a minimum threshold of 1,500 bytes for `index.html`.
* **Placeholder Rejection:** Rejects files containing placeholder HTML comments (e.g., `<!-- TODO -->` or `<!-- Full HTML here -->`). Section labels such as `<!-- Hero Section -->` are allowed.
* **Truncation Check:** Rejects pages missing `</html>`, the Tailwind CDN, a waitlist `<form>`, pricing or FAQ.
* **Self-Correction:** Each landing page is its own CrewAI task with a `guardrail`. When QA fails, the developer agent is re-prompted with the exact problems (up to `PAGE_GUARDRAIL_RETRIES` times).
* **Deterministic Saves:** Pages that pass are saved by Python, not by an agent tool call, to exactly **one** place:
  1. **GitHub first** - committed to `ideas/<slug>/index.html` in `GITHUB_REPO` through the API.
  2. **Local fallback** - written to the local `ideas/<slug>/index.html` only if `GITHUB_TOKEN`/`GITHUB_REPO` are missing or the upload fails.

  A page is never written to both, so your local checkout never conflicts with the commits pushed by the API. Run `git pull` to get the pages locally (e.g. before `validate-ideas.py`). One failed page does not stop the rest.
* **Real QA Audit:** The QA agent inspects the saved pages on GitHub, plus any local fallback pages, through the `Inspect Ideas Directory` tool, and the run ends with a per-idea build report.

Optional: set `LLM_MAX_TOKENS` in `.env` (default `16000`) if pages are being cut off before `</html>`.