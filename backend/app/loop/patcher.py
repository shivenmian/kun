"""Patcher — applies the planner's proposed change to a per-experiment workspace.

One interface, two implementations (CONTRACT / spec §4; design: docs/08-agent-edit-design.md):

  - ``config-patch`` (P0): write a new config.yaml with `changes` applied into
    runs/<mission>/<exp>/ and produce a UNIFIED DIFF vs the parent config (for
    the file_diff_created event). Reliable, seconds/cycle. The always-available
    fallback. ``apply_config_patch`` is unchanged from P0.

  - ``agent-edit`` (P1, here): hand the planner's proposed change to a coding
    agent (Claude Code CLI) run as a subprocess to edit *real model code* inside
    an isolated, git-tracked per-experiment SANDBOX, then return the resulting
    git diff. Validated, recorded-only; any flake falls back to config-patch.

The agent-edit patcher NEVER touches the real source tree: it copies the
mission's ``editable_files`` out of ``examples/<adapter>/`` into the experiment
workspace, ``git init``s that copy, and the coding agent edits the SANDBOX only.
"""
from __future__ import annotations

import difflib
import json
import os
import shutil
import signal
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple

import yaml

# --- defaults / env knobs -----------------------------------------------------
# Editor model: the Claude Code CLI subprocess (separate from the planner LLM).
# Default to a cheap/fast alias for cost+speed (doc 08 §4/§5).
DEFAULT_EDITOR_MODEL = os.environ.get("KUN_EDITOR_MODEL", "sonnet")
# Wall-clock cap for ONE edit (Python subprocess timeout; macOS has no `timeout`).
DEFAULT_EDITOR_TIMEOUT_SEC = float(os.environ.get("KUN_EDITOR_TIMEOUT_SEC", "180"))
# Turn cap for the agentic edit loop.
DEFAULT_EDITOR_MAX_TURNS = int(os.environ.get("KUN_EDITOR_MAX_TURNS", "12"))
# commit-per-node (doc 08 §6): commit the validated edit so the trajectory is a
# real git DAG and we can record a commit_sha. Cheap; on by default but optional.
COMMIT_PER_NODE = os.environ.get("KUN_COMMIT_PER_NODE", "1") not in ("0", "false", "")

# Git identity for the sandbox repo (avoid depending on the user's global config).
_GIT_ID = [
    "-c", "user.email=kun@localhost",
    "-c", "user.name=kun-agent-edit",
    "-c", "commit.gpgsign=false",
    "-c", "init.defaultBranch=main",
]


def _dump(cfg: Dict[str, Any]) -> str:
    # Stable key order so diffs are minimal and readable.
    return yaml.safe_dump(cfg, sort_keys=True, default_flow_style=False)


# =============================================================================
# config-patch (P0) — UNCHANGED
# =============================================================================

def apply_config_patch(
    *,
    base_config: Dict[str, Any],
    changes: Dict[str, Any],
    workspace_dir: str,
    base_file_path: str,
    new_file_path: Optional[str] = None,
) -> Tuple[str, str, str]:
    """Write the patched config and return (config_path, diff, base_file_path).

    - ``base_config``: parent node's config dict (the baseline for exp_000).
    - ``changes``: keys to overwrite (the LLM/heuristic proposal).
    - ``workspace_dir``: runs/<mission>/<exp>/ (created if missing).
    - ``base_file_path`` / ``new_file_path``: labels used in the unified diff.
    """
    os.makedirs(workspace_dir, exist_ok=True)
    new_config = dict(base_config)
    new_config.update(changes)

    config_path = os.path.join(workspace_dir, "config.yaml")
    new_text = _dump(new_config)
    with open(config_path, "w") as f:
        f.write(new_text)

    base_text = _dump(base_config)
    if new_file_path is None:
        new_file_path = config_path
    diff = "".join(
        difflib.unified_diff(
            base_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=base_file_path,
            tofile=new_file_path,
        )
    )
    return config_path, diff, base_file_path


# =============================================================================
# Patcher interface (doc 08 §2)
# =============================================================================

