"""Runner — executes the tiny-CNN train.py in a per-experiment workspace.

Creates runs/<mission>/<exp>/, runs `python examples/tiny_cnn/train.py --config
<config>` as a subprocess with the mission timeout, streams metric_logged events
as metrics.jsonl rows appear, then emits experiment_finished{status:success} or
experiment_failed{failure_type:nan_detected|timeout|error}.

All emission goes through the ``emit`` callback (which wraps kun_log).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

# Repo root = .../kun-w3 (this file is backend/app/loop/runner.py).
REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
TRAIN_SCRIPT = os.path.join(REPO_ROOT, "examples", "tiny_cnn", "train.py")


def _read_new_metric_rows(path: str, seen: int) -> Tuple[List[Dict[str, Any]], int]:
    if not os.path.exists(path):
        return [], seen
    rows: List[Dict[str, Any]] = []
    with open(path) as f:
        lines = f.read().splitlines()
    for line in lines[seen:]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows, len(lines)


def run_experiment(
    *,
    config_path: str,
    workspace_dir: str,
    timeout_sec: int,
    emit: Callable[..., Any],
    envelope: Dict[str, Any],
    train_script: str = TRAIN_SCRIPT,
) -> Dict[str, Any]:
    """Run one experiment. Emits experiment_started, metric_logged*, and
    experiment_finished | experiment_failed. Returns a result dict:

        {status, final_metrics, last_metrics, failure_type?, message?,
         stdout_path, stderr_path}

    ``train_script`` is the adapter's trainer entry point (default: the tiny-CNN
    script). Any trainer that honors the contract — accept ``--config``, write
    metric rows to <workspace>/metrics.jsonl, exit nonzero with a ``train_loss:"nan"``
    row on divergence — plugs in unchanged.
    """
    os.makedirs(workspace_dir, exist_ok=True)
    metrics_path = os.path.join(workspace_dir, "metrics.jsonl")
    stdout_path = os.path.join(workspace_dir, "stdout.log")
    stderr_path = os.path.join(workspace_dir, "stderr.log")
    # Clear any stale metrics from a previous attempt.
    open(metrics_path, "w").close()

    rel_config = os.path.relpath(config_path, REPO_ROOT)
    rel_script = os.path.relpath(train_script, REPO_ROOT)
    command = f"python {rel_script} --config {rel_config}"

    emit(
        "experiment_started",
        {
            "command": command,
            "workspace_path": os.path.relpath(workspace_dir, REPO_ROOT),
            "timeout_sec": timeout_sec,
        },
        **envelope,
    )

    proc = subprocess.Popen(
        [sys.executable, train_script, "--config", config_path],
        cwd=REPO_ROOT,
        stdout=open(stdout_path, "w"),
        stderr=open(stderr_path, "w"),
    )

    seen = 0
    last_metrics: Dict[str, Any] = {}
    final_metrics: Dict[str, Any] = {}
    nan_seen = False
    t0 = time.time()
    timed_out = False

    def drain_metrics():
        nonlocal seen, last_metrics, final_metrics, nan_seen
        rows, seen = _read_new_metric_rows(metrics_path, seen)
        for row in rows:
            name = row.get("name")
            value = row.get("value")
            if name == "train_loss" and (value == "nan" or value == "NaN"):
                nan_seen = True
                last_metrics["train_loss"] = "nan"
                continue
            if isinstance(value, (int, float)):
                last_metrics[name] = value
                if name in ("val_accuracy", "train_accuracy", "runtime_sec"):
                    final_metrics[name] = value
            # Stream live metric_logged for chartable rows.
            payload = {"name": name, "value": value, "step": row.get("step")}
            if "epoch" in row:
                payload["epoch"] = row["epoch"]
            if "phase" in row:
                payload["phase"] = row["phase"]
            emit("metric_logged", payload, **envelope)

    while proc.poll() is None:
        if time.time() - t0 > timeout_sec:
            proc.kill()
            timed_out = True
            break
        drain_metrics()
        time.sleep(0.3)
    # Final drain after process exit.
    drain_metrics()
    returncode = proc.returncode

    runtime = round(time.time() - t0, 1)
    final_metrics.setdefault("runtime_sec", runtime)

    if timed_out:
        emit(
            "experiment_failed",
            {
                "failure_type": "timeout",
                "message": f"Exceeded timeout of {timeout_sec}s.",
                "last_metrics": last_metrics,
                "stdout_path": os.path.relpath(stdout_path, REPO_ROOT),
                "stderr_path": os.path.relpath(stderr_path, REPO_ROOT),
            },
            **envelope,
        )
        return {
            "status": "failed",
            "failure_type": "timeout",
            "last_metrics": last_metrics,
            "final_metrics": final_metrics,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
        }

    if nan_seen or returncode == 3:
        emit(
            "experiment_failed",
            {
                "failure_type": "nan_detected",
                "message": "Training loss became NaN.",
                "last_metrics": last_metrics or {"train_loss": "nan"},
                "stdout_path": os.path.relpath(stdout_path, REPO_ROOT),
                "stderr_path": os.path.relpath(stderr_path, REPO_ROOT),
            },
            **envelope,
        )
        return {
            "status": "failed",
            "failure_type": "nan_detected",
            "last_metrics": last_metrics or {"train_loss": "nan"},
            "final_metrics": final_metrics,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
        }

    if returncode != 0:
        emit(
            "experiment_failed",
            {
                "failure_type": "error",
                "message": f"train.py exited with code {returncode}.",
                "last_metrics": last_metrics,
                "stdout_path": os.path.relpath(stdout_path, REPO_ROOT),
                "stderr_path": os.path.relpath(stderr_path, REPO_ROOT),
            },
            **envelope,
        )
        return {
            "status": "failed",
            "failure_type": "error",
            "last_metrics": last_metrics,
            "final_metrics": final_metrics,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
        }

    emit(
        "experiment_finished",
        {
            "status": "success",
            "final_metrics": final_metrics,
            "artifacts": [os.path.relpath(config_path, REPO_ROOT)],
        },
        **envelope,
    )
    return {
        "status": "success",
        "final_metrics": final_metrics,
        "last_metrics": last_metrics,
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
    }
