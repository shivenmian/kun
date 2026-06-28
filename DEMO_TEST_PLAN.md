# Kun — Final Manual Test Plan (P1 demo validation)

Hero = **A + B**:  **A** autonomous research is real (observe a real run) · **B** you steer it to the
edge and it learns (the money shot). The closed loop is **steered** (honest framing: "I push it →
it fails for real → it learns → it obeys"). nanogpt is **synthetic** until your Asset-B run lands.

Execute top to bottom. Annotations: ✅ expect · 👀 watch for · 🎥 record for the demo.

---

## 0. Setup (two terminals)

**Terminal A — backend:**
```bash
cd /Users/shivenmian/kun/backend && source .venv/bin/activate
uvicorn app.main:app --port 8000
```
**Terminal B — web:**
```bash
cd /Users/shivenmian/kun/web && npm run dev      # note the URL, usually http://localhost:5173
```
Web proxies `/api` → `:8000`; the `curl`s below hit `:8000` directly.

**Helper (used throughout):** `?replay` loads only the bundled sample. To view ANY other replay,
register it then open `?observe`:
```bash
curl -s -X POST localhost:8000/missions/register -H 'Content-Type: application/json' \
  -d "{\"mission_id\":\"NAME\",\"events_path\":\"$(pwd)/PATH/TO/file.events.jsonl\"}"
# then open http://localhost:5173/?observe=NAME
```

---

## 1. Pre-check (optional — already verified green)
```bash
cd /Users/shivenmian/kun/backend && source .venv/bin/activate
for t in test_constraints test_steering test_agent_edit test_memory_writer; do python app/loop/$t.py | tail -1; done
python -m app.api.test_steering | tail -1
cd /Users/shivenmian/kun && python examples/test_external_loop_mode_b.py | tail -1
```
✅ `14, 15, 8, 13`, an "ALL STEERING TESTS PASSED"-type banner, and `6`.

---

## 2. Browser sanity / cold-start (5 min — do FIRST)
1. Open `http://localhost:5173/?replay` (the bundled 8-node sample).
2. Click **every node**; switch **every node-view tab**; open the research-memory panel, event stream, topbar.
✅ Nothing breaks; graph is legible; panels populate.
👀 This catches embarrassing UI breakage before you invest in the feature tests.

---

## 3. ⭐ Beat A — autonomous research is REAL (observe a real autonomous run)
This is the autonomy beat. `probe_v4` is a genuine Opus run (LR sweep → finds optimum → overshoots
at 0.012 → recognizes the collapse → backs off). Register and view it:
```bash
cd /Users/shivenmian/kun && source backend/.venv/bin/activate
curl -s -X POST localhost:8000/missions/register -H 'Content-Type: application/json' \
  -d "{\"mission_id\":\"probe_v4\",\"events_path\":\"$(pwd)/runs/probe_v4/events.jsonl\"}"
# open http://localhost:5173/?observe=probe_v4
```
👀 Read the per-node **hypotheses + rationale** — it should clearly read as the AI doing real
research and self-correcting (no human in the loop). This is your "it researches itself" beat.
🎥 Candidate footage for the video's "autonomous" moment.

---

## 4. ⭐⭐ Compare view (cockpit craft)
1. Open `http://localhost:5173/?replay`.
2. Select any node → node-view tabs → **compare** → pick Node A and Node B.
✅ Side-by-side config diff (differences highlighted) + both metric curves overlaid + a rank card
(which node wins on the objective + signed delta). Empty-state if <2 picked.

---

## 5. ⭐⭐ Two-tier research-memory (hard + soft + confidence growth)
Captured real run with both tiers + a sharpened constraint:
```bash
curl -s -X POST localhost:8000/missions/register -H 'Content-Type: application/json' \
  -d "{\"mission_id\":\"steer_demo\",\"events_path\":\"$(pwd)/examples/replays/live_steering_dod5.events.jsonl\"}"
# open http://localhost:5173/?observe=steer_demo
```
✅ Memory panel shows: **hard** constraints with a bound + reject chip (`learning_rate > 0.025`,
`dropout > 0.68`); the dropout one shows confidence **medium → high** (sharpened by two underfits);
**soft** lessons (no bound, "bias only", e.g. "+0.022 val_accuracy").
> Note: this is real training + real failures, but the failures were **steered** (forced via reject-
> with-replacement). Narrate as steering, not autonomous discovery.

---

## 6. ⭐⭐⭐ Beat B — THE HERO: live steering (the money shot) 🎥 RECORD THIS
Create a mission, turn the approval gate ON, start, then steer from the UI.
```bash
MID=$(curl -s -X POST localhost:8000/missions -H 'Content-Type: application/json' -d '{
  "name":"Live steering demo","goal":"demo",
  "objective":{"metric":"val_accuracy","direction":"maximize","target":0.999},
  "budget":{"max_experiments":8,"max_runtime_per_experiment_sec":120},
  "adapter":"tiny_cnn","editable_files":["config.yaml"],
  "allowed_changes":["learning_rate","dropout","optimizer","scheduler","weight_decay"],
  "constraints":[]}' | python3 -c "import sys,json;print(json.load(sys.stdin)['mission_id'])")
echo "MID=$MID"
curl -s -X POST localhost:8000/missions/$MID/stop -H 'Content-Type: application/json' -d '{"action":"resume","approval_required":true}'
curl -s -X POST localhost:8000/missions/$MID/start -H 'Content-Type: application/json' -d '{"mode":"live","started_by":"user"}'
echo "open: http://localhost:5173/?live=$MID"
```
Open `?live=$MID` (loop holds at the first proposal — gate on). Exercise each control:

**6a. Approval gate (Approve / Edit / Reject):**
- **Approve** a proposal → it runs, graph grows, gate re-arms.
- **Edit & Approve** → tweak the changes JSON → runs your values.
- **Reject with replacement** `{"learning_rate":0.05}` → 🔴 **NaN**.
  👀 **THE MONEY SHOT:** node turns **red** → a learned constraint (`learning_rate > 0.025`) appears
  + highlights in the memory panel.
- **Reject** another with `{"dropout":0.9}` → underfit → a second learned constraint.

**6b. Constraint reshape (the closed loop):** now **Approve the next planner proposal as-is**.
👀 Its `changes` respect both bounds (no lr>0.025, no high dropout) — the constraint **deterministically
reshaped** it. This (red node → constraint → reshaped proposal) is the centerpiece of the 1-min video.

**6c. Mid-run instruct:** type guidance + optional bound (e.g. ban `learning_rate > 0.003`).
✅ Biases the next proposal; the bound also hard-rejects violations.

**6d. Stop / Pause / Resume:** Pause → loop blocks (topbar "paused"); Resume → continues; Stop →
`mission_finished` (reason `user_stop`).

**6e. Fork-execute** (on a running, non-paused mission): select a valid node → Fork dialog → add an
instruction + optional constraint → **Fork & run**. ✅ New branch appears and the loop runs a real
experiment on it.

🎥 **Record 6a→6b end-to-end** (reject→NaN→constraint→approve→reshaped). That clip IS the demo.
> If you'd rather not click live, the captured version of exactly this is `steer_demo` (Step 5).

---

## 7. ⭐⭐ agent-edit drove real code (recorded)
```bash
curl -s -X POST localhost:8000/missions/register -H 'Content-Type: application/json' \
  -d "{\"mission_id\":\"agentedit_demo\",\"events_path\":\"$(pwd)/examples/replays/agent_edit_real.events.jsonl\"}"
# open http://localhost:5173/?observe=agentedit_demo
```
✅ 4 nodes; `file_diff_created` diffs are **real code edits** (e.g. `return x` → `return np.tanh(x)`);
accuracy climbs 0.43→0.97. Read `examples/replays/agent_edit_real.README.md` for honest framing.
> Honest narration: this proves the **agent-edit mechanism** (real edits, real metrics) on a small
> numpy MLP. The "what to try" was scripted; it is NOT autonomous research and NOT a serious model
> (that's nanogpt). Don't overclaim.

---

## 8. ⭐⭐ Mode-B wedge with teeth (Kun steers a loop it never ran)
```bash
# Terminal: start the external (not-Kun) loop
cd /Users/shivenmian/kun && source backend/.venv/bin/activate
KUN_MODE_B_MISSION=mode_b_demo KUN_MODE_B_ITERS=8 KUN_MODE_B_SLEEP=2 python examples/external_loop_mode_b.py
# Another terminal, after a couple iterations: inject a bound
curl -s -X POST localhost:8000/missions/mode_b_demo/instruct -H 'Content-Type: application/json' \
  -d '{"text":"keep lr small","bound":{"param":"learning_rate","op":">","value":0.003}}'
# open http://localhost:5173/?observe=mode_b_demo
```
✅ The external loop's console prints `obeyed … clamped learning_rate …` on the next iteration and its
proposed `learning_rate` drops to 0.0015 — Kun steered a loop it doesn't run.
🎥 Strong wedge clip ("15 lines of someone else's loop, steered live by Kun").

---

## 9. ⭐ nanogpt (serious-trajectory SHAPE — synthetic stand-in)
```bash
curl -s -X POST localhost:8000/missions/register -H 'Content-Type: application/json' \
  -d "{\"mission_id\":\"nanogpt_demo\",\"events_path\":\"$(pwd)/examples/replays/nanogpt.events.jsonl\"}"
# open http://localhost:5173/?observe=nanogpt_demo
```
✅ 7-node rich trajectory (AdamW→Muon win, a NaN with a learned bound, best/fork node).
> Honest: **synthetic** until your 8×H100 Asset-B run replaces it (`nanogpt.README.md` says so).
> Narrate as "this is the shape; the real overnight run drops in here."

---

## 10. (Optional) Gated LLM memory-writer
```bash
cd /Users/shivenmian/kun/backend && source .venv/bin/activate
KUN_MEMORY_WRITER=1 python -c "
from app.loop.run_mission import run_mission
run_mission(mission_id='mw_demo', mission={'name':'mw','adapter':'tiny_cnn',
 'allowed_changes':['learning_rate','dropout','scheduler'],
 'objective':{'metric':'val_accuracy','direction':'maximize'},'budget':{'max_experiments':3}})"
```
✅ Near the end, extra soft `constraint_learned` (no bound) distilled by the LLM. Unset flag → none.

---

## 11. Demo-readiness passes (do once the above looks good)
- **Determinism:** re-run the Step 6 hero once more; confirm the NaN+constraint behave the same
  (the failure is forced, so it should). If anything is flaky, prefer demoing from the recording.
- **Backup recordings:** screen-record each reel item below so a live flake never sinks the demo.

---

## The demo reel (what to record, in priority order)
1. ⭐⭐⭐ **Beat B — steer it live** (Step 6, 6a→6b): reject → 🔴 NaN → constraint minted → next
   proposal deterministically reshaped to respect it; then pause/stop; fork-and-run. *The money shot.*
2. ⭐⭐⭐ **Beat A — autonomous research** (Step 3, `probe_v4`): real autonomous exploration + self-correction.
3. ⭐⭐ **Two-tier memory** (Step 5): hard bounds + soft lessons + confidence sharpening.
4. ⭐⭐ **Compare view** (Step 4): overlay two curves + rank.
5. ⭐⭐ **Mode-B wedge** (Step 8): Kun steers an external loop it never ran.
6. ⭐⭐ **agent-edit real code** (Step 7): real diffs editing real code.
7. ⭐ **nanogpt** (Step 9): serious-trajectory shape — swap in the real Asset-B run when ready.
