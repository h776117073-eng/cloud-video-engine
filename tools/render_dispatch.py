#!/usr/bin/env python3
"""Programmatic GitHub Actions dispatcher for Blender renders.

No browser is required. Store a GitHub fine-grained PAT in GITHUB_TOKEN.
Required repository permission: Actions -> Read and write.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

API_ROOT = "https://api.github.com"
API_VERSION = "2026-03-10"
DEFAULT_REPO = "h776117073-eng/cloud-video-engine"
DEFAULT_WORKFLOW = ".github/workflows/blender_render.yml"
DEFAULT_REF = "main"
DEFAULT_BLENDER_VERSION = "5.2.2"


class GitHubError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderResult:
    run_id: int
    status: str
    conclusion: str | None
    run_url: str
    artifact_id: int | None
    artifact_name: str | None
    artifact_download_url: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "conclusion": self.conclusion,
            "run_url": self.run_url,
            "artifact_id": self.artifact_id,
            "artifact_name": self.artifact_name,
            "artifact_download_url": self.artifact_download_url,
        }


class GitHubActionsClient:
    def __init__(self, token: str, repository: str, timeout: float = 30.0) -> None:
        if not token:
            raise ValueError("GITHUB_TOKEN is required.")
        if "/" not in repository or repository.count("/") != 1:
            raise ValueError("repository must be in OWNER/REPO form.")
        self.repository = repository
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "blender-cloud-render-agent/1.0",
            }
        )
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        expected: tuple[int, ...] = (200,),
        **kwargs: Any,
    ) -> requests.Response:
        response = self.session.request(
            method, f"{API_ROOT}{path}", timeout=self.timeout, **kwargs
        )
        if response.status_code not in expected:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text[:500]
            raise GitHubError(
                f"GitHub API {method} {path} returned {response.status_code}: {detail}"
            )
        return response

    def dispatch(
        self,
        *,
        workflow: str = DEFAULT_WORKFLOW,
        ref: str = DEFAULT_REF,
        script_path: str | None = None,
        script_base64: str | None = None,
        output_name: str = "render.mp4",
        blender_version: str = DEFAULT_BLENDER_VERSION,
    ) -> int:
        if bool(script_path) == bool(script_base64):
            raise ValueError("Provide exactly one of script_path or script_base64.")
        if not output_name.endswith(".mp4"):
            raise ValueError("output_name must end with .mp4.")
        if "/" in output_name or "\\" in output_name:
            raise ValueError("output_name must be a filename, not a path.")

        inputs: dict[str, str] = {
            "output_name": output_name,
            "blender_version": blender_version,
        }
        if script_path:
            inputs["script_path"] = script_path
        else:
            inputs["script_base64"] = script_base64 or ""

        before = datetime.now(timezone.utc)
        response = self.request(
            "POST",
            f"/repos/{self.repository}/actions/workflows/{workflow}/dispatches",
            expected=(200, 201, 204),
            json={"ref": ref, "inputs": inputs},
        )

        if response.status_code == 200 and response.content:
            payload = response.json()
            run_id = payload.get("workflow_run_id")
            if run_id:
                return int(run_id)

        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            runs = self.list_runs(workflow=workflow, branch=ref, event="workflow_dispatch")
            candidates = []
            for run in runs:
                created = run.get("created_at")
                if not created:
                    continue
                try:
                    created_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if created_at >= before:
                    candidates.append(run)
            if candidates:
                candidates.sort(key=lambda item: item.get("created_at", ""), reverse=True)
                return int(candidates[0]["id"])
            time.sleep(2)
        raise GitHubError("Workflow was dispatched but its run ID could not be discovered.")

    def get_run(self, run_id: int) -> dict[str, Any]:
        return self.request(
            "GET", f"/repos/{self.repository}/actions/runs/{run_id}"
        ).json()

    def list_runs(
        self,
        *,
        workflow: str,
        branch: str | None = None,
        event: str | None = None,
        per_page: int = 20,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"per_page": per_page}
        if branch:
            params["branch"] = branch
        if event:
            params["event"] = event
        return self.request(
            "GET",
            f"/repos/{self.repository}/actions/workflows/{workflow}/runs",
            params=params,
        ).json().get("workflow_runs", [])

    def poll_run(
        self,
        run_id: int,
        *,
        timeout_seconds: int = 1200,
        interval_seconds: int = 10,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            run = self.get_run(run_id)
            if run.get("status") == "completed":
                return run
            time.sleep(interval_seconds)
        raise TimeoutError(f"Workflow run {run_id} did not finish within the timeout.")

    def list_artifacts(self, run_id: int) -> list[dict[str, Any]]:
        return self.request(
            "GET",
            f"/repos/{self.repository}/actions/runs/{run_id}/artifacts",
            params={"per_page": 100},
        ).json().get("artifacts", [])

    def wait_for_artifact(
        self,
        run_id: int,
        *,
        timeout_seconds: int = 120,
        interval_seconds: int = 5,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        prefix = f"blender-render-{run_id}"
        while time.monotonic() < deadline:
            for artifact in self.list_artifacts(run_id):
                if (
                    not artifact.get("expired", False)
                    and artifact.get("name", "").startswith(prefix)
                ):
                    return artifact
            time.sleep(interval_seconds)
        raise TimeoutError(f"No render artifact appeared for run {run_id}.")

    def render(
        self,
        *,
        workflow: str = DEFAULT_WORKFLOW,
        ref: str = DEFAULT_REF,
        script_base64: str,
        output_name: str = "render.mp4",
        blender_version: str = DEFAULT_BLENDER_VERSION,
        timeout_seconds: int = 1200,
    ) -> RenderResult:
        run_id = self.dispatch(
            workflow=workflow,
            ref=ref,
            script_base64=script_base64,
            output_name=output_name,
            blender_version=blender_version,
        )
        run = self.poll_run(run_id, timeout_seconds=timeout_seconds)
        if run.get("conclusion") != "success":
            raise GitHubError(
                f"Blender workflow failed: status={run.get('status')} "
                f"conclusion={run.get('conclusion')} run_url={run.get('html_url')}"
            )
        artifact = self.wait_for_artifact(run_id)
        return RenderResult(
            run_id=run_id,
            status=run.get("status", "completed"),
            conclusion=run.get("conclusion"),
            run_url=run.get(
                "html_url",
                f"https://github.com/{self.repository}/actions/runs/{run_id}",
            ),
            artifact_id=artifact.get("id"),
            artifact_name=artifact.get("name"),
            artifact_download_url=artifact.get("archive_download_url"),
        )


def encode_script(path: str | Path) -> str:
    data = Path(path).read_bytes()
    if not data:
        raise ValueError("Blender script is empty.")
    return base64.b64encode(data).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dispatch and monitor a Blender GitHub Actions render."
    )
    parser.add_argument("--script-path")
    parser.add_argument("--script-base64")
    parser.add_argument("--output-name", default="render.mp4")
    parser.add_argument("--blender-version", default=DEFAULT_BLENDER_VERSION)
    parser.add_argument("--ref", default=DEFAULT_REF)
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW)
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY", DEFAULT_REPO))
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    if bool(args.script_path) == bool(args.script_base64):
        parser.error("Provide exactly one of --script-path or --script-base64.")
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        parser.error("Set GITHUB_TOKEN in the environment.")

    script_b64 = args.script_base64
    if args.script_path:
        script_b64 = encode_script(args.script_path)

    client = GitHubActionsClient(token=token, repository=args.repo)
    result = client.render(
        workflow=args.workflow,
        ref=args.ref,
        script_base64=script_b64,
        output_name=args.output_name,
        blender_version=args.blender_version,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
