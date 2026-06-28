"""Tiny, FAST, CPU-only, deterministic real-code target for Kun's agent-edit replay.

A 1-hidden-layer MLP trained with plain-numpy full-batch gradient descent on a
deterministic, nonlinearly-separable synthetic dataset (concentric circles: an
inner disk surrounded by an outer ring).
Its behavior depends entirely on the CODE-LEVEL knobs below -- the activation
function and a few numeric constants written IN THIS FILE (NOT a config file).
It prints a single parseable metric line to stdout:

    METRIC accuracy=0.9333

Runs in well under a second with only numpy. No torch, no GPU, no network.

The coding agent (Kun's agent-edit patcher) edits THIS file to run experiments;
Kun then executes the edited copy and parses the accuracy. The activation's
gradient is computed numerically (central difference), so changing ONLY the
`activation` function body is a complete, self-consistent edit -- no paired
derivative edit is required.
"""
import numpy as np

# ============================ CODE-LEVEL KNOBS ===============================
# These are real source-code constants/functions the agent edits to experiment.
HIDDEN_SIZE = 3          # hidden-layer width
LEARNING_RATE = 0.2      # full-batch gradient-descent step size
EPOCHS = 400             # number of gradient-descent epochs
SEED = 0                 # fixed -> the whole run is deterministic


def activation(x):
    """Hidden-layer nonlinearity (a CODE-LEVEL knob).

    Default is the IDENTITY (linear) map: with a linear hidden layer the network
    collapses to a linear classifier, which cannot separate the nonlinear
    concentric-circles dataset. Swapping this for a real nonlinearity (e.g.
    ``np.tanh(x)``) is the single most impactful edit.
    """
    return x


# ============================ fixed scaffold =================================
def _activation_grad(x, eps=1e-5):
    """Elementwise derivative of ``activation`` via central difference.

    Computed numerically so that editing ONLY the ``activation`` body above stays
    self-consistent (the gradient tracks whatever activation is in use)."""
    return (activation(x + eps) - activation(x - eps)) / (2.0 * eps)


def make_dataset(n_per_class=150, noise=0.30, seed=0):
    """Deterministic concentric-circles dataset (no sklearn): an inner disk (class 0)
    inside an outer ring (class 1).

    This dataset is NOT linearly separable -- no straight decision boundary can
    split an inner disk from a surrounding ring -- so a linear (identity-activation)
    network is stuck near chance, while a nonlinear hidden layer can carve out the
    ring. That makes the ``activation`` knob the dominant lever on accuracy."""
    rng = np.random.RandomState(seed)
    t = np.linspace(0.0, 2.0 * np.pi, n_per_class)
    inner_r, outer_r = 1.0, 2.0
    x0 = np.stack([inner_r * np.cos(t), inner_r * np.sin(t)], axis=1)  # class 0 (inner)
    x1 = np.stack([outer_r * np.cos(t), outer_r * np.sin(t)], axis=1)  # class 1 (outer ring)
    X = np.concatenate([x0, x1], axis=0)
    y = np.concatenate([np.zeros(n_per_class), np.ones(n_per_class)])
    X = X + rng.normal(scale=noise, size=X.shape)
    # Deterministic shuffle + standardize.
    perm = rng.permutation(len(X))
    X, y = X[perm], y[perm]
    X = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-9)
    return X, y.reshape(-1, 1)


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -50, 50)))


def main():
    np.random.seed(SEED)
    X, y = make_dataset(seed=SEED)
    # Deterministic 70/30 train/test split.
    n_train = int(0.7 * len(X))
    Xtr, ytr = X[:n_train], y[:n_train]
    Xte, yte = X[n_train:], y[n_train:]

    # Init weights (deterministic).
    d_in = X.shape[1]
    W1 = np.random.randn(d_in, HIDDEN_SIZE) * 0.5
    b1 = np.zeros((1, HIDDEN_SIZE))
    W2 = np.random.randn(HIDDEN_SIZE, 1) * 0.5
    b2 = np.zeros((1, 1))

    n = len(Xtr)
    for _ in range(EPOCHS):
        # Forward.
        z1 = Xtr @ W1 + b1
        a1 = activation(z1)
        z2 = a1 @ W2 + b2
        p = _sigmoid(z2)
        # Backward (BCE + sigmoid).
        dz2 = (p - ytr) / n
        dW2 = a1.T @ dz2
        db2 = dz2.sum(axis=0, keepdims=True)
        da1 = dz2 @ W2.T
        dz1 = da1 * _activation_grad(z1)
        dW1 = Xtr.T @ dz1
        db1 = dz1.sum(axis=0, keepdims=True)
        # Update.
        W1 -= LEARNING_RATE * dW1
        b1 -= LEARNING_RATE * db1
        W2 -= LEARNING_RATE * dW2
        b2 -= LEARNING_RATE * db2

    # Evaluate test accuracy.
    a1 = activation(Xte @ W1 + b1)
    pte = _sigmoid(a1 @ W2 + b2)
    acc = float(((pte > 0.5).astype(float) == yte).mean())
    if not np.isfinite(acc):
        print("METRIC accuracy=nan")
    else:
        print(f"METRIC accuracy={acc:.4f}")


if __name__ == "__main__":
    main()
