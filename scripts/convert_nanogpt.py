"""Asset B converter (recorded, timing-flexible) — nanogpt run artifacts -> Kun events.jsonl.

Kun's serious demo (Beat 1) wants a RICH real-code modded-nanogpt trajectory: new
optimizers / attention tweaks, real diffs, real metrics. A live overnight GPU run is an
external ops dependency, so this converter exists so we are never blocked: it maps a
nanogpt training run's artifacts into a schema-valid Kun trajectory, and ships with a
hand-authored (SYNTHESIZED) trajectory that is a drop-in stand-in until the real run is
captured.

Two ways to use it:

  1. SYNTHESIZED stand-in (default — what ships today): the ATTEMPTS / FORKS lists below
     hold a realistic, internally-consistent modded-nanogpt arc. Run:
         python scripts/convert_nanogpt.py -o examples/replays/nanogpt.events.jsonl
     The script prints a LOUD notice that this is synthesized, not a captured run.
  2. Auto-parse a real run dir: wire parse_run_dir() to your real artifact format, then:
         python scripts/convert_nanogpt.py --run-dir runs/nanogpt_overnight -o <out>
     This is the path that the REAL overnight run uses to DROP IN and replace the
     synthesized file (same converter, same schema, real numbers).

HONESTY GUARD (critical): output must reflect what actually happened. The shipped ATTEMPTS
are a SYNTHESIZED stand-in for the overnight Mode-A + agent-edit run, not a live execution.
Never present these numbers as a captured run. See examples/replays/nanogpt.README.md.

Schema: docs/03-event-schema.md. No new event types are introduced.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
from dataclasses import dataclass, field

PLANNER = {"type": "agent", "name": "planner", "model": "claude-opus-4-8"}
EVALUATOR = {"type": "agent", "name": "evaluator", "model": "claude-opus-4-8"}
HUMAN = {"type": "human", "name": "user"}

MISSION_META = {
    "mission_id": "modded_nanogpt_run",
    "name": "modded-nanogpt speedrun (recorded)",
    "goal": "Reach the GPT-2 (124M) FineWeb validation-loss target with fewer steps / less wall-clock.",
    "objective": {"metric": "val_loss", "direction": "minimize", "target": 3.28},
    "budget": {"max_experiments": 12, "max_runtime_per_experiment_sec": 1800},
    "adapter": "modded_nanogpt",
    "patcher": "agent-edit",  # Kun-driven edits to train_gpt.py. Mode-B ingest may use "external".
    "model": "claude-opus-4-8",
    "editable_files": ["train_gpt.py"],
    "allowed_changes": [
        "optimizer", "muon_lr", "adam_lr", "momentum", "warmup_steps",
        "attention", "position_embedding", "logit_softcap", "weight_decay",
    ],
    "constraints": [],
}


@dataclass
class Attempt:
    """One nanogpt experiment = one attempted change (new optimizer / attention tweak / ...)."""
    exp_id: str
    parent: str | None
    hypothesis: str
    changes: dict                                  # {"optimizer": "muon", ...} — what changed
    diff: str                                      # real unified diff of train_gpt.py
    metrics: list[tuple[str, float, int]]          # [(name, value, step), ...] real time series
    status: str                                    # "valid" | "buggy"
    final_metrics: dict | None = None              # {"val_loss":.., "runtime_sec":.., "tokens_per_sec":..}
    failure: dict | None = None                    # buggy: {"failure_type","message","last_metrics"}
    verdict: str = "promote"                       # "promote" | "reject"
    summary: str = ""
    evidence: list[str] = field(default_factory=list)
    command: str = "torchrun --standalone --nproc_per_node=8 train_gpt.py"
    operator: str | None = None                    # inferred if None (draft/debug/improve)
    branch: str = "branch_main"
    timestamp: str | None = None                   # real ISO-8601 ts if available


@dataclass
class Fork:
    """A human fork: spawns a new branch off a parent experiment (mirrors the sample replay)."""
    branch_id: str
    parent_experiment_id: str
    name: str
    instruction: str
    reason: str
    constraint: dict | None = None                 # optional canonical constraint object (human)
    timestamp: str | None = None


# --- emit --------------------------------------------------------------------
def build_events(meta: dict, attempts: list[Attempt], forks: list[Fork] | None = None) -> list[dict]:
    mission_id = meta["mission_id"]
    by_id = {a.exp_id: a for a in attempts}
    forks_by_branch = {f.branch_id: f for f in (forks or [])}
    seen_branches = {"branch_main"}
    events: list[dict] = []
    seq = 0

    def emit(type_, payload, ts=None, **env):
        nonlocal seq
        seq += 1
        rec = {
            "schema_version": 1,
            "event_id": f"evt_{seq:04d}",
            "timestamp": ts or f"2026-06-27T20:{(seq // 60):02d}:{(seq % 60):02d}Z",
            "type": type_,
            "mission_id": mission_id,
            "payload": payload,
        }
        rec.update(env)
        events.append(rec)

    def infer_operator(a: Attempt) -> str:
        if a.operator:
            return a.operator
        if a.parent is None:
            return "draft"
        p = by_id.get(a.parent)
        return "debug" if (p and p.status == "buggy") else "improve"

    emit("mission_created", {k: v for k, v in meta.items() if k != "mission_id"})
    emit("mission_started", {"mode": "replay", "started_by": "converter"})

    for a in attempts:
        # If this attempt opens a new (human) branch, emit the fork + branch (+ constraint) first.
        if a.branch not in seen_branches:
            f = forks_by_branch.get(a.branch)
            if f is not None:
                emit("fork_created",
                     {"instruction": f.instruction, "reason": f.reason},
                     ts=f.timestamp or a.timestamp, branch_id=f.branch_id,
                     parent_experiment_id=f.parent_experiment_id, actor=HUMAN)
                emit("branch_created",
                     {"name": f.name, "source": "human_fork", "reason": f.reason},
                     ts=f.timestamp or a.timestamp, branch_id=f.branch_id,
                     parent_experiment_id=f.parent_experiment_id)
                if f.constraint:
                    emit("constraint_added", f.constraint, ts=f.timestamp or a.timestamp,
                         branch_id=f.branch_id, actor=HUMAN)
            seen_branches.add(a.branch)

        op = infer_operator(a)
        emit("experiment_proposed",
             {"operator": op, "hypothesis": a.hypothesis, "changes": a.changes,
              "rationale": a.summary or a.hypothesis},
             ts=a.timestamp, experiment_id=a.exp_id, branch_id=a.branch,
             parent_experiment_id=a.parent, actor=PLANNER)
        emit("file_diff_created", {"file_path": "train_gpt.py", "diff": a.diff},
             ts=a.timestamp, experiment_id=a.exp_id, branch_id=a.branch)
        emit("experiment_started",
             {"command": a.command, "workspace_path": f"runs/nanogpt/{a.exp_id}", "timeout_sec": 1800},
             ts=a.timestamp, experiment_id=a.exp_id, branch_id=a.branch, parent_experiment_id=a.parent)
        for name, value, step in a.metrics:
            emit("metric_logged", {"name": name, "value": value, "step": step},
                 ts=a.timestamp, experiment_id=a.exp_id, branch_id=a.branch)

        if a.status == "valid":
            emit("experiment_finished", {"status": "success", "final_metrics": a.final_metrics or {}},
                 ts=a.timestamp, experiment_id=a.exp_id, branch_id=a.branch)
        else:
            emit("experiment_failed", a.failure or {"failure_type": "error", "message": "run failed"},
                 ts=a.timestamp, experiment_id=a.exp_id, branch_id=a.branch)
            # NaN on a numeric change -> a learned constraint with a machine-checkable bound
            learned = _bound_from_nan(a)
            if learned:
                emit("constraint_learned", learned, ts=a.timestamp,
                     experiment_id=a.exp_id, branch_id=a.branch)

        emit("evaluation_created",
             {"verdict": a.verdict, "summary": a.summary, "evidence": a.evidence},
             ts=a.timestamp, experiment_id=a.exp_id, branch_id=a.branch, actor=EVALUATOR)
        # Decision -> node lifecycle: a failed/NaN node uses "retry_debug" (stays buggy/red, like
        # the sample replay); a valid-but-worse node uses "reject"; an advance uses "promote".
        if a.status == "buggy":
            decision = "retry_debug"
        elif a.verdict == "promote":
            decision = "promote"
        else:
            decision = "reject"
        emit("decision_created",
             {"decision": decision,
              "rationale": a.summary,
              "next_action": {"type": "propose_next_experiment",
                              "parent_experiment_id": a.parent or a.exp_id}},
             ts=a.timestamp, experiment_id=a.exp_id, branch_id=a.branch)

    # mission_finished: best = lowest val_loss among valid attempts
    valid = [a for a in attempts if a.status == "valid" and (a.final_metrics or {}).get("val_loss") is not None]
    best = min(valid, key=lambda a: a.final_metrics["val_loss"], default=None)
    emit("mission_finished",
         {"status": "completed", "reason": "max_experiments_reached",
          "best_experiment_id": best.exp_id if best else None,
          "best_metric": {"name": "val_loss", "value": best.final_metrics["val_loss"]} if best else None})
    return events


_LR_HINT = re.compile(r"(lr|learning_rate)", re.I)


def _bound_from_nan(a: Attempt) -> dict | None:
    """If a run NaN'd after raising a numeric param, learn an upper-bound constraint.

    For learning-rate-like params we follow CONTRACT §3's deterministic rule (NaN at x ->
    bound at x*0.5); for other numeric params we bound at the offending value itself. The
    `bound` is what the planner hard-rejects against, so the next proposal must respect it.
    """
    ft = (a.failure or {}).get("failure_type", "")
    if "nan" not in ft.lower():
        return None
    numeric = {k: v for k, v in a.changes.items() if isinstance(v, (int, float))}
    if not numeric:
        return None
    param, value = next(iter(numeric.items()))
    bound_value = round(value * 0.5, 6) if _LR_HINT.search(param) else value
    return {
        "constraint_id": f"learned_{a.exp_id}",
        "source": "learned",
        "text": f"{param} = {value} caused {ft} in {a.exp_id}; treat {param} > {bound_value} as banned.",
        "applies_to": [param],
        "bound": {"param": param, "op": ">", "value": bound_value},
        "confidence": "high",
        "supporting_experiments": [a.exp_id],
    }


# --- artifact parsing (wire this to your real run) ---------------------------
_METRIC_RE = re.compile(r"step[=:\s]+(\d+).*?val[_ ]loss[=:\s]+([0-9.]+)", re.I)


def parse_metric_lines(text: str) -> list[tuple[str, float, int]]:
    """Helper: pull (val_loss, step) points out of a training log. Adjust the regex to your format."""
    out = []
    for m in _METRIC_RE.finditer(text):
        out.append(("val_loss", float(m.group(2)), int(m.group(1))))
    return out


def parse_run_dir(run_dir: pathlib.Path) -> tuple[list[Attempt], list[Fork]]:
    """TODO: map your real artifacts -> ([Attempt], [Fork]).

    auto-nanogpt / Claude-Code runs typically leave: a markdown harness (e.g. scratchpad/THREAD.md),
    git history (one commit per attempt -> `git show` for the diff), and per-attempt training logs.
    Suggested shape:
      - one Attempt per attempt/commit; diff = `git show <sha> -- train_gpt.py`
      - metrics via parse_metric_lines(open(log).read()) (+ tokens_per_sec from throughput lines)
      - status = "buggy" if the log contains NaN/crash else "valid"
      - hypothesis/summary from the THREAD.md entry for that attempt
      - Fork entries for any human fork recorded in the harness
    Until wired, raise so nobody ships empty output by accident.
    """
    raise NotImplementedError(
        "parse_run_dir() not wired yet. Either implement it for your artifact format, "
        "or run without --run-dir to emit the SYNTHESIZED stand-in trajectory (ATTEMPTS/FORKS)."
    )


# --- SYNTHESIZED attempts (realistic stand-in; REPLACE with the captured run) ------------
# A plausible, internally-consistent modded-nanogpt arc. NOT a captured run — see the
# honesty guard above and examples/replays/nanogpt.README.md. Numbers (val_loss descending
# toward the 3.28 target, ~120k tok/s on 8xH100, ~10 min/run) are realistic stand-ins.

_BASELINE_DIFF = (
    "--- a/train_gpt.py\n"
    "+++ b/train_gpt.py\n"
    "@@ -378,11 +378,11 @@ class Hyperparameters:\n"
    "     sequence_length = 1024\n"
    "     num_iterations = 3000\n"
    "-    learning_rate = 1e-3\n"
    "+    learning_rate = 6e-4\n"
    "     weight_decay = 0.0\n"
    "-    val_loss_every = 0\n"
    "+    val_loss_every = 1000\n"
)

_MUON_DIFF = (
    "--- a/train_gpt.py\n"
    "+++ b/train_gpt.py\n"
    "@@ -118,6 +118,40 @@\n"
    "+def zeropower_via_newtonschulz5(G, steps: int):\n"
    "+    # Orthogonalize the update via a quintic Newton-Schulz iteration (bf16).\n"
    "+    assert G.ndim == 2\n"
    "+    a, b, c = (3.4445, -4.7750, 2.0315)\n"
    "+    X = G.bfloat16()\n"
    "+    X = X / (X.norm() + 1e-7)\n"
    "+    transposed = G.size(0) > G.size(1)\n"
    "+    if transposed:\n"
    "+        X = X.T\n"
    "+    for _ in range(steps):\n"
    "+        A = X @ X.T\n"
    "+        B = b * A + c * A @ A\n"
    "+        X = a * X + B @ X\n"
    "+    if transposed:\n"
    "+        X = X.T\n"
    "+    return X\n"
    "+\n"
    "+class Muon(torch.optim.Optimizer):\n"
    "+    def __init__(self, params, lr=0.02, momentum=0.95, ns_steps=5):\n"
    "+        super().__init__(params, dict(lr=lr, momentum=momentum, ns_steps=ns_steps))\n"
    "+    @torch.no_grad()\n"
    "+    def step(self):\n"
    "+        for group in self.param_groups:\n"
    "+            for p in group['params']:\n"
    "+                if p.grad is None:\n"
    "+                    continue\n"
    "+                state = self.state[p]\n"
    "+                if 'momentum_buffer' not in state:\n"
    "+                    state['momentum_buffer'] = torch.zeros_like(p.grad)\n"
    "+                buf = state['momentum_buffer']\n"
    "+                buf.mul_(group['momentum']).add_(p.grad)\n"
    "+                g = p.grad.add(buf, alpha=group['momentum'])\n"
    "+                g = zeropower_via_newtonschulz5(g, steps=group['ns_steps'])\n"
    "+                p.add_(g.view_as(p), alpha=-group['lr'])\n"
    "@@ -470,8 +504,13 @@\n"
    "-    optimizer = torch.optim.AdamW(model.parameters(), lr=6e-4, weight_decay=0.0)\n"
    "-    optimizers = [optimizer]\n"
    "+    # Muon on the 2D hidden matrices; AdamW keeps the embeddings, lm_head and scalars.\n"
    "+    hidden_matrix_params = [p for p in model.blocks.parameters() if p.ndim == 2]\n"
    "+    scalar_and_embed = [p for p in model.parameters() if p.ndim < 2]\n"
    "+    scalar_and_embed += list(model.wte.parameters()) + list(model.lm_head.parameters())\n"
    "+    adam = torch.optim.AdamW(scalar_and_embed, lr=6e-4, betas=(0.9, 0.95), weight_decay=0.0)\n"
    "+    muon = Muon(hidden_matrix_params, lr=0.02, momentum=0.95)\n"
    "+    optimizers = [adam, muon]\n"
)

_AGGRESSIVE_LR_DIFF = (
    "--- a/train_gpt.py\n"
    "+++ b/train_gpt.py\n"
    "@@ -508,7 +508,7 @@\n"
    "     adam = torch.optim.AdamW(scalar_and_embed, lr=6e-4, betas=(0.9, 0.95), weight_decay=0.0)\n"
    "-    muon = Muon(hidden_matrix_params, lr=0.02, momentum=0.95)\n"
    "+    muon = Muon(hidden_matrix_params, lr=0.05, momentum=0.95)  # push the Muon LR\n"
    "     optimizers = [adam, muon]\n"
)

_WARMUP_DIFF = (
    "--- a/train_gpt.py\n"
    "+++ b/train_gpt.py\n"
    "@@ -508,7 +508,7 @@\n"
    "     adam = torch.optim.AdamW(scalar_and_embed, lr=6e-4, betas=(0.9, 0.95), weight_decay=0.0)\n"
    "-    muon = Muon(hidden_matrix_params, lr=0.02, momentum=0.95)\n"
    "+    muon = Muon(hidden_matrix_params, lr=0.024, momentum=0.95)\n"
    "     optimizers = [adam, muon]\n"
    "@@ -540,6 +540,9 @@\n"
    "+    warmup_steps = 256\n"
    "     def get_lr(it):\n"
    "+        if it < warmup_steps:\n"
    "+            return (it + 1) / warmup_steps\n"
    "         return 1.0\n"
)

_QKNORM_DIFF = (
    "--- a/train_gpt.py\n"
    "+++ b/train_gpt.py\n"
    "@@ -150,9 +150,11 @@ class CausalSelfAttention(nn.Module):\n"
    "     def forward(self, x):\n"
    "         B, T, C = x.size()\n"
    "         q, k, v = self.c_attn(x).split(self.n_embd, dim=2)\n"
    "         q = q.view(B, T, self.n_head, C // self.n_head)\n"
    "         k = k.view(B, T, self.n_head, C // self.n_head)\n"
    "+        # QK-norm: RMS-normalize queries/keys before RoPE for stabler attention logits.\n"
    "+        q = F.rms_norm(q, (q.size(-1),))\n"
    "+        k = F.rms_norm(k, (k.size(-1),))\n"
    "         q, k = apply_rotary(q), apply_rotary(k)\n"
)

_LEARNED_POS_DIFF = (
    "--- a/train_gpt.py\n"
    "+++ b/train_gpt.py\n"
    "@@ -150,11 +150,11 @@ class CausalSelfAttention(nn.Module):\n"
    "     def forward(self, x):\n"
    "         B, T, C = x.size()\n"
    "         q, k, v = self.c_attn(x).split(self.n_embd, dim=2)\n"
    "         q = q.view(B, T, self.n_head, C // self.n_head)\n"
    "         k = k.view(B, T, self.n_head, C // self.n_head)\n"
    "         q = F.rms_norm(q, (q.size(-1),))\n"
    "         k = F.rms_norm(k, (k.size(-1),))\n"
    "-        q, k = apply_rotary(q), apply_rotary(k)\n"
    "+        # swap RoPE for learned absolute position embeddings (wpe added in __init__)\n"
    "@@ -210,6 +210,7 @@ class GPT(nn.Module):\n"
    "         self.wte = nn.Embedding(config.vocab_size, config.n_embd)\n"
    "+        self.wpe = nn.Embedding(config.block_size, config.n_embd)\n"
)

_SOFTCAP_DIFF = (
    "--- a/train_gpt.py\n"
    "+++ b/train_gpt.py\n"
    "@@ -228,7 +228,9 @@ class GPT(nn.Module):\n"
    "         x = self.transformer_norm(x)\n"
    "-        logits = self.lm_head(x)\n"
    "+        logits = self.lm_head(x)\n"
    "+        # logit soft-cap: tanh-bound the output logits for a small, stable gain.\n"
    "+        logits = 15.0 * torch.tanh(logits / 15.0)\n"
    "         return logits\n"
)


ATTEMPTS: list[Attempt] = [
    Attempt(
        "exp_000", None,
        "Baseline GPT-2 (124M) with AdamW on FineWeb.",
        {"optimizer": "adamw", "learning_rate": 6e-4},
        _BASELINE_DIFF,
        [("val_loss", 3.55, 1000), ("val_loss", 3.46, 2000), ("val_loss", 3.40, 3000),
         ("tokens_per_sec", 118000, 3000)],
        "valid",
        final_metrics={"val_loss": 3.40, "runtime_sec": 612, "tokens_per_sec": 118000},
        verdict="promote", summary="AdamW baseline lands at val_loss 3.40 in 3000 steps.",
        evidence=["baseline established at 3.40", "still 0.12 above the 3.28 target"],
    ),
    Attempt(
        "exp_001", "exp_000",
        "Replace AdamW with the Muon optimizer on the 2D hidden matrices (keep AdamW for embeddings/lm_head/scalars).",
        {"optimizer": "muon", "muon_lr": 0.02},
        _MUON_DIFF,
        [("val_loss", 3.44, 1000), ("val_loss", 3.34, 2000), ("val_loss", 3.30, 3000),
         ("tokens_per_sec", 121500, 3000)],
        "valid",
        final_metrics={"val_loss": 3.30, "runtime_sec": 598, "tokens_per_sec": 121500},
        verdict="promote", summary="Muon improved val_loss 3.40 -> 3.30 at equal step budget.",
        evidence=["-0.10 vs baseline", "throughput up ~3% (Newton-Schulz is cheap)", "approaching target"],
    ),
    Attempt(
        "exp_002", "exp_001",
        "Push the Muon LR to 0.05 to converge in fewer steps.",
        {"muon_lr": 0.05},
        _AGGRESSIVE_LR_DIFF,
        [("val_loss", 3.50, 500)],
        "buggy",
        failure={"failure_type": "nan_detected",
                 "message": "Muon update exploded; loss became NaN around step ~640.",
                 "last_metrics": {"train_loss": "nan", "val_loss": 3.50},
                 "stdout_path": "runs/nanogpt/exp_002/stdout.log",
                 "stderr_path": "runs/nanogpt/exp_002/stderr.log"},
        verdict="reject", summary="muon_lr=0.05 diverged to NaN; learned an upper bound on muon_lr.",
        evidence=["NaN at ~step 640", "val_loss spiked to 3.50 before divergence"],
    ),
    Attempt(
        "exp_003", "exp_001",
        "Back off the Muon LR below the learned bound and add a 256-step warmup for stability.",
        {"muon_lr": 0.024, "warmup_steps": 256},
        _WARMUP_DIFF,
        [("val_loss", 3.41, 1000), ("val_loss", 3.31, 2000), ("val_loss", 3.27, 3000),
         ("tokens_per_sec", 121000, 3000)],
        "valid",
        final_metrics={"val_loss": 3.27, "runtime_sec": 601, "tokens_per_sec": 121000},
        verdict="promote",
        summary="Respecting the learned muon_lr bound (<=0.025) + warmup: val_loss 3.27 — crosses the 3.28 target.",
        evidence=["honors learned_exp_002 (muon_lr <= 0.025)", "-0.03 vs exp_001", "first run under target 3.28"],
    ),
    Attempt(
        "exp_004", "exp_003",
        "Add QK-norm (RMS-normalize queries/keys before RoPE) for stabler attention logits.",
        {"attention": "qk_norm"},
        _QKNORM_DIFF,
        [("val_loss", 3.39, 1000), ("val_loss", 3.28, 2000), ("val_loss", 3.245, 3000),
         ("tokens_per_sec", 120500, 3000)],
        "valid",
        final_metrics={"val_loss": 3.245, "runtime_sec": 607, "tokens_per_sec": 120500},
        verdict="promote", summary="QK-norm improved val_loss 3.27 -> 3.245 (new best on main).",
        evidence=["-0.025 vs exp_003", "throughput ~flat", "stable attention logits"],
    ),
    Attempt(
        "exp_005", "exp_004",
        "Swap RoPE for learned absolute position embeddings.",
        {"position_embedding": "learned_absolute"},
        _LEARNED_POS_DIFF,
        [("val_loss", 3.42, 1000), ("val_loss", 3.33, 2000), ("val_loss", 3.29, 3000),
         ("tokens_per_sec", 119800, 3000)],
        "valid",
        final_metrics={"val_loss": 3.29, "runtime_sec": 610, "tokens_per_sec": 119800},
        verdict="reject", summary="Learned absolute pos-emb regressed val_loss 3.245 -> 3.29; keep RoPE+QK-norm.",
        evidence=["+0.045 worse than exp_004", "back above target 3.28", "RoPE generalizes better here"],
    ),
    # --- human fork off the best STABLE node (exp_004), on a new branch ---
    Attempt(
        "exp_006", "exp_004",
        "On the fork: add a tanh logit soft-cap (cap 15) for a small, stable gain.",
        {"logit_softcap": 15},
        _SOFTCAP_DIFF,
        [("val_loss", 3.38, 1000), ("val_loss", 3.27, 2000), ("val_loss", 3.238, 3000),
         ("tokens_per_sec", 120300, 3000)],
        "valid",
        final_metrics={"val_loss": 3.238, "runtime_sec": 606, "tokens_per_sec": 120300},
        verdict="promote", summary="Logit soft-cap improved val_loss 3.245 -> 3.238 (overall best).",
        evidence=["-0.007 vs exp_004", "honors human muon_lr bound", "stable, under target"],
        branch="branch_human_001",
    ),
]

FORKS: list[Fork] = [
    Fork(
        branch_id="branch_human_001",
        parent_experiment_id="exp_004",
        name="human-fork-softcap",
        instruction="Fork from the best stable node (QK-norm). Keep RoPE, stay under the learned muon_lr bound, and try a logit soft-cap.",
        reason="exp_004 is the best stable node; explore a soft-cap without revisiting the unstable high-LR / learned-pos directions.",
        constraint={
            "constraint_id": "human_001",
            "source": "human",
            "text": "Ban muon_lr > 0.025 (NaN'd at 0.05 in exp_002).",
            "applies_to": ["muon_lr"],
            "bound": {"param": "muon_lr", "op": ">", "value": 0.025},
        },
    ),
]


def main():
    ap = argparse.ArgumentParser(description="Convert a nanogpt run into Kun events.jsonl")
    ap.add_argument("-o", "--out", default="examples/replays/nanogpt.events.jsonl")
    ap.add_argument("--run-dir", help="auto-parse this artifact dir (requires wiring parse_run_dir)")
    args = ap.parse_args()

    if args.run_dir:
        attempts, forks = parse_run_dir(pathlib.Path(args.run_dir))
        synthesized = False
    else:
        attempts, forks = ATTEMPTS, FORKS
        synthesized = True

    events = build_events(MISSION_META, attempts, forks)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    print(f"wrote {len(events)} events ({len(attempts)} experiments) -> {out}")
    if synthesized:
        print(
            "\n  NOTE: this is a SYNTHESIZED stand-in trajectory (hand-authored from realistic "
            "modded-nanogpt numbers), NOT a captured GPU run. It stands in for the overnight "
            "Mode-A + agent-edit run until that run is recorded; then re-run with --run-dir to "
            "drop in the real numbers. See examples/replays/nanogpt.README.md. (honesty guard)"
        )


if __name__ == "__main__":
    main()
