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
