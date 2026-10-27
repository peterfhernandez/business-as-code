"""GitHub first, local fallback - never both (CLAUDE.md section 4.3)."""
import os
from pathlib import Path

from github import Github, GithubException

REPO_ROOT = Path(__file__).resolve().parent.parent


def _github_repo():
    token = os.getenv("GITHUB_TOKEN")
    repo_name = os.getenv("GITHUB_REPO") or os.getenv("GITHUB_REPO_NAME")
    if not token or not repo_name:
        return None
    return Github(token).get_repo(repo_name)


def _ensure_branch(repo, branch: str) -> None:
    try:
        repo.get_branch(branch)
    except GithubException:
        base = repo.get_branch(repo.default_branch)
        repo.create_git_ref(ref=f"refs/heads/{branch}", sha=base.commit.sha)


def save_file(path: str, content: str, message: str, branch: str) -> str:
    """Commits `path` to `branch` on GitHub, or writes it locally if that is unavailable."""
    try:
        repo = _github_repo()
        if repo is not None:
            _ensure_branch(repo, branch)
            try:
                existing = repo.get_contents(path, ref=branch)
                repo.update_file(path, message, content, existing.sha, branch=branch)
            except GithubException as e:
                if e.status != 404:
                    raise
                repo.create_file(path, message, content, branch=branch)
            return f"github:{repo.full_name}@{branch}/{path}"
    except GithubException as e:
        print(f"[storage] GitHub upload failed ({e.status}); saving locally instead.")

    target = REPO_ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"local:{target}"


def load_file(path: str, branch: str) -> str | None:
    """Reads `path` from the local checkout, else from `branch` on GitHub."""
    local = REPO_ROOT / path
    if local.exists():
        return local.read_text(encoding="utf-8")
    repo = _github_repo()
    if repo is None:
        return None
    try:
        return repo.get_contents(path, ref=branch).decoded_content.decode("utf-8")
    except GithubException:
        return None
