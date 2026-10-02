# Dashi: team plan (source of truth)

Both VMs follow this file. If something here needs to change, agree it out loud first,
then edit this file in its own commit. `BUILD_BRIEF.md` is the spec; this file decides
scope, ownership and timing where the brief offers more than we have time for.

Dashi was called "DriverSide" in early drafts. Same project.

## Time (UTC)

- Submission deadline about **11:20 PM**. **Code freeze 11:05 PM** (15 min before).
  Last 15 min: clean redeploy, one demo run-through, `SUBMISSION.md`. No new features.
- Updated 9:25 PM. Done so far: the app is live at `/app` on sample data, restyled with
  the wireframe design. **Not started: discovery and the review pipeline** (the real
  `moments.json`). That is now the critical path.

| Time | Vaishnav (VM 2, with Cursor) | Teammate 1 (was wireframes) | Teammate 2 (was finding videos) |
|------|------------------------------|-----------------------------|---------------------------------|
| 9:25-10:00 | Discovery (brief section 3): scenario searches, pick 4 trips, re-ingest yes/no | 3-minute demo script against the live app (runbook script as the base) | In the VSS UI, filter `camera_id` = `pie_cam-3`, search each playbook scenario, send chunk filenames with clear examples to Vaishnav |
| 10:00-10:40 | `core.py` + `analyze.py`, real `moments.json`, redeploy | Watch each moment the pipeline finds: agree or disagree | Label 10-12 clips for the eval (`eval/labels.json`) |
| 10:40-11:05 | Eval run, rider "let your rider know" loop if time, fixes | README (brief section 12) | Record a backup screen capture of the demo |
| 11:05-11:20 | Freeze: clean redeploy, demo run-through | `SUBMISSION.md` | Demo |

**Not doing:** post-training a model (no training path on the shared endpoints, internet
video is against event rules, and no judging criterion rewards it; mention it as a next
step in the pitch). The wireframe's "Harsh braking" / "Speeding" flags (no telemetry;
the brief forbids those claims) and its SF / Marcus content (footage is Toronto).

## Scope

**In:** discovery; pipeline stages 1-5; `moments.json` for 4 trips; app with Coach, Trips,
Learn from the cache; the 4 chips with the 8 s templated fallback; evidence packet
(simulated send); deploy at `/app`; Weave eval on 10-12 hand-labelled clips; README.

**Out:** `/ds/analyze` live review, free-text Ask with tool selection, Cosmos Reason
verification (`verified_by_vlm` stays `null`), voice, before/after comparison view.
Free text in the Ask box falls back to "here is what I can help with" plus the chips.

**Re-ingest:** at most one chunk, only Vaishnav (VM 2), only if discovery shows captions don't
say what the camera vehicle does. Save `captions_before.json` first.

## Who owns which file

Only edit files you own. Need a change in someone else's file? Ask them.

| Owner | Files |
|-------|-------|
| Vaishnav (VM 2) | Everything under `app/` and `deploy/`, plus `discovery.md`, `captions_before.json`, `playbook.json`, `eval/*.py`, `eval/results.md` |
| Teammate 1 | `README.md`, `SUBMISSION.md`, `DEMO.md` (demo script) |
| Teammate 2 | `eval/labels.json` |
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
- **`playbook.json`**: `id`, `title`, `lesson`, `enabled` are read by the app. Discovery
  only flips `enabled` and may tune `look_for` / `*_when` text.

## Facts already checked (VM 2, 8:45 PM)

- VSS login, `/videos/explore` and `/tools/segments` work through `app/clients.py`.
  Explore has 414 chunks in total; **180 are `pie_cam-3`** (Toronto, `capture_type`
  `streets`, `location` `toronto`), named like `20261001_071147_set06_video_chunk_0003.mp4`.
- **Each dashcam chunk is about 30 s: 6 segments of 5 s.** The brief assumes about
  5 min per trip. Discovery decides: one chunk per trip, or a few consecutive chunks of
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

## Deployed (VM 2, 9:10 PM)

- **Live at http://video-lab-team-7.cosmos.vastdata.com/app/** with the sample data.
  Health, Coach, Trips, Learn, the 4 chips (LLM from inside the pod), evidence packet and
  clip playback are all verified on the public URL.
- `deploy/deploy.sh` does the full apply; `deploy/deploy.sh code` only refreshes the
  ConfigMap and restarts. The first ~15 s after a restart return errors while pip runs.
- The pod cannot resolve the public host, so its `VSS_URL` is the in-cluster
  `http://video-backend-service.team-7.svc.cluster.local:8000`. Browsers still play clips
  via the public `/api/v1/videos/stream`.
- Ask model: `deepseek-ai/DeepSeek-V4-Flash` (best wording of the three tried, about 1 s).
  Llama 3.3 70B invented rider ratings; `ask.py` now rejects any answer whose star
  rating is not in the data, and falls back to the template.
- **Handoff:** when the pipeline writes `app/moments.json` (plus `app/trips.json` and
  `app/playbook.json`), the app switches from the sample to it automatically. VM 2 then
  pulls and runs `deploy/deploy.sh code`. Keep the brief's schema and `trip_id`,
  `moment_id` formats; `story_role` on trips is optional.
- Run locally on a VM: `cd app && DASHI_LOCAL=1 PORT=8090 ../.venv/bin/python main.py`.

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
- Deployment and re-ingest happen from VM 2 only.

## Getting the code on the other VM

Repo: `vaishnav-ajai/dashi` on Cursor (private; ask Vaishnav for access first).

```sh
curl -fsSL https://downloads.cursor.com/origin/install.sh | sh
~/.local/bin/origin auth login        # your own Cursor account
cd ~/vast-builders-challenge
~/.local/bin/origin repo clone vaishnav-ajai/dashi dashi
echo 'dashi/' >> .git/info/exclude
mkdir -p .cursor/rules && cp dashi/cursor-rules/dashi.mdc .cursor/rules/ && echo '.cursor/rules/dashi.mdc' >> .git/info/exclude
cd dashi && git config user.name "team-7" && git config user.email "team-7@dashi.local"
```

Then start Cursor in `~/vast-builders-challenge` (so the VAST skills load) and give it:
"Read dashi/PLAN.md and dashi/BUILD_BRIEF.md in full. I am <Teammate 1 or 2>. Only touch
the files PLAN.md says I own."