@dataclass
class PatchResult:
    """Result of applying a proposed change to a workspace (doc 08 §2)."""

    ok: bool                                   # valid, applied edit?
    diff: str = ""                             # unified diff (git diff vs base)
    files_changed: List[str] = field(default_factory=list)
    commit_sha: Optional[str] = None           # if commit-per-node is on
    error: Optional[str] = None                # populated when ok is False (-> buggy)
    # Telemetry from the editor JSON (logged onto the node when available).
    cost_usd: Optional[float] = None
    session_id: Optional[str] = None


class Patcher(Protocol):
    def apply(
        self,
        workspace: str,
        proposal: Any,
        constraints: List[Any],
        editable_files: List[str],
        model: str,
    ) -> PatchResult: ...


# =============================================================================
# helpers shared by agent-edit
# =============================================================================

def _ensure_api_key() -> bool:
    """Ensure ANTHROPIC_API_KEY is in the environment, loading backend/.env if
    needed. Returns True if a key is present afterwards."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    here = os.path.dirname(__file__)
    candidates = [
        os.path.abspath(os.path.join(here, "..", "..", ".env")),       # backend/.env
        os.path.abspath(os.path.join(here, "..", "..", "..", ".env")),  # repo/.env
        # The worktree may have no backend/.env of its own — fall back to the
        # primary checkout's backend/.env (where the key actually lives).
        "/Users/shivenmian/kun/backend/.env",
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    os.environ.setdefault(k, v)
        except OSError:
            pass
        if os.environ.get("ANTHROPIC_API_KEY"):
            return True
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _git(workspace: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", workspace, *args],
        capture_output=True, text=True, check=check,
    )


def _proposal_field(proposal: Any, name: str, default: Any = None) -> Any:
    """Read a field from a Proposal (pydantic model) or a plain dict."""
    if proposal is None:
        return default
    if isinstance(proposal, dict):
        return proposal.get(name, default)
    return getattr(proposal, name, default)


def _constraints_lines(constraints: List[Any]) -> List[str]:
    """Belt-and-suspenders ban lines for the editor (doc 08 §3)."""
    lines: List[str] = []
    for c in constraints or []:
        bound = getattr(c, "bound", None) if not isinstance(c, dict) else c.get("bound")
        text = getattr(c, "text", None) if not isinstance(c, dict) else c.get("text")
        if bound is not None:
            param = getattr(bound, "param", None) if not isinstance(bound, dict) else bound.get("param")
            op = getattr(bound, "op", None) if not isinstance(bound, dict) else bound.get("op")
            value = getattr(bound, "value", None) if not isinstance(bound, dict) else bound.get("value")
            lines.append(f"- Do NOT set {param} {op} {value}." + (f" ({text})" if text else ""))
        elif text:
            lines.append(f"- {text}")
    return lines


def build_edit_prompt(
    proposal: Any,
    constraints: List[Any],
    editable_files: List[str],
) -> str:
    """Bounded editing prompt for the coding agent (doc 08 §3)."""
    operator = _proposal_field(proposal, "operator", "improve")
    hypothesis = _proposal_field(proposal, "hypothesis", "")
    changes = _proposal_field(proposal, "changes", {}) or {}
    rationale = _proposal_field(proposal, "rationale", "")

    # Operator discipline.
    if operator == "improve":
        discipline = (
            "Make exactly ONE atomic change so its effect is measurable. "
            "Do not refactor or change anything else."
        )
    elif operator == "debug":
        discipline = (
            "The previous run failed. Fix the bug while PRESERVING the existing "
            "approach. Make the smallest change that resolves the failure."
        )
    else:  # draft
        discipline = "Scaffold the new approach described below. Keep it minimal and runnable."

    parts: List[str] = [
        "You are a mechanical code editor inside an autonomous ML research loop.",
        "Implement the SPECIFIC change below. Do not invent a different direction.",
        "",
        f"CHANGE TO IMPLEMENT (operator={operator}):",
        f"  Hypothesis: {hypothesis}",
    ]
    if changes:
        parts.append(f"  Concrete change(s): {json.dumps(changes)}")
    if rationale:
        parts.append(f"  Rationale: {rationale}")
    parts += [
        "",
        f"OPERATOR DISCIPLINE: {discipline}",
        "",
        "EDITABLE SURFACE — edit ONLY these files (relative to this directory):",
    ]
    parts += [f"  - {f}" for f in editable_files]

    bans = _constraints_lines(constraints)
    if bans:
        parts += ["", "ACTIVE CONSTRAINTS (respect these bounds):"]
        parts += [f"  {b}" for b in bans]

    parts += [
        "",
        "DO NOT:",
        "  - Do NOT run training or any commands.",
        "  - Do NOT commit.",
        "  - Do NOT touch files outside the editable set above.",
        "  - Make the change and stop.",
    ]
    return "\n".join(parts)


def _run_editor(
    prompt: str, workspace: str, model: str, timeout_sec: float, max_turns: int,
) -> Tuple[int, str, str, bool]:
    """Run the Claude Code CLI as a subprocess in ``workspace``.

    Returns (returncode, stdout, stderr, timed_out). On timeout the whole
    process group is killed (doc 08 §5)."""
    cmd = [
        "claude", "-p", prompt,
        "--bare",
        "--permission-mode", "acceptEdits",
        "--allowedTools", "Read,Edit,Write",   # NO Bash -> editor can't run/commit
        "--max-turns", str(max_turns),
        "--output-format", "json",
        "--model", model,
    ]
    env = os.environ.copy()  # MUST inherit ANTHROPIC_API_KEY + PATH
    proc = subprocess.Popen(
        cmd, cwd=workspace, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True,  # own process group for clean group-kill
    )
    try:
        out, err = proc.communicate(timeout=timeout_sec)
        return proc.returncode, out, err, False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        try:
            out, err = proc.communicate(timeout=10)
        except Exception:
            out, err = "", ""
        return -1, out, err, True


# =============================================================================
# agent-edit (P1)
# =============================================================================

class AgentEdit:
    """The agent-edit patcher: sandbox -> coding-agent subprocess -> validated diff."""

    def apply(
        self,
        workspace: str,
        proposal: Any,
        constraints: List[Any],
        editable_files: List[str],
        model: str = DEFAULT_EDITOR_MODEL,
        *,
        source_dir: str,
        timeout_sec: float = DEFAULT_EDITOR_TIMEOUT_SEC,
        max_turns: int = DEFAULT_EDITOR_MAX_TURNS,
        commit_per_node: Optional[bool] = None,
    ) -> PatchResult:
        """Edit ``editable_files`` (copied from ``source_dir``) inside an isolated
        git-tracked ``workspace`` and return the captured diff as a PatchResult.

        Any flake -> ``ok=False`` with an ``error`` (the loop falls back to
        config-patch for this experiment; doc 08 §7). Never raises for expected
        failure modes."""
        if commit_per_node is None:
            commit_per_node = COMMIT_PER_NODE
        editable_files = list(editable_files or [])
        if not editable_files:
            return PatchResult(ok=False, error="no editable_files configured")

        # 1) Seed the SANDBOX: copy editable source files in, git init + base commit.
        try:
            os.makedirs(workspace, exist_ok=True)
            for rel in editable_files:
                src = os.path.join(source_dir, rel)
                if not os.path.exists(src):
                    return PatchResult(
                        ok=False, error=f"editable source missing: {rel} (looked in {source_dir})"
                    )
                dst = os.path.join(workspace, rel)
                os.makedirs(os.path.dirname(dst) or workspace, exist_ok=True)
                shutil.copy2(src, dst)
            if not os.path.isdir(os.path.join(workspace, ".git")):
                _git(workspace, *_GIT_ID, "init", "-q")
            _git(workspace, *_GIT_ID, "add", "-A")
            _git(workspace, *_GIT_ID, "commit", "-q", "-m", "base", "--allow-empty")
        except (OSError, subprocess.CalledProcessError) as e:
            return PatchResult(ok=False, error=f"sandbox setup failed: {e}")

        # 2) Require an API key for the editor subprocess (else fall back).
        if not _ensure_api_key():
            return PatchResult(ok=False, error="no ANTHROPIC_API_KEY for editor")

        # 3) Build the bounded prompt + invoke the coding agent.
        prompt = build_edit_prompt(proposal, constraints, editable_files)
        try:
            rc, out, err, timed_out = _run_editor(
                prompt, workspace, model, timeout_sec, max_turns
            )
        except FileNotFoundError:
            return PatchResult(ok=False, error="claude CLI not found on PATH")
        except Exception as e:  # subprocess machinery failure
            return PatchResult(ok=False, error=f"editor subprocess error: {e}")

        if timed_out:
            return PatchResult(ok=False, error="editor timed out")

        # Telemetry from --output-format json (best-effort).
        cost_usd: Optional[float] = None
        session_id: Optional[str] = None
        parsed: Optional[Dict[str, Any]] = None
        try:
            parsed = json.loads(out)
            if isinstance(parsed, dict):
                cost_usd = parsed.get("total_cost_usd")
                session_id = parsed.get("session_id")
        except (json.JSONDecodeError, TypeError):
            pass

        if rc != 0:
            msg = (parsed or {}).get("result") if isinstance(parsed, dict) else None
            return PatchResult(
                ok=False,
                error=f"editor exited rc={rc}: {msg or (err or out)[:200]}",
                cost_usd=cost_usd, session_id=session_id,
            )

        # 4) Capture the diff vs the base commit.
        try:
            _git(workspace, *_GIT_ID, "add", "-A")
            diff = _git(workspace, *_GIT_ID, "diff", "--cached").stdout
            names = _git(workspace, *_GIT_ID, "diff", "--cached", "--name-only").stdout
        except subprocess.CalledProcessError as e:
            return PatchResult(ok=False, error=f"diff capture failed: {e}",
                               cost_usd=cost_usd, session_id=session_id)
        files_changed = [n for n in names.splitlines() if n.strip()]

        # 5) Validate (doc 08 §5).
        if not diff.strip():
            return PatchResult(ok=False, error="agent made no change",
                               cost_usd=cost_usd, session_id=session_id)

        out_of_scope = [f for f in files_changed if f not in editable_files]
        if out_of_scope:
            # Enforce the editable surface: revert everything -> buggy.
            try:
                _git(workspace, *_GIT_ID, "reset", "-q", "--hard", "HEAD")
                _git(workspace, *_GIT_ID, "clean", "-qfd")
            except subprocess.CalledProcessError:
                pass
            return PatchResult(
                ok=False,
                error=f"edited files outside editable set: {out_of_scope}",
                files_changed=files_changed, cost_usd=cost_usd, session_id=session_id,
            )

        # Optional cheap syntax check on changed .py files -> mark buggy early.
        for f in files_changed:
            if f.endswith(".py"):
                chk = subprocess.run(
                    ["python", "-m", "py_compile", os.path.join(workspace, f)],
                    capture_output=True, text=True,
                )
                if chk.returncode != 0:
                    return PatchResult(
                        ok=False, diff=diff, files_changed=files_changed,
                        error=f"py_compile failed for {f}: {chk.stderr.strip()[:200]}",
                        cost_usd=cost_usd, session_id=session_id,
                    )

        # 6) commit-per-node (optional/stretch, doc 08 §6).
        commit_sha: Optional[str] = None
        if commit_per_node:
            try:
                _git(workspace, *_GIT_ID, "commit", "-q", "-m", "agent-edit")
                commit_sha = _git(workspace, *_GIT_ID, "rev-parse", "HEAD").stdout.strip()
            except subprocess.CalledProcessError:
                commit_sha = None

        return PatchResult(
            ok=True, diff=diff, files_changed=files_changed, commit_sha=commit_sha,
            cost_usd=cost_usd, session_id=session_id,
        )


# Module singleton (used as ``from app.loop.patcher import agent_edit``).
agent_edit = AgentEdit()


# =============================================================================
# patcher selection (pluggable; doc 08 §1, §7)
# =============================================================================

VALID_PATCHERS = ("config-patch", "agent-edit")


def select_patcher(mission: Optional[Dict[str, Any]] = None) -> str:
    """Choose which patcher the loop uses. Env override ``KUN_PATCHER`` wins,
    else ``mission["patcher"]``, else the always-safe default ``config-patch``
    (so every P0 mission is unchanged). Unknown values fall back to config-patch."""
    name = os.environ.get("KUN_PATCHER") or (mission or {}).get("patcher") or "config-patch"
    name = str(name).strip().lower()
    if name not in VALID_PATCHERS:
        return "config-patch"
    return name


# Back-compat shim: the old P0 stub raised NotImplementedError. Now functional.
def apply_agent_edit(*args, **kwargs) -> PatchResult:  # pragma: no cover - thin shim
    return agent_edit.apply(*args, **kwargs)
