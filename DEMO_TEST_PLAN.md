# Kun — Final Manual Test / Demo-Rehearsal Plan (UI-first)

Hero = **A + B**:  **A** autonomous research is real (observe a real run) · **B** you steer it to the
edge and it learns (the money shot). The closed loop is **steered** (honest framing: "I push it →
it fails for real → it learns → it obeys"). nanogpt is **synthetic** until your Asset-B run lands.

**Everything below is done in the browser** (the cockpit now has full mission control). The old
curl commands are kept as a scriptable fallback in the **Appendix** — same endpoints, for
automation/headless. Button labels are approximate; match what's on screen.

Annotations: ✅ expect · 👀 watch for · 🎥 record for the demo.

---

## 0. Setup (two terminals)
```bash
# Terminal A — backend
cd /Users/shivenmian/kun/backend && source .venv/bin/activate && uvicorn app.main:app --port 8000
# Terminal B — web
cd /Users/shivenmian/kun/web && npm run dev        # open the printed URL, usually http://localhost:5173
```

## 1. Pre-check (optional — already verified green)
```bash
cd /Users/shivenmian/kun/backend && source .venv/bin/activate
for t in test_constraints test_steering test_agent_edit test_memory_writer; do python app/loop/$t.py | tail -1; done
python -m app.api.test_missions_list | tail -1 && python -m app.api.test_steering | tail -1
cd /Users/shivenmian/kun && python examples/test_external_loop_mode_b.py | tail -1
```
✅ `14, 15, 8, 13`, missions-list PASS, steering banner, `6`.

---

## 2. Browser sanity / cold-start (do FIRST, ~5 min)
Open the app. Click around the **persistent shell**: the mission navigator rail, topbar instruments,
the **Replay** and **+ New mission** / **Observe** buttons. Load the **Fashion-MNIST sample** from the
Replay gallery, click every node, switch every node-view tab, open the research-memory panel + event
stream. ✅ Nothing breaks; panels populate; graph legible.

---

## 3. ⭐ Beat A — autonomous research is REAL (one click)
**Replay gallery → "Autonomous research (real)".**
👀 Read the per-node hypotheses/rationale: a genuine Opus run doing an LR range test — finds the
optimum (~0.01, 0.853), overshoots at 0.012, **recognizes the collapse, backs off**. Real autonomous
exploration + self-correction, no human in the loop.
🎥 Footage for the "it researches itself" beat. (Honesty: real autonomous run; no NaN — see README.)

## 4. ⭐⭐ Compare view (cockpit craft)
Load the **sample** (Replay gallery) → select a node → node-view tabs → **compare** → pick Node A/B.
✅ Side-by-side config diff (differences highlighted) + both metric curves overlaid + a rank card
(winner on the objective + signed delta). Empty-state if <2 picked.

## 5. ⭐⭐ Two-tier research-memory (hard + soft + confidence growth)
**Replay gallery → "Live steering (DoD #5)".**
✅ Memory panel: **hard** constraints with bound + reject chip (`learning_rate > 0.025`,
`dropout > 0.68`); the dropout one shows confidence **medium → high** (sharpened); **soft** lessons
(no bound, "bias only"). 👀 Real training + real failures, but **steered** — narrate as steering.

---

## 6. ⭐⭐⭐ Beat B — THE HERO: live steering, all-UI (the money shot) 🎥 RECORD
Create + run + steer entirely in the cockpit:

1. **+ New mission** → fill the modal:
   - name/goal anything; objective `val_accuracy` / maximize / target `0.999`
   - budget: max_experiments `8`, runtime/exp `120`
   - adapter `tiny_cnn`, patcher `config-patch`
   - allowed changes: `learning_rate, dropout, optimizer, scheduler, weight_decay`
   - ✅ **check "approval gate ON"**
2. Click **Create & start**. The mission opens live and **holds at the first proposal** (gate on).
3. **Steer via the Control Deck / approval banner:**
   - **Reject with replacement** `{"learning_rate": 0.05}` → 🔴 **NaN**.
     👀 **MONEY SHOT:** node turns **red** → constraint (`learning_rate > 0.025`) appears + highlights
     in the memory panel.
   - **Reject** another with `{"dropout": 0.9}` → underfit → a second learned constraint.
   - **6b — the closed loop:** now **Approve the next planner proposal as-is**.
     👀 Its `changes` respect both bounds (no lr>0.025, no high dropout) — **deterministically
     reshaped**. (red node → constraint → reshaped proposal = the 1-min-video centerpiece.)
   - **Edit & Approve** on some proposal → runs your edited values.
4. **Mid-run Instruct** (Control Deck) → guidance + optional bound (e.g. ban `learning_rate > 0.003`)
   → biases next proposal; bound hard-rejects violations.
5. **Topbar approval toggle** → flip the gate off/on live.
6. **Stop / Pause / Resume** (Control Deck) → topbar reflects state; Stop → `mission_finished`.
7. **Fork-execute** → select a valid node → Fork dialog → instruction + optional constraint → Fork &
   run → ✅ new branch, real experiment runs on it.

🎥 **Record steps 3 end-to-end** (reject→red NaN→constraint→approve→reshaped). That clip IS the demo.
> Don't want to click live? The captured version is **"Live steering (DoD #5)"** in the gallery (Step 5).

## 6b. Regression check — the pause+toggle fix
Pause a live mission, then flip the **approval toggle**. ✅ The mission **stays paused** (arming the
gate must not un-pause — this was the recent fix). Quick but important.

---

## 7. ⭐⭐ agent-edit drove real code (one click)
**Replay gallery → "Agent-edit (real)".** ✅ 4 nodes; `file_diff_created` diffs are **real code edits**
(`return x` → `return np.tanh(x)`); accuracy 0.43→0.97. 👀 Honest framing: proves the agent-edit
**mechanism** on a numpy MLP; the decisions were scripted, it's not autonomous research or a serious
model (that's nanogpt). See `agent_edit_real.README.md`.

## 8. ⭐⭐ Mode-B wedge with teeth (Kun steers a loop it never ran)
The external producer is a CLI script (that's the point — not Kun's loop):
```bash
cd /Users/shivenmian/kun && source backend/.venv/bin/activate
KUN_MODE_B_MISSION=mode_b_demo KUN_MODE_B_ITERS=8 KUN_MODE_B_SLEEP=2 python examples/external_loop_mode_b.py
```
In the cockpit, open it from the **mission navigator** (it appears live) or **Observe** (mission_id
`mode_b_demo`). Then inject a bound — via the **Instruct** box on that mission, or curl:
```bash
curl -s -X POST localhost:8000/missions/mode_b_demo/instruct -H 'Content-Type: application/json' \
  -d '{"text":"keep lr small","bound":{"param":"learning_rate","op":">","value":0.003}}'
```
✅ The external loop's console prints `obeyed … clamped learning_rate …` and its proposed lr drops to
0.0015 — Kun steered a loop it doesn't run. 🎥 Strong wedge clip.

## 9. ⭐ nanogpt (serious-trajectory SHAPE — synthetic stand-in)
**Replay gallery → "nanoGPT (synthesized)".** ✅ 7-node rich trajectory (AdamW→Muon, a NaN with a
learned bound, best/fork node). 👀 **Synthetic** until your 8×H100 Asset-B run replaces it — narrate
as "this is the shape; the real overnight run drops in here."

## 10. (Optional) Gated LLM memory-writer (headless)
```bash
cd /Users/shivenmian/kun/backend && source .venv/bin/activate
KUN_MEMORY_WRITER=1 python -c "from app.loop.run_mission import run_mission; run_mission(mission_id='mw_demo', mission={'name':'mw','adapter':'tiny_cnn','allowed_changes':['learning_rate','dropout','scheduler'],'objective':{'metric':'val_accuracy','direction':'maximize'},'budget':{'max_experiments':3}})"
```
✅ Extra soft `constraint_learned` (no bound) near the end; unset flag → none.

---

## 11. Demo-readiness passes
- **New-UI surfaces to confirm work** (they're new since the last audit): New-mission modal create+start,
  topbar approval toggle, Control Deck approve/edit/reject/fork/instruct, Replay gallery + Observe modal,
  mission navigator + attention badges/toasts. Step 6 already exercises most of these.
- **Determinism:** re-run the Step 6 hero once; the forced NaN+constraint should behave identically. If
  flaky, demo from the recording.
- **Backup recordings:** screen-record every reel item below.

---

## The demo reel (record in priority order)
1. ⭐⭐⭐ **Beat B — steer it live** (Step 6): reject → 🔴 NaN → constraint → reshaped proposal; pause/stop; fork-and-run. *The money shot.*
2. ⭐⭐⭐ **Beat A — autonomous research** (Step 3): real autonomous exploration + self-correction.
3. ⭐⭐ **Two-tier memory** (Step 5) · ⭐⭐ **Compare** (Step 4) · ⭐⭐ **Mode-B wedge** (Step 8) · ⭐⭐ **agent-edit** (Step 7).
4. ⭐ **nanogpt** (Step 9): serious-trajectory shape — swap in the real Asset-B run when ready.

---

## Appendix — curl fallback (automation / headless; same endpoints)
Old UI-free path, still 100% valid:
```bash
# create + arm gate + start (Step 6)
MID=$(curl -s -X POST localhost:8000/missions -H 'Content-Type: application/json' -d '{
  "name":"Live steering demo","goal":"demo","objective":{"metric":"val_accuracy","direction":"maximize","target":0.999},
  "budget":{"max_experiments":8,"max_runtime_per_experiment_sec":120},"adapter":"tiny_cnn","editable_files":["config.yaml"],
  "allowed_changes":["learning_rate","dropout","optimizer","scheduler","weight_decay"],"constraints":[]}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['mission_id'])")
curl -s -X POST localhost:8000/missions/$MID/stop    -d '{"approval_required":true}'   # action now optional
curl -s -X POST localhost:8000/missions/$MID/start   -d '{"mode":"live","started_by":"user"}'
# observe any replay (Steps 3/5/7/9) — UI gallery does this for you:
curl -s -X POST localhost:8000/missions/register -H 'Content-Type: application/json' \
  -d "{\"mission_id\":\"NAME\",\"events_path\":\"$(pwd)/examples/replays/FILE.events.jsonl\"}"   # then ?observe=NAME
```
