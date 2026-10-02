# Dashi: team plan (source of truth)

Both VMs follow this file. If something here needs to change, agree it out loud first,
then edit this file in its own commit. `BUILD_BRIEF.md` is the spec; this file decides
scope, ownership and timing where the brief offers more than we have time for.

Dashi was called "DriverSide" in early drafts. Same project.

## Time (UTC)

- Deadline about **11:20 PM**. **Code freeze 10:35 PM.** After freeze: clean redeploy,
  rehearse the demo twice, record a backup video, write `SUBMISSION.md`. No new features.

| Time | VM 1: Person 1 (+ Person 3) | VM 2: Person 2 |
|------|-----------------------------|----------------|
| 8:30-8:45 | Clone this repo inside `~/vast-builders-challenge/`, health check | `kubectl` + kubeconfig, `app/clients.py`, `moments.sample.json` |
| 8:45-9:20 | Phase 0 discovery (brief section 3), `captions_before.json`, pick 4 trips, re-ingest yes/no | `main.py` + `index.html` against the sample data |
| 9:20-10:05 | `core.py` + `analyze.py`: one trip, Person 3 checks clips, then all trips, story roles | **First deploy to `/app` by 9:45**, then UI polish |
| 10:05-10:35 | Push real `moments.json` + `trips.json`; eval (10-12 clips) | Pull real data, evidence packet, redeploy |
| 10:35-11:20 | Freeze. Rehearse, backup recording, submission | Same |

## Scope

**In:** discovery; pipeline stages 1-5; `moments.json` for 4 trips; app with Coach, Trips,
Learn from the cache; the 4 chips with the 8 s templated fallback; evidence packet
(simulated send); deploy at `/app`; Weave eval on 10-12 hand-labelled clips; README.

**Out:** `/ds/analyze` live review, free-text Ask with tool selection, Cosmos Reason
verification (`verified_by_vlm` stays `null`), voice, before/after comparison view.
Free text in the Ask box falls back to "here is what I can help with" plus the chips.

**Re-ingest:** at most one chunk, only Person 1, only if discovery shows captions don't
say what the camera vehicle does. Save `captions_before.json` first.

## Who owns which file

Only edit files you own. Need a change in someone else's file? Ask them.

| Owner | Files |
|-------|-------|
| VM 1 (Person 1) | `discovery.md`, `captions_before.json`, `playbook.json` and `app/playbook.json` (keep identical), `app/trips.json`, `app/core.py`, `app/analyze.py`, `app/moments.json`, `eval/make_sheet.py`, `eval/run_eval.py`, `eval/results.md` |
| VM 1 (Person 3) | `eval/labels.json`, `README.md`, `SUBMISSION.md` |
| VM 2 (Person 2) | `app/main.py`, `app/index.html`, `app/requirements.txt`, `app/clients.py`, `app/ask.py`, `app/moments.sample.json`, `deploy/` |
| Agreed together | `PLAN.md`, `BUILD_BRIEF.md`, the `moments.json` schema |

## Contracts between the VMs

- **`moments.json` schema** is exactly the one in brief section 5. Do not add or rename
  fields without telling the other VM. `main.py` serves `app/moments.json` when it
  exists and falls back to `app/moments.sample.json`.
- **`app/clients.py`** (VM 2, pushed by 8:45) is shared by `main.py` and `core.py`:
  - `VSS` class: logs in with `VSS_URL`, `VSS_USERNAME`, `VSS_PASSWORD`, caches the JWT,
    logs in again on a 401. Methods `get(path, **params)`, `post(path, json)`, `token()`.
    Paths are relative to `/api/v1`.
  - `llm()`: W&B OpenAI-compatible client (brief section 5). `MODEL` comes from env
    `DASHI_MODEL`.
  - On the VM, `VSS_URL`, `VSS_USERNAME`, `VSS_PASSWORD` default to `INGRESS_URL`,
    `USERNAME`, `PASSWORD`, so the same code runs on the VM and in the pod.
