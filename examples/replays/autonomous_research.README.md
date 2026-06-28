# autonomous_research.events.jsonl — Beat A (real autonomous research)

A **verbatim capture** of a real Kun Mode-A run (Opus 4.8 planner, tiny-CNN, config-patch).
No human in the loop, no forcing. The agent autonomously runs a learning-rate range test:
sweeps lr 0.001→0.012, finds the optimum (~0.01, val_accuracy 0.853), recognizes the accuracy
**collapse** at 0.012, and backs off — genuine autonomous exploration + self-correction.

Honesty note: this is real autonomous research, real training, real metrics. It does NOT contain a
NaN/divergence — a strong, well-aligned planner stops at the empirical optimum rather than blowing
itself up (we confirmed this across four framings). The dramatic failure→learn→reshape arc is shown
separately via **steering** (see live_steering_dod5). Narrate this as "the AI does the research
itself"; narrate the steered run as "and you can push it to the edge — it learns the limit."

Source mission_id: probe_v4.
