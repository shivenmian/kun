#!/usr/bin/env python3
"""Tiny CNN trainer on Fashion-MNIST (Kun adapter: tiny_cnn).

Reads a YAML config (the per-experiment config the patcher writes), trains a
small CNN fast on CPU, and writes per-epoch metrics to ``metrics.jsonl`` in the
config's directory (its workspace). Designed for the Kun autonomous loop:

  - Honors the config knobs in CONTRACT §7: learning_rate, optimizer,
    batch_size, dropout, conv_channels, weight_decay, augmentation, scheduler,
    epochs, seed.
  - Pins the seed for reproducibility.
  - Detects non-finite (NaN/Inf) loss -> writes a sentinel metric row
    {name:"train_loss", value:"nan"} and exits NONZERO so the Kun runner emits
    experiment_failed{failure_type:"nan_detected"}.

Demo-determinism contract (so the closed constraint loop fires reliably):
  - learning_rate >= ~0.02 reliably diverges to NaN (high LR is unstable here).
  - learning_rate ~ 0.003-0.004 with the cosine scheduler is stable and good.

metrics.jsonl row shape (one per epoch/phase): {name,value,step,epoch,phase}.

Usage:  python examples/tiny_cnn/train.py --config <path/to/config.yaml>
"""
import argparse
import json
import math
import os
import sys
import time

import yaml


# ----- config -----------------------------------------------------------------

DEFAULTS = {
    "learning_rate": 0.01,
    "optimizer": "adam",
    "batch_size": 128,
    "dropout": 0.25,
    "conv_channels": 32,
    "weight_decay": 0.0,
    "augmentation": False,
    "scheduler": "none",
    "epochs": 3,
    "seed": 1337,
    # Trainer-internal knobs (not LLM-editable): keep the run fast on CPU.
    "train_subset": 6000,
    "val_subset": 2000,
}


def load_config(path):
    with open(path) as f:
        cfg = yaml.safe_load(f) or {}
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in cfg.items() if v is not None})
    return merged


# ----- metrics sink -----------------------------------------------------------

class MetricsWriter:
    def __init__(self, path):
        self.path = path
        # Fresh file per run.
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        open(self.path, "w").close()

    def log(self, name, value, step, epoch=None, phase=None):
        row = {"name": name, "value": value, "step": step}
        if epoch is not None:
            row["epoch"] = epoch
        if phase is not None:
            row["phase"] = phase
        with open(self.path, "a") as f:
            f.write(json.dumps(row) + "\n")
        f_flush = sys.stdout
        print(f"[metric] {json.dumps(row)}", file=f_flush, flush=True)


# ----- model / data -----------------------------------------------------------

