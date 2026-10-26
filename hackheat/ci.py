"""Lint, secret scan, freshness, package, and deploy checks used by CI."""

from __future__ import annotations

import ast
import json
import re
import sys
import zipfile
from pathlib import Path

from hackheat import __version__
from hackheat.board import load_board
from hackheat.mcp_server import TOOLS
from hackheat.timeutil import now

ROOT = Path(__file__).resolve().parents[1]

SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"glpat-[A-Za-z0-9\-_]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"sk-(?:live|test|proj|ant)-[A-Za-z0-9]{10,}"),
)

SKIP_DIRS = {".git", ".venv", "venv", "dist", "__pycache__", ".pytest_cache"}

FLOW_SNIPPETS = (
    "version: v1",
    "environment: ambient",
    "type: HumanInputComponent",
    'interaction_type: "approval"',
    "on_user_input_prompt",
    "on_user_response",
    '"approve"',
    '"modify"',
    '"reject"',
    "default_route",
    "sends_response_to: curator_agent",
    "python3 -m hackheat.curator validate",
    "python3 -m hackheat.curator apply",
    "--approved-by",
)


def lint() -> None:
    _compile_python()
    board = load_board()
    if len(board.items) < 60:
        raise SystemExit(f"Expected the seeded board, found {len(board.items)} rows.")
    ids = [item.id for item in board.items]
    if len(ids) != len(set(ids)):
        raise SystemExit("Board ids are not unique.")
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    if not license_text.startswith("MIT License"):
        raise SystemExit("LICENSE must start with 'MIT License' so GitLab can show it in About.")
    flow = (ROOT / "flows" / "radar-curator.yml").read_text(encoding="utf-8")
    for snippet in FLOW_SNIPPETS:
        if snippet not in flow:
            raise SystemExit(f"flows/radar-curator.yml is missing {snippet!r}.")
    if re.search(r"(?m)^name:", flow) or re.search(r"(?m)^description:", flow):
        raise SystemExit("Custom flow definitions reject top-level name and description fields.")
    mcp = json.loads((ROOT / ".gitlab" / "duo" / "mcp.json").read_text(encoding="utf-8"))
    server = mcp["mcpServers"]["hack-heat-live"]
    if server.get("command") not in {"python3", "python"}:
        raise SystemExit("Duo MCP config must launch the Python stdio server.")
    approved = set(server.get("approvedTools") or [])
    names = {tool["name"] for tool in TOOLS}
    if approved != names:
        raise SystemExit(f"approvedTools {sorted(approved)} does not match server tools {sorted(names)}.")
    _check_agent_config()
    _check_pipeline()
    agent = (ROOT / "agents" / "radar-curator.yml").read_text(encoding="utf-8")
    if "system_prompt:" not in agent or "name:" not in agent:
        raise SystemExit("agents/radar-curator.yml is missing name or system_prompt.")
    print(f"lint ok — {len(board.items)} rows, flow gate present, {len(names)} MCP tools")


AGENT_CONFIG_KEYS = {"image", "setup_script", "network_policy", "cache"}

PIPELINE_SNIPPETS = (
    "template: Jobs/SAST.gitlab-ci.yml",
    "template: Jobs/Secret-Detection.gitlab-ci.yml",
    "  - release\n",
    "  - secure\n",
    "when: manual",
    "tag_name: $CI_COMMIT_TAG",
)


def _check_agent_config() -> None:
    """Duo flow execution config: only keys GitLab documents, and python3 must resolve."""
    path = ROOT / ".gitlab" / "duo" / "agent-config.yml"
    if not path.exists():
        raise SystemExit(".gitlab/duo/agent-config.yml is missing.")
    text = path.read_text(encoding="utf-8")
    keys = set(re.findall(r"(?m)^([A-Za-z_]+):", text))
    unknown = keys - AGENT_CONFIG_KEYS
    if unknown:
        raise SystemExit(f"agent-config.yml has unsupported keys: {sorted(unknown)}")
    if "python3" not in text:
        raise SystemExit("agent-config.yml must make python3 available to the curator flow.")


