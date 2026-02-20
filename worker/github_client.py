"""
GitHub API client for the task queue.

The worker writes task JSON files to a GitHub repo's tasks/ directory.
The local daemon polls for these files, executes them, and deletes them.
"""

from __future__ import annotations

import base64
import logging

import httpx

logger = logging.getLogger("claude-code-slack.github")

GITHUB_API = "https://api.github.com"


class GitHubClient:
    def __init__(self, token: str, repo: str, branch: str = "main"):
        self.token = token
        self.repo = repo
        self.branch = branch

    def _headers(self) -> dict:
        h = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def read_file(self, path: str) -> str | None:
        """Read a file from the GitHub repo. Returns content or None."""
        url = f"{GITHUB_API}/repos/{self.repo}/contents/{path}"
        params = {"ref": self.branch}

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._headers(), params=params)

            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                logger.error(f"GitHub read error {path}: {resp.status_code}")
                return None

            data = resp.json()
            return base64.b64decode(data["content"]).decode("utf-8")

    async def write_file(self, path: str, content: str, message: str) -> bool:
        """Create or update a file. Returns True on success."""
        url = f"{GITHUB_API}/repos/{self.repo}/contents/{path}"

        # Get current SHA if file exists (required for updates)
        sha = await self._get_file_sha(path)

        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": self.branch,
        }
        if sha:
            payload["sha"] = sha

        async with httpx.AsyncClient() as client:
            resp = await client.put(url, headers=self._headers(), json=payload)

            if resp.status_code in (200, 201):
                logger.info(f"Wrote {path} to GitHub")
                return True

            logger.error(f"GitHub write error {path}: {resp.status_code}")
            return False

    async def delete_file(self, path: str, sha: str, message: str) -> bool:
        """Delete a file from the repo."""
        url = f"{GITHUB_API}/repos/{self.repo}/contents/{path}"
        payload = {
            "message": message,
            "sha": sha,
            "branch": self.branch,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.request(
                "DELETE", url, headers=self._headers(), json=payload
            )
            return resp.status_code in (200, 204)

    async def _get_file_sha(self, path: str) -> str | None:
        """Get the SHA of a file (needed for updates)."""
        url = f"{GITHUB_API}/repos/{self.repo}/contents/{path}"
        params = {"ref": self.branch}

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._headers(), params=params)
            if resp.status_code == 200:
                return resp.json().get("sha")
            return None