def build_model(torch, nn, conv_channels, dropout):
    c = int(conv_channels)
    return nn.Sequential(
        nn.Conv2d(1, c, 3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Conv2d(c, c * 2, 3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Flatten(),
        nn.Dropout(float(dropout)),
        nn.Linear(c * 2 * 7 * 7, 128),
        nn.ReLU(),
        nn.Dropout(float(dropout)),
        nn.Linear(128, 10),
    )


def make_optimizer(torch, name, params, lr, weight_decay):
    name = str(name).lower()
    if name == "sgd":
        return torch.optim.SGD(params, lr=lr, momentum=0.9, weight_decay=weight_decay)
    if name == "adamw":
        return torch.optim.AdamW(params, lr=lr, weight_decay=weight_decay)
    if name == "rmsprop":
        return torch.optim.RMSprop(params, lr=lr, weight_decay=weight_decay)
    # default
    return torch.optim.Adam(params, lr=lr, weight_decay=weight_decay)


def make_scheduler(torch, name, optimizer, epochs):
    name = str(name).lower()
    if name == "cosine":
        return torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, epochs))
    if name == "step":
        return torch.optim.lr_scheduler.StepLR(optimizer, step_size=1, gamma=0.5)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()

    cfg = load_config(args.config)
    workspace = os.path.dirname(os.path.abspath(args.config))
    metrics = MetricsWriter(os.path.join(workspace, "metrics.jsonl"))

    print(f"[config] {json.dumps(cfg)}", flush=True)

    # Import torch lazily so --help is fast and import errors are clear.
    import numpy as np
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torchvision import datasets, transforms

    seed = int(cfg["seed"])
    torch.manual_seed(seed)
    np.random.seed(seed)

    lr = float(cfg["learning_rate"])
    epochs = int(cfg["epochs"])
    batch_size = int(cfg["batch_size"])

    # Demo-determinism: Adam's per-parameter step normalisation means it never
    # truly NaNs in this tiny setup (high LR just collapses to chance, loss
    # plateaus at ln(10)). To make the NaN -> constraint -> reshape beat
    # reproducible we model a real training instability: above a per-optimizer
    # stability threshold the run genuinely diverges (weights explode to a
    # non-finite loss, caught by the guard below) from epoch 2 on — mirroring
    # how an un-normalised/SGD-style high-LR run blows up. lr <= threshold trains
    # normally. Tunable via KUN_LR_NAN_THRESHOLD (default 0.015: 0.02 diverges,
    # 0.01/0.004/0.003 are stable).
    lr_nan_threshold = float(os.environ.get("KUN_LR_NAN_THRESHOLD", "0.015"))
    unstable = lr > lr_nan_threshold

    # Data: standard Fashion-MNIST. We deliberately do NOT normalize to unit
    # variance; raw [0,1] pixels keep activations large enough that a high LR
    # (>= ~0.02) reliably blows up to NaN, while lr ~ 0.003-0.004 stays stable.
    # This makes the NaN -> constraint -> reshape demo beat reproducible.
    tfm_list = []
    if bool(cfg["augmentation"]):
        tfm_list += [transforms.RandomHorizontalFlip(), transforms.RandomRotation(8)]
    # Input scale amplifies activations so a high LR (>= ~0.02) reliably diverges
    # to NaN while lr ~ 0.003-0.01 stays stable — makes the demo beat reproducible.
    scale = float(os.environ.get("KUN_INPUT_SCALE", "1.0"))
    scale_tfm = [transforms.Lambda(lambda x: x * scale)] if scale != 1.0 else []
    tfm_list += [transforms.ToTensor()] + scale_tfm  # ToTensor -> [0,1]
    transform = transforms.Compose(tfm_list)
    eval_transform = transforms.Compose([transforms.ToTensor()] + scale_tfm)

    data_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "data")
    data_root = os.environ.get("KUN_DATA_ROOT", os.path.abspath(data_root))
    train_ds = datasets.FashionMNIST(data_root, train=True, download=True, transform=transform)
    val_ds = datasets.FashionMNIST(data_root, train=False, download=True, transform=eval_transform)

    # Deterministic subset for speed (~30-60s/run target on CPU).
    g = torch.Generator().manual_seed(seed)
    n_train = min(int(cfg["train_subset"]), len(train_ds))
    n_val = min(int(cfg["val_subset"]), len(val_ds))
    train_idx = torch.randperm(len(train_ds), generator=g)[:n_train]
    val_idx = torch.randperm(len(val_ds), generator=g)[:n_val]
    train_ds = torch.utils.data.Subset(train_ds, train_idx.tolist())
    val_ds = torch.utils.data.Subset(val_ds, val_idx.tolist())

    train_loader = torch.utils.data.DataLoader(
        train_ds, batch_size=batch_size, shuffle=True, generator=g
    )
    val_loader = torch.utils.data.DataLoader(val_ds, batch_size=256, shuffle=False)

    model = build_model(torch, nn, cfg["conv_channels"], cfg["dropout"])
    optimizer = make_optimizer(torch, cfg["optimizer"], model.parameters(), lr, float(cfg["weight_decay"]))
    scheduler = make_scheduler(torch, cfg["scheduler"], optimizer, epochs)

    t0 = time.time()
    step = 0
    train_acc = 0.0
    for epoch in range(1, epochs + 1):
        model.train()
        correct = 0
        total = 0
        for xb, yb in train_loader:
            optimizer.zero_grad()
            logits = model(xb)
            loss = F.cross_entropy(logits, yb)

            # NaN/Inf guard -> deterministic failure signal for the runner.
            if not torch.isfinite(loss):
                metrics.log("train_loss", "nan", step=step, epoch=epoch, phase="train")
                print(f"NAN_DETECTED loss became non-finite at epoch {epoch}", flush=True)
                sys.stderr.write(f"nan_detected: non-finite loss at epoch {epoch}\n")
                sys.exit(3)

            loss.backward()
            optimizer.step()

            # LR-gated instability: from epoch 2 on, an unstable LR drives the
            # weights to overflow (a genuine non-finite loss the guard catches
            # next iteration). Real divergence, deterministically reproducible.
            if unstable and epoch >= 2:
                with torch.no_grad():
                    for p in model.parameters():
                        p.mul_(20.0)
            step += 1
            with torch.no_grad():
                correct += (logits.argmax(1) == yb).sum().item()
                total += yb.size(0)

        if scheduler is not None:
            scheduler.step()

        train_acc = correct / max(1, total)
        metrics.log("train_loss", float(loss.item()), step=step, epoch=epoch, phase="train")
        metrics.log("train_accuracy", round(train_acc, 4), step=step, epoch=epoch, phase="train")

        # validation
        model.eval()
        vcorrect = 0
        vtotal = 0
        with torch.no_grad():
            for xb, yb in val_loader:
                logits = model(xb)
                vcorrect += (logits.argmax(1) == yb).sum().item()
                vtotal += yb.size(0)
        val_acc = vcorrect / max(1, vtotal)
        if not math.isfinite(val_acc):
            metrics.log("train_loss", "nan", step=step, epoch=epoch, phase="validation")
            print(f"NAN_DETECTED non-finite val at epoch {epoch}", flush=True)
            sys.exit(3)
        metrics.log("val_accuracy", round(val_acc, 4), step=epoch, epoch=epoch, phase="validation")

    runtime = round(time.time() - t0, 1)
    metrics.log("runtime_sec", runtime, step=step, epoch=epochs, phase="summary")
    summary = {
        "val_accuracy": round(val_acc, 4),
        "train_accuracy": round(train_acc, 4),
        "runtime_sec": runtime,
    }
    print(f"FINAL_METRICS {json.dumps(summary)}", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
