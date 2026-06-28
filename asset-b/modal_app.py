"""
Modal wrapper for Asset B — a recorded EXTERNAL nanogpt autoresearch run (Mode-B fallback).

Brain/muscle split:
  - BRAIN (free): the agent edits `train_gpt.py` on your LAPTOP and commits per attempt.
  - MUSCLE (billed per-second): each experiment dispatches training to ONE H100 on Modal.
Modal has no idle charges, so you only pay while a training run is actually executing.

Place this file in the ROOT of your local modded-nanogpt clone, then (see asset-b/README.md):
    modal run modal_app.py --action download         # once: pull a few FineWeb chunks to a Volume
    modal run modal_app.py --action train            # per attempt: trains the CURRENT train_gpt.py on 1x H100
    modal volume get nanogpt-logs <run_id>.txt ./logs/   # pull a full run log back for the converter

API: every call here is VERIFIED against modal 1.5.1 (the version in backend/.venv) —
from_registry(add_python=), pip_install_from_requirements, run_commands, add_local_dir(ignore=),
Volume.from_name(create_if_missing=), function(gpu=,volumes=,timeout=), local_entrypoint.
If you upgrade Modal later and something errors, check https://modal.com/docs.

Honesty guard (doc 07): this is an *external* run ingested via Kun's open contract — never
narrate it as "Kun drove it" (that's Mode A) or as live. Capture REAL numbers only.
"""
import modal

# REPO is the path INSIDE the Modal cloud container (containers run as root, so /root is home).
# It is NOT a folder on your laptop. Your local modded-nanogpt dir (the "." passed to
# add_local_dir below) is copied here at build time. Don't change this to a /Users/... path.
REPO = "/root/modded-nanogpt"
DATA_DIR = f"{REPO}/data/fineweb10B"   # cached_fineweb10B.py writes here; we back it with a Volume
LOGS_DIR = f"{REPO}/logs"             # train_gpt.py writes logs/<run_id>.txt; back it with a Volume
# 8 = the model's NATIVE config (world_size=8, grad_accum=1, sharded Muon) that every record was
# trained on. Single-GPU (world_size=1 -> grad_accum=8, comms="none") trains INCORRECTLY for this
# SOTA config (val_loss rises/diverges), so we run the real 8-GPU path.
# Note: a single 8xH100 container can take a few retries to provision (capacity); just re-run.
N_GPU = 8

# --- Image: CUDA 12.8 + py3.12 + requirements + torch nightly cu128 ---
# NOTE: the repo's committed Dockerfile says cu126, but it is STALE (last touched 2025-05). The
# current code's custom CUDA kernels (triton_kernels.py, compiled via torch.cuda._compile_kernel with
# cuda_include_dirs=/usr/local/cuda/include) use 12.8-era intrinsics like __tanhf, and the real record
# logs show "PyTorch 2.11.0+cu128 compiled for CUDA 12.8". cu126 fails with: __tanhf is undefined.
# The local-dir copy is LAST so editing train_gpt.py only re-uploads that tiny layer (torch stays cached).
image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04", add_python="3.12"
    )
    .apt_install("git", "build-essential")
    .pip_install_from_requirements("requirements.txt")
    .run_commands(
        "pip install --pre torch --index-url "
        "https://download.pytorch.org/whl/nightly/cu128 --upgrade"
    )
    # copy=True bakes the repo into the image filesystem, so the data/ and logs/ Volumes overlay
    # cleanly on real dirs (a runtime mount with Volumes nested inside it is fragile). "." is your
    # LOCAL modded-nanogpt dir (the cwd where you run `modal`); it lands at REPO in the container.
    .add_local_dir(".", REPO, copy=True,
                   ignore=["fineweb10B", "logs", ".git", "__pycache__",
                           "*.bin", "img", "records", "evals", "THREAD.md"])
)

app = modal.App("kun-asset-b-nanogpt", image=image)

# Persistent storage that survives across attempts.
data_vol = modal.Volume.from_name("nanogpt-fineweb", create_if_missing=True)
logs_vol = modal.Volume.from_name("nanogpt-logs", create_if_missing=True)
cache_vol = modal.Volume.from_name("nanogpt-compile-cache", create_if_missing=True)  # torch.compile/triton cache
CACHE_DIR = "/cache"


@app.function(volumes={DATA_DIR: data_vol}, timeout=60 * 60)
def download_data(num_chunks: int = 8):
    """Download the val shard + `num_chunks` train shards (~100M tokens each) to the data Volume.
    The speedrun trains on <400M tokens, so ~4-8 chunks is plenty for a demo trajectory.
    Run ONCE; the Volume persists."""
    import subprocess
    subprocess.run(["python", "data/cached_fineweb10B.py", str(num_chunks)], cwd=REPO, check=True)
    data_vol.commit()
    print(f"OK: downloaded val + {num_chunks} train chunks to the nanogpt-fineweb Volume")


