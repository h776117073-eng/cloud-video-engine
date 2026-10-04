#!/usr/bin/env python3
"""Natural-language Blender agent.

The agent:
1. Sends the user prompt to the OpenAI Responses API.
2. Extracts a complete Blender bpy script.
3. Runs static syntax/safety checks.
4. Base64-encodes the script.
5. Dispatches .github/workflows/blender_render.yml through GitHub REST API.
6. Polls until the render completes and prints the artifact URL.

Secrets are read only from environment variables.
"""

from __future__ import annotations

import argparse
import ast
import base64
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import requests

from render_dispatch import (
    DEFAULT_BLENDER_VERSION,
    DEFAULT_REPO,
    DEFAULT_REF,
    DEFAULT_WORKFLOW,
    GitHubActionsClient,
)

OPENAI_API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.6"

SYSTEM_PROMPT = Path(__file__).with_name("AGENT_SYSTEM_PROMPT.md").read_text(
    encoding="utf-8"
)

ALLOWED_IMPORTS = {
    "bpy",
    "math",
    "mathutils",
    "os",
    "random",
    "typing",
    "pathlib",
    "json",
}

BLOCKED_NAMES = {"eval", "exec", "compile", "__import__"}

BLOCKED_MODULES = {
    "subprocess",
    "socket",
    "requests",
    "urllib",
    "http",
    "ftplib",
    "paramiko",
}

BLOCKED_CALLS = {"system", "popen", "remove", "unlink", "rmtree"}


class AgentError(RuntimeError):
    pass


def extract_python(text: str) -> str:
    fenced = re.findall(
        r"\`\`\`(?:python|py)?\s*(.*?)\`\`\`",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fenced:
        code = max(fenced, key=len).strip()
    else:
        code = text.strip()
        if code.startswith("python\n"):
            code = code.split("\n", 1)[1]
    if not code:
        raise AgentError("The model returned an empty Blender script.")
    return code


def validate_script(code: str) -> None:
    if len(code.encode("utf-8")) > 120_000:
        raise AgentError("Generated Blender script is larger than 120 KB.")

    try:
        tree = ast.parse(code, filename="generated_blender.py")
    except SyntaxError as exc:
        raise AgentError(f"Generated Blender script has a syntax error: {exc}") from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in BLOCKED_MODULES or root not in ALLOWED_IMPORTS:
                    raise AgentError(
                        f"Import is not allowed in generated Blender code: {alias.name}"
                    )
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in BLOCKED_MODULES or root not in ALLOWED_IMPORTS:
                raise AgentError(
                    f"Import is not allowed in generated Blender code: {node.module}"
                )
        elif isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            raise AgentError(f"Dynamic execution is not allowed: {node.id}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr in BLOCKED_CALLS:
                raise AgentError(
                    f"Potentially destructive call is not allowed: {node.func.attr}"
                )
            if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_NAMES:
                raise AgentError(f"Dynamic execution is not allowed: {node.func.id}")

    required_tokens = ("BLENDER_OUTPUT", "FFMPEG", "H264")
    missing = [token for token in required_tokens if token not in code]
    if missing:
        raise AgentError(
            "Generated script is missing required render contract markers: "
            + ", ".join(missing)
        )


def call_openai(prompt: str, *, model: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise AgentError("Set OPENAI_API_KEY in the environment.")

    payload: dict[str, Any] = {
        "model": model,
        "instructions": SYSTEM_PROMPT,
        "input": prompt,
        "store": False,
        "max_output_tokens": 30000,
    }

    response = requests.post(
        OPENAI_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180,
    )
    if response.status_code >= 400:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text[:1000]
        raise AgentError(f"OpenAI API error {response.status_code}: {detail}")

    data = response.json()
    output_text = data.get("output_text")
    if not output_text:
        raise AgentError("OpenAI response did not contain output_text.")
    return str(output_text)


def build_script(prompt: str, *, model: str) -> str:
    raw = call_openai(prompt, model=model)
    code = extract_python(raw)
    validate_script(code)
    return code


def dispatch(
    code: str,
    *,
    repo: str,
    workflow: str,
    ref: str,
    output_name: str,
    blender_version: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise AgentError("Set GITHUB_TOKEN in the environment.")

    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    client = GitHubActionsClient(token=token, repository=repo)
    result = client.render(
        workflow=workflow,
        ref=ref,
        script_base64=encoded,
        output_name=output_name,
        blender_version=blender_version,
        timeout_seconds=timeout_seconds,
    )
    return result.as_dict()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a Blender bpy script from a prompt and dispatch it to GitHub Actions."
    )
    parser.add_argument("prompt", nargs="?", help="User natural-language video request.")
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", DEFAULT_MODEL))
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY", DEFAULT_REPO))
    parser.add_argument(
        "--workflow", default=os.getenv("BLENDER_WORKFLOW", DEFAULT_WORKFLOW)
    )
    parser.add_argument("--ref", default=os.getenv("GITHUB_REF_NAME", DEFAULT_REF))
    parser.add_argument("--output-name", default="render.mp4")
    parser.add_argument("--blender-version", default=DEFAULT_BLENDER_VERSION)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--save-script", help="Optional path to save the generated bpy script.")
    parser.add_argument(
        "--no-dispatch",
        action="store_true",
        help="Generate and validate code without starting Actions.",
    )
    args = parser.parse_args()

    prompt = args.prompt
    if not prompt:
        prompt = sys.stdin.read().strip()
    if not prompt:
        parser.error("Provide a prompt argument or pipe the prompt through stdin.")

    code = build_script(prompt, model=args.model)

    if args.save_script:
        path = Path(args.save_script)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code, encoding="utf-8")

    result: dict[str, Any] = {
        "model": args.model,
        "script_bytes": len(code.encode("utf-8")),
        "script": code,
    }

    if not args.no_dispatch:
        result["render"] = dispatch(
            code,
            repo=args.repo,
            workflow=args.workflow,
            ref=args.ref,
            output_name=args.output_name,
            blender_version=args.blender_version,
            timeout_seconds=args.timeout_seconds,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AgentError, TimeoutError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
