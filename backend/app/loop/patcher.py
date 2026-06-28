"""Patcher — applies the planner's proposed change to a per-experiment workspace.

One interface, two implementations (CONTRACT / spec §4):
  - ``config-patch`` (P0, here): write a new config.yaml with `changes` applied
    into runs/<mission>/<exp>/ and produce a UNIFIED DIFF vs the parent config
    (for the file_diff_created event).
  - ``agent-edit`` (P1): NOT built. The interface is left open below.
"""
from __future__ import annotations

import difflib
import os
from typing import Any, Dict, Optional, Tuple

import yaml


def _dump(cfg: Dict[str, Any]) -> str:
    # Stable key order so diffs are minimal and readable.
    return yaml.safe_dump(cfg, sort_keys=True, default_flow_style=False)


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


def apply_agent_edit(*args, **kwargs):  # pragma: no cover - P1, interface only
    """agent-edit patcher (P1). Hands the change to a coding-agent subprocess to
    edit real model code and returns the resulting diff. Intentionally not
    implemented for P0 — config-patch is the always-available path."""
    raise NotImplementedError("agent-edit is P1; use config-patch for P0.")