@app.function(gpu=f"H100:{N_GPU}", volumes={DATA_DIR: data_vol, LOGS_DIR: logs_vol, CACHE_DIR: cache_vol}, timeout=45 * 60)
def train(run_id: str | None = None, disable_fp8: bool = False) -> dict:
    """Run ONE experiment: {N_GPU}x-H100 train of the CURRENT (edited) train_gpt.py.

    The 45-min timeout is a runaway-cost guard (~$3 max/run on H100); raise it only if a
    legitimately longer run is needed.

    Hyperparameters (num_scheduled_iterations, model size, lr, scheduler, ...) live INSIDE
    train_gpt.py and are edited by the agent — there are no CLI knobs. For a demo, shrink
    num_scheduled_iterations (default 1380) to a few hundred so a run is a few minutes.
    NOTE: the FIRST run compiles for ~20 min on one GPU; later runs are faster because the
    torch.compile + triton caches are persisted on a Volume. Training itself is cheap
    (~0.3-0.5s/step), so compile dominates — prefer running ENOUGH steps to learn, not fewer.

    run.sh is `torchrun --standalone --nproc_per_node=8 train_gpt.py` — we run that native 8-GPU
    config (grad_accum=1, sharded Muon), the one the records were trained on.
    Keep FP8 ON for H100 (Hopper); only set disable_fp8=True on non-Hopper cards.
    """
    import subprocess, os, glob, uuid
    rid = run_id or uuid.uuid4().hex[:8]
    env = dict(os.environ)
    if disable_fp8:
        env["DISABLE_FP8"] = "1"
    # Persist torch.compile (inductor) + triton caches on a Volume so warmup drops from ~20 min to
    # ~minutes after the first run. Non-structural edits (lr / optimizer / scheduler / steps) reuse
    # the cache; only architecture changes force a fuller recompile.
    env["TORCHINDUCTOR_CACHE_DIR"] = f"{CACHE_DIR}/inductor"
    env["TRITON_CACHE_DIR"] = f"{CACHE_DIR}/triton"
    os.makedirs(env["TORCHINDUCTOR_CACHE_DIR"], exist_ok=True)
    os.makedirs(env["TRITON_CACHE_DIR"], exist_ok=True)
    before = set(glob.glob(f"{LOGS_DIR}/*.txt"))   # snapshot so we return THIS run's log, not a stale one
    cmd = ["torchrun", "--standalone", f"--nproc_per_node={N_GPU}", "train_gpt.py"]
    print(f"[{rid}] launching: {' '.join(cmd)}  (first run ~20 min compile; later runs faster via cached kernels)")
    # No capture_output → the child's stdout/stderr STREAM live to the Modal run terminal.
    r = subprocess.run(cmd, cwd=REPO, env=env)
    logs_vol.commit()
    cache_vol.commit()   # persist the populated compile cache for the next run
    # train_gpt.py writes logs/<its-own-uuid>.txt; pick the NEW file created by this run.
    new_logs = sorted(set(glob.glob(f"{LOGS_DIR}/*.txt")) - before, key=os.path.getmtime)
    newest = new_logs[-1] if new_logs else None
    if newest:
        tail = open(newest).read()[-6000:]
        log_name = os.path.basename(newest)
    else:
        tail = "(no new log file — the run likely failed early; see the streamed output above)"
        log_name = None
    status = "ok" if r.returncode == 0 else f"FAILED (exit {r.returncode})"
    print(f"[{rid}] {status}; log file on Volume: {log_name}")
    return {"run_id": rid, "log_name": log_name, "returncode": r.returncode, "tail": tail}


@app.function(volumes={LOGS_DIR: logs_vol})
def list_logs() -> list:
    import glob, os
    return [os.path.basename(p) for p in sorted(glob.glob(f"{LOGS_DIR}/*.txt"), key=os.path.getmtime)]


@app.local_entrypoint()
def main(action: str = "train", num_chunks: int = 8, disable_fp8: bool = False):
    """`modal run modal_app.py --action {download|train|logs}`"""
    if action == "download":
        download_data.remote(num_chunks)
    elif action == "train":
        out = train.remote(disable_fp8=disable_fp8)
        print("\n===== LOG TAIL (read val_loss from here) =====")
        print(out["tail"])
        print(f"\nreturncode={out['returncode']}  log_file={out['log_name']}")
        print(f"pull the full log:  modal volume get nanogpt-logs {out['log_name']} ./logs/")
    elif action == "logs":
        for name in list_logs.remote():
            print(name)
    else:
        raise SystemExit(f"unknown action: {action} (use download|train|logs)")
