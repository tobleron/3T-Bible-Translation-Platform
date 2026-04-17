#!/usr/bin/env python3
"""Repository analyzer for 3T Bible Translation Platform.

This is intentionally stdlib-only so it can run immediately after clone.
"""

from __future__ import annotations

import ast
import fnmatch
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "_dev-system" / "config" / "efficiency.json"
REPORT_PATH = ROOT / "_dev-system" / "reports" / "latest.json"
TASK_DIR = ROOT / "_dev-tasks"
GENERATED_RE = re.compile(r"^D\d{3}_.*\.md$")


@dataclass
class Finding:
    severity: str
    kind: str
    message: str
    line: int | None = None


@dataclass
class FileReport:
    path: str
    role: str
    language: str
    loc: int
    risk: float
    preferred_loc: int
    hard_loc: int
    branches: int = 0
    max_nesting: int = 0
    mutable_state: int = 0
    imports: int = 0
    callables: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def severity_score(self) -> float:
        finding_weight = sum({"high": 5, "medium": 3, "low": 1}.get(f.severity, 1) for f in self.findings)
        over_preferred = max(0, self.loc - self.preferred_loc) / max(self.preferred_loc, 1)
        over_hard = max(0, self.loc - self.hard_loc) / max(self.hard_loc, 1)
        return self.risk + finding_weight + over_preferred * 4 + over_hard * 8


