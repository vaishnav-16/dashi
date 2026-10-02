# Dashi: progress log

State as of **9:35 PM UTC, Fri Oct 2**. Submission deadline about **11:20 PM**, code freeze
**11:05 PM**. Owner of the remaining build work: Vaishnav on VM 2 (this VM), with Cursor.
Plan and ownership: `PLAN.md`. Spec: `BUILD_BRIEF.md`.

## Done and verified

| Area | What exists | Verified how |
|------|-------------|--------------|
| Repo | `vaishnav-ajai/dashi` on Cursor (private), cloned at `~/vast-builders-challenge/dashi/`, ignored by the outer challenge repo. 6 commits, local equals remote. | `git status`, `git log origin/main` |
| Shared plan | `PLAN.md` (timeline, scope, file ownership, contracts, names, git rules, clone steps); brief renamed DriverSide to Dashi incl. "How this will be judged"; Cursor rule `cursor-rules/dashi.mdc` installed on VM 2 | Read back |
| Tooling on VM 2 | `kubectl` v1.37 in `~/.local/bin`, kubeconfig `/config/team-7-k8s.yaml`; Python venv `dashi/.venv` (fastapi, uvicorn, requests, openai; **weave not installed yet**); origin CLI logged in | Commands run |
| `app/clients.py` | `VSS` client (login, JWT cache, re-login on 401, `get`, `post`, `stream_path`), `llm()` W&B client, `MODEL` default `deepseek-ai/DeepSeek-V4-Flash`, `setting()` reads pod env, then `/config/*.config`, then VM env | Live calls: login, explore, segments, model list |
| `app/moments.sample.json` | 4 trips (T-1041 underrated, T-1042 missed_risk, T-1043 clean, T-1044 mixed), 5 moments, **real** `pie_cam-3` clip URIs and captions, hand-made verdicts, `"sample": true` | Clips play in browser |
| `app/ask.py` | Task tools (`get_trips`, `get_trip_moments`, `get_lesson`, `find_in_my_footage`), 4 chip intents + keyword router, help text for off-topic, one LLM call to phrase, 8 s budget, templated fallback, guards that reject invented star ratings and evidence offers that do not exist | All 4 chips + off-topic tested; answers 1-2 s |
| `app/main.py` | FastAPI: `/health`, `/`, `/ds/home`, `/ds/trips`, `/ds/trips/{id}`, `/ds/moments/{id}`, `/ds/clip`, `/ds/lessons`, `POST /ds/lessons/{id}/done`, `POST /ds/ask`, `POST /ds/trips/{id}/evidence` (packet + simulated send with reference). Serves `moments.json` if present, else the sample. `DASHI_LOCAL=1` for VM runs | curl of every route, locally and deployed |
| `app/index.html` | Phone column, wireframe styling (Inter, black pills, purple ✦ AI accent, green/amber ringed video panels, timestamp pills). Coach (stats, proactive cards, chips, chat-style Ask), Trips (list, badges, detail with timeline, moment cards, 5 s before/after, two columns, evidence packet modal), Learn (lessons with own clip, Mark as learned, counters). Simulated labels, sample banner, clip-failure caption fallback, empty states | Browser screenshots; clips load (readyState 4) on the public URL |
| Deployment | `deploy/deploy.sh` (full) and `deploy/deploy.sh code` (ConfigMap + restart). Live at **http://video-lab-team-7.cosmos.vastdata.com/app/** (reachable only inside the event network / VM browsers). Pod uses in-cluster `VSS_URL` `http://video-backend-service.team-7.svc.cluster.local:8000`; W&B reachable from the pod | `/app/health`, chip answers from pod, clip stream HTTP 206 |

## Facts learned about the data

- 414 indexed chunks; **180 are `pie_cam-3`** (Toronto, `streets`), files like
  `20261001_071147_set06_video_chunk_0003.mp4` from drive sets `set01`..`set06`.
- **Each chunk is about 30 s = 6 segments of 5 s.** Trip length decision still open.
- Segment fields (all strings): `source`, `reasoning_content`, `segment_start_sec`,
  `segment_end_sec`, `segment_number`, `total_segments`, `object_classes`,
  `object_counts` (JSON string), `original_video`, `camera_id`.
- Captions are long scene descriptions and sometimes mention the ego vehicle. YOLO is
  noisy (cows, kites, sheep) and person counts are low.
- Llama 3.3 70B invented ratings; DeepSeek V4 Flash does not and is about 1 s.

## Not started (critical path)

1. **Discovery** (brief section 3): scenario searches on `pie_cam-3`, `discovery.md`,
   prune `playbook.json`, choose 4 trips, `captions_before.json`, re-ingest decision.
2. **Review pipeline** `app/core.py` + `app/analyze.py` (brief section 5, stages 1-5),
   real `app/moments.json` + `app/trips.json`, story roles, redeploy.
3. **Eval** (brief section 9): `eval/make_sheet.py`, `eval/labels.json` (Teammate 2),
   `eval/run_eval.py` with Weave, `eval/results.md`.
4. **README** (brief section 12) and `SUBMISSION.md` (Teammate 1, needs real numbers).
5. Optional: wireframe's "Let your rider know" rider view loop.

## Teammates (not on this VM)

- Teammate 1: was making wireframes; now demo script, then clip review, README, submission.
- Teammate 2: searching our archive in the VSS UI for scenario chunks (filenames to
  Vaishnav), then eval labels, backup recording.
- Neither has pushed anything yet.