- **`playbook.json`**: `id`, `title`, `lesson`, `enabled` are read by the app. Person 1
  only flips `enabled` and may tune `look_for` / `*_when` text.

## Facts already checked (VM 2, 8:45 PM)

- VSS login, `/videos/explore` and `/tools/segments` work through `app/clients.py`.
  Explore has 414 chunks in total; **180 are `pie_cam-3`** (Toronto, `capture_type`
  `streets`, `location` `toronto`), named like `20261001_071147_set06_video_chunk_0003.mp4`.
- **Each dashcam chunk is about 30 s: 6 segments of 5 s.** The brief assumes about
  5 min per trip. Person 1 decides: one chunk per trip, or a few consecutive chunks of
  the same `setNN` combined into one trip (`original_video` then becomes a list).
  Tell VM 2 which, since the trip shape in `moments.json` depends on it.
- Real segment fields (all values are **strings**): `source` (clip URI),
  `reasoning_content` (caption), `segment_start_sec`, `segment_end_sec`,
  `segment_number`, `total_segments`, `object_classes` (comma list), `object_counts`
  (JSON string, e.g. `{"car": 13, "person": 1}`), `original_video`, `camera_id`.
- YOLO is noisy on this footage (reports cows, kites, sheep, airplanes) and person
  counts are low. Lean on captions; use counts only as supporting evidence.
- Captions already say "the ego vehicle is traveling in the rightmost lane", so the
  model does describe the camera vehicle sometimes. Check whether they say slows,
  stops or yields before deciding on re-ingest.
- W&B models: 29 available. `meta-llama/Llama-3.3-70B-Instruct`,
  `deepseek-ai/DeepSeek-V4-Flash` and `Qwen/Qwen3-30B-A3B-Instruct-2507` all returned
  clean JSON with `response_format: json_object` in under 1 s. Default in
  `clients.py` is Llama 3.3 70B; set `DASHI_MODEL` to override.
- The VM has no `pip`. Set up Python like this, inside `dashi/`:
  ```sh
  python3 -m venv --without-pip .venv
  curl -fsSL https://bootstrap.pypa.io/get-pip.py | .venv/bin/python
  .venv/bin/python -m pip install fastapi uvicorn requests openai weave
  ```
- `kubectl` is not preinstalled; VM 2 installed it in `~/.local/bin`. Kubeconfig is
  `/config/team-7-k8s.yaml`.

## Names (do not improvise)

| Thing | Value |
|-------|-------|
| Folder | `~/vast-builders-challenge/dashi/` (its own git repo, ignored by the outer repo) |
| Kubernetes app name | `dashi` (ConfigMap `dashi-code`, Secret `dashi-vss-creds`) |
| Namespace | `team-7` |
| App URL | `http://video-lab-team-7.cosmos.vastdata.com/app/` |
| LLM model env var | `DASHI_MODEL` |
| App JSON routes | `/ds/...` (brief section 6) |
| Driver | "Alex", ratings labelled "Simulated" |

## Git rules

- `git pull --rebase` before you start a task and before every push.
- Small commits, push often. Never commit `/config` contents, tokens, passwords or
  `.env` files. List env var names only: `env | cut -d= -f1 | sort`.
- Deployment happens from VM 2 only. Re-ingest happens from VM 1 only.

## Getting the code on the other VM

Repo: `vaishnav-ajai/dashi` on Cursor (private; ask Vaishnav for access first).

```sh
curl -fsSL https://downloads.cursor.com/origin/install.sh | sh
~/.local/bin/origin auth login        # your own Cursor account
cd ~/vast-builders-challenge
~/.local/bin/origin repo clone vaishnav-ajai/dashi dashi
echo 'dashi/' >> .git/info/exclude
cd dashi && git config user.name "team-7" && git config user.email "team-7@dashi.local"
```

Then start Cursor in `~/vast-builders-challenge` (so the VAST skills load) and give it:
"Read dashi/PLAN.md and dashi/BUILD_BRIEF.md in full. I am VM 1, Person 1. Only touch
the files PLAN.md says I own."