class PythonMetrics(ast.NodeVisitor):
    branch_nodes = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.ExceptHandler,
        ast.With,
        ast.AsyncWith,
        ast.Match,
        ast.BoolOp,
        ast.IfExp,
    )

    def __init__(self) -> None:
        self.branches = 0
        self.max_nesting = 0
        self._nesting = 0
        self.mutable_state = 0
        self.imports = 0
        self.callables = 0

    def generic_visit(self, node: ast.AST) -> None:
        enters_branch = isinstance(node, self.branch_nodes)
        if enters_branch:
            self.branches += 1
            self._nesting += 1
            self.max_nesting = max(self.max_nesting, self._nesting)
        super().generic_visit(node)
        if enters_branch:
            self._nesting -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.callables += 1
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.callables += 1
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.callables += 1
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.mutable_state += 1
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.mutable_state += 1
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.mutable_state += 1
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        self.imports += len(node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.imports += len(node.names)


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def is_excluded(path: Path, config: dict[str, Any]) -> bool:
    rel_path = rel(path)
    parts = set(path.relative_to(ROOT).parts)
    for folder in config["exclusions"]["folders"]:
        if folder in parts or rel_path == folder or rel_path.startswith(f"{folder}/"):
            return True
    for pattern in config["exclusions"]["file_globs"]:
        if fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(rel_path, pattern):
            return True
    return False


def discover_files(config: dict[str, Any]) -> list[Path]:
    files: set[Path] = set()
    for root_name in config["scanned_roots"]:
        root = ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and not is_excluded(path, config):
                files.add(path)
    for file_name in config["extra_files"]:
        path = ROOT / file_name
        if path.exists() and path.is_file() and not is_excluded(path, config):
            files.add(path)
    return sorted(files)


def count_loc(text: str) -> int:
    count = 0
    in_block = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith('"""') or line.startswith("'''"):
            in_block = not (line.count('"""') == 2 or line.count("'''") == 2)
            continue
        if in_block:
            if line.endswith('"""') or line.endswith("'''"):
                in_block = False
            continue
        if line.startswith("#"):
            continue
        count += 1
    return count


def language_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix in {".html", ".jinja", ".j2"}:
        return "template"
    if suffix == ".css":
        return "css"
    if suffix in {".yaml", ".yml", ".toml", ".json"}:
        return "config"
    if suffix in {".sh"} or path.name == "ttt.sh":
        return "shell"
    if suffix in {".md"}:
        return "markdown"
    return "text"


def infer_role(path: Path, language: str, config: dict[str, Any]) -> str:
    rel_path = rel(path)
    if rel_path.startswith("tests/"):
        return "test"
    if rel_path.startswith("src/ttt_webapp/"):
        return "compat-shim"
    if rel_path.endswith("controller.py"):
        return "browser-controller"
    if rel_path.endswith("webapp.py") or rel_path.endswith("chainlit_app.py"):
        return "browser-route"
    if "llm" in rel_path or "llama_cpp" in rel_path:
        return "llm-client"
    if "repositories" in rel_path or "chunk_catalog" in rel_path or "session_manager" in rel_path:
        return "data-repository"
    if rel_path.startswith("src/ttt_epub/"):
        return "epub-builder"
    if "/scripts/" in rel_path or rel_path.startswith("src/ttt_converters/") or path.name == "ttt.sh":
        return "tool-script"
    if language == "template":
        return "template"
    if language == "css":
        return "style"
    if language in {"config", "shell", "markdown"}:
        return "config"
    return "general-python"


def role_limits(role: str, config: dict[str, Any]) -> tuple[int, int]:
    role_config = config["roles"].get(role, config["roles"]["general-python"])
    return int(role_config["preferred_loc"]), int(role_config["hard_loc"])


def pattern_findings(text: str, config: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    lower_text = text.lower()
    for rule in config["forbidden_patterns"]:
        pattern = rule["pattern"]
        haystack = lower_text if pattern.lower() == pattern else text
        needle = pattern if haystack is text else pattern.lower()
        index = haystack.find(needle)
        if index == -1:
            continue
        line = text[:index].count("\n") + 1
        findings.append(Finding(rule["severity"], "forbidden-pattern", rule["message"], line))
    return findings


def analyze_python(path: Path, text: str, role: str, config: dict[str, Any]) -> FileReport:
    loc = count_loc(text)
    preferred, hard = role_limits(role, config)
    metrics = PythonMetrics()
    findings = pattern_findings(text, config)
    try:
        tree = ast.parse(text, filename=rel(path))
        metrics.visit(tree)
    except SyntaxError as exc:
        findings.append(Finding("high", "syntax", f"Python syntax error: {exc.msg}", exc.lineno))

    settings = config["settings"]
    depth = max(0, len(path.relative_to(ROOT).parts) - settings["max_path_depth"])
    risk = (
        1.0
        + metrics.branches * settings["branch_weight"]
        + metrics.max_nesting * settings["nesting_weight"]
        + metrics.mutable_state * settings["state_weight"]
        + metrics.imports * settings["import_weight"]
        + metrics.callables * settings["callable_weight"]
        + depth * settings["path_depth_weight"]
    )
    if loc > preferred:
        findings.append(Finding("medium", "size", f"{loc} LOC exceeds preferred {preferred} LOC for role `{role}`."))
    if loc > hard:
        findings.append(Finding("high", "size", f"{loc} LOC exceeds hard ceiling {hard} LOC for role `{role}`."))
    return FileReport(
        path=rel(path),
        role=role,
        language="python",
        loc=loc,
        risk=round(risk, 2),
        preferred_loc=preferred,
        hard_loc=hard,
        branches=metrics.branches,
        max_nesting=metrics.max_nesting,
        mutable_state=metrics.mutable_state,
        imports=metrics.imports,
        callables=metrics.callables,
        findings=findings,
    )


def analyze_text(path: Path, text: str, role: str, language: str, config: dict[str, Any]) -> FileReport:
    loc = count_loc(text)
    preferred, hard = role_limits(role, config)
    findings = pattern_findings(text, config)
    if loc > preferred:
        findings.append(Finding("medium", "size", f"{loc} LOC exceeds preferred {preferred} LOC for role `{role}`."))
    if loc > hard:
        findings.append(Finding("high", "size", f"{loc} LOC exceeds hard ceiling {hard} LOC for role `{role}`."))
    risk = 1.0 + max(0, loc - preferred) / max(preferred, 1)
    return FileReport(
        path=rel(path),
        role=role,
        language=language,
        loc=loc,
        risk=round(risk, 2),
        preferred_loc=preferred,
        hard_loc=hard,
        findings=findings,
    )


def analyze_file(path: Path, config: dict[str, Any]) -> FileReport:
    text = path.read_text(encoding="utf-8", errors="replace")
    language = language_for(path)
    role = infer_role(path, language, config)
    if language == "python":
        return analyze_python(path, text, role, config)
    return analyze_text(path, text, role, language, config)


def finding_dict(finding: Finding) -> dict[str, Any]:
    return {
        "severity": finding.severity,
        "kind": finding.kind,
        "message": finding.message,
        "line": finding.line,
    }


def report_dict(report: FileReport) -> dict[str, Any]:
    return {
        "path": report.path,
        "role": report.role,
        "language": report.language,
        "loc": report.loc,
        "risk": report.risk,
        "preferred_loc": report.preferred_loc,
        "hard_loc": report.hard_loc,
        "branches": report.branches,
        "max_nesting": report.max_nesting,
        "mutable_state": report.mutable_state,
        "imports": report.imports,
        "callables": report.callables,
        "findings": [finding_dict(f) for f in report.findings],
    }


def reset_generated_tasks() -> None:
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    for path in TASK_DIR.iterdir():
        if path.is_file() and GENERATED_RE.match(path.name):
            path.unlink()


def task_slug(path: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", path).strip("_")
    return slug[:70] or "task"


def write_tasks(reports: list[FileReport], config: dict[str, Any]) -> list[str]:
    reset_generated_tasks()
    actionable = [
        report
        for report in reports
        if report.findings or report.loc > report.preferred_loc or report.risk >= 6.0
    ]
    actionable.sort(key=lambda item: item.severity_score, reverse=True)
    created: list[str] = []
    for index, report in enumerate(actionable[: config["settings"]["max_tasks"]], start=1):
        path = TASK_DIR / f"D{index:03d}_{task_slug(report.path)}.md"
        findings = "\n".join(
            f"- `{finding.severity}` `{finding.kind}`"
            f"{f' line {finding.line}' if finding.line else ''}: {finding.message}"
            for finding in report.findings
        )
        if not findings:
            findings = "- No hard finding; this file is listed because its risk/size score is high."
        body = f"""# Task D{index:03d}: Review {report.path}

## Why This Exists

`{report.path}` is a `{report.role}` file with an estimated risk score of `{report.risk}`.

## Metrics

- LOC: `{report.loc}` (preferred `{report.preferred_loc}`, hard ceiling `{report.hard_loc}`)
- Language: `{report.language}`
- Branches: `{report.branches}`
- Max nesting: `{report.max_nesting}`
- Mutable assignments: `{report.mutable_state}`
- Imports: `{report.imports}`
- Callables/classes: `{report.callables}`

## Findings

{findings}

## Suggested Handling

Keep the next change focused. If refactoring is warranted, split only cohesive behavior into named helper modules and preserve existing route/import compatibility. For browser workbench changes, rerun:

```bash
./ttt.sh test
```
"""
        path.write_text(body, encoding="utf-8")
        created.append(rel(path))
    return created


def write_report(reports: list[FileReport], tasks: list[str]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": "3T-Bible-Translation-Platform",
        "summary": {
            "files_scanned": len(reports),
            "tasks_generated": len(tasks),
            "highest_risk": max((report.risk for report in reports), default=0),
        },
        "tasks": tasks,
        "files": [report_dict(report) for report in sorted(reports, key=lambda item: item.severity_score, reverse=True)],
    }
    REPORT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    config = load_config()
    files = discover_files(config)
    reports = [analyze_file(path, config) for path in files]
    tasks = write_tasks(reports, config)
    write_report(reports, tasks)

    print(f"Scanned {len(reports)} files")
    print(f"Wrote {rel(REPORT_PATH)}")
    print(f"Generated {len(tasks)} advisory task(s)")
    for task in tasks:
        print(f"- {task}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