def _check_pipeline() -> None:
    text = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    for snippet in PIPELINE_SNIPPETS:
        if snippet not in text:
            raise SystemExit(f".gitlab-ci.yml is missing {snippet.strip()!r}.")
    declared = set(re.findall(r"(?m)^  - ([a-z_-]+)$", text.split("include:")[0]))
    used = set(re.findall(r"(?m)^  stage: ([a-z_-]+)$", text))
    missing = used - declared
    if missing:
        raise SystemExit(f".gitlab-ci.yml uses undeclared stages: {sorted(missing)}")


def secrets() -> None:
    findings: list[str] = []
    for path in _files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"{path.relative_to(ROOT)} matches {pattern.pattern}")
    if findings:
        raise SystemExit("Secret scan failed:\n" + "\n".join(findings))
    print(f"secret scan ok — {sum(1 for _ in _files())} files")


def freshness() -> None:
    board = load_board()
    moment = now()
    open_count = sum(1 for item in board.items if item.is_open(moment))
    unparsed = [
        item.id
        for item in board.items
        if (item.raw.get("deadline") or item.raw.get("registrationCloses")) and not item.gates
    ]
    if unparsed:
        raise SystemExit("Unparseable deadlines: " + ", ".join(unparsed))
    if not board.items:
        raise SystemExit("Board is empty.")
    print(
        f"freshness ok — updated {board.updated_at}, {open_count} open of {len(board.items)} "
        f"as of {moment.isoformat()}"
    )


def package() -> Path:
    destination = ROOT / "dist" / f"hack-heat-live-{__version__}.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    include_roots = [
        "hackheat",
        "data",
        "flows",
        "agents",
        "docs",
        "deploy",
        "candidates",
        "tests",
    ]
    include_files = [
        "LICENSE",
        "README.md",
        "Dockerfile",
        ".gitlab-ci.yml",
        ".env.example",
        "Makefile",
    ]
    if destination.exists():
        destination.unlink()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in include_files:
            path = ROOT / name
            if path.exists():
                archive.write(path, name)
        for folder in include_roots:
            base = ROOT / folder
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
                    continue
                archive.write(path, path.relative_to(ROOT).as_posix())
        notes = (
            f"Hack Heat Live {__version__}\n"
            "Path A, Supervised autonomy.\n"
            "Production deploy stays manual. See deploy/cloudrun/README.md.\n"
        )
        archive.writestr("dist-note.txt", notes)
    print(f"packaged {destination.relative_to(ROOT)} ({destination.stat().st_size} bytes)")
    return destination


def deploy_check() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    service = (ROOT / "deploy" / "cloudrun" / "service.yaml").read_text(encoding="utf-8")
    if "hackheat.http_api" not in dockerfile:
        raise SystemExit("Dockerfile does not start the HTTP API.")
    if "minScale: \"0\"" not in service and 'minScale: "0"' not in service:
        raise SystemExit("Cloud Run service must scale to zero.")
    if "containerPort: 8080" not in service:
        raise SystemExit("Cloud Run service must listen on 8080.")
    print("deploy check ok — image and Cloud Run service are present.")
    print("Supervised gate: run the production deploy only after the outcome is approved.")
    print(
        "gcloud run deploy hack-heat-live --source . --region asia-southeast1 "
        "--allow-unauthenticated --port 8080"
    )


def _compile_python() -> None:
    for path in _files():
        if path.suffix != ".py":
            continue
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))


def _files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix in {".png", ".webp", ".jpg", ".gif", ".zip"}:
            continue
        yield path


def main(argv: list[str] | None = None) -> None:
    command = (argv or sys.argv[1:])[0] if (argv or sys.argv[1:]) else ""
    commands = {
        "lint": lint,
        "secrets": secrets,
        "freshness": freshness,
        "package": package,
        "deploy-check": deploy_check,
    }
    if command not in commands:
        raise SystemExit("usage: python -m hackheat.ci lint|secrets|freshness|package|deploy-check")
    commands[command]()


if __name__ == "__main__":
    main()
