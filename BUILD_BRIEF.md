# Dashi: build brief

This file is the specification for the coding agent. Read all of it before writing code.
Companion files in this folder: `playbook.json`, `trips.seed.json`, `reingest_prompt.txt`.
`RUNBOOK.md` is for the humans on the team (order of work, demo script).

## 1. What we are building

**Dashi is a video agent on the rideshare driver's side.** After each trip it reviews
the driver's dashcam footage, finds the moments that matter, and does three things:

1. **Shows what happened**, with the clip and timestamp as evidence.
2. **Coaches**: says how that moment could have been safer, from a fixed playbook.
3. **Gives credit**: when the driver handled a hazard well, it says so, and when a low
   rider rating does not match what the video shows, it offers to send the evidence.

Why it matters: a rider rates from the back seat and cannot see why the driver braked.
Sensor-based telematics knows the car stopped, not that a pedestrian stepped out. Video
shows the cause, so the driver's record can reflect how they drove.

Two ways in, matching the team's sketch:

- **Ask**: the driver says "Help me improve my reviews". The agent finds the trip, the
  timestamp and the scenario, then shows "what happened" next to "how it could be safer".
- **Proactive education**: after a trip is reviewed, the agent posts short lesson cards
  built from the driver's own clips, without being asked.

Design principles (taken from the Uber Driver Assistant talk):

- Every answer connects **context** (which trip, which rating), **evidence** (the clip),
  and **choice** (what the driver can do next). The driver stays in charge.
- Tools are designed around tasks, not raw APIs. The model never reconciles raw endpoints.
- Quality is measured with an eval, not assumed.

## 2. Hard constraints

- Use the skills in `.cursor/skills/` before writing raw REST calls. Never print, log or
  commit secrets. List env var names only (`env | cut -d= -f1 | sort`).
- The deliverable is a **web app on Kubernetes** at
  `http://video-lab-team-<N>.cosmos.vastdata.com/app`, deployed with the
  `deployment/deploy-app-no-registry` skill: `python:3.12-slim`, code from a ConfigMap,
  no Docker build. Running locally on the VM is for testing only.
- Do not redeploy or edit the DataEngine pipeline. Do not ingest video from the internet.
  Stay in this team's namespace, buckets and credentials.
- Only one or two people start re-ingests. Re-ingest one chunk first and read the captions
  before doing more.
- **There is no telemetry.** No speed, braking force or GPS. Every judgment comes from
  what the camera shows (captions and detections). Never claim speeding or hard braking.
- **There are no rider ratings in the environment.** Ratings and comments are synthetic
  (`trips.seed.json`). The UI and README must label them "simulated".
- The footage is a Toronto dashcam research set (`camera_id` `pie_cam-3`) standing in for
  a rideshare driver's trips. Say so in the README.

## 3. Phase 0: discovery (do this before any app code)

The scenario list must come from what the footage contains. Steps:

1. Log in (`retrieval/login`). Read `/metadata/schema` and confirm the exact `camera_id`
   value for the dashcam footage (expected `pie_cam-3`).
2. `GET /videos/explore?scope=all` (page through `total`). List the dashcam parent chunks:
   `original_video`, filename, clip count, duration. Print a table.
3. Fetch one chunk's segments (`GET /tools/segments?original_video=`) and print the
   **field names** of one segment plus one full caption (`reasoning_content`). Record the
   real field names for: clip URI, caption, start and end time, segment order, object
   classes and counts. The rest of this brief uses assumed names. Adapt to the real ones.
4. For every scenario in `playbook.json`, run its `search_queries` through `POST /search`
   with `metadata_filters: {"camera_id": "<dashcam id>"}`, `top_k: 10`,
   `min_similarity: 0.3`, `llm_top_n: 0`. Record hits per scenario with scores and captions.
5. Write `discovery.md`: per scenario, number of convincing hits and two example captions.
   Mark scenarios with fewer than 3 convincing hits as `"enabled": false` in
   `playbook.json`. Keep the best 3 to 5.
6. If no rideshare-style scenario (curb, stopping in lane) survives on the dashcam, run
   the same queries without the camera filter and report which cameras do show them. The
   team decides whether to use those clips as lesson examples.
7. **Before any re-ingest**, dump `/tools/segments` for every chosen chunk to
   `dashi/captions_before.json`. Re-ingest replaces the rows, so the old captions
   are gone afterwards, and the before/after comparison and the eval need them.
8. Decide on re-ingest. If captions rarely say what the **camera vehicle** does (slows,
   stops, yields, pulls over), re-ingest with `reingest_prompt.txt` (737 characters, the
   limit is 800). One chunk first with `ingest/reingest-chunk`, compare captions before
   and after, then up to 4 more chunks. Keep a copy of two before/after caption pairs for
   the README and the demo.

Output of this phase: enabled scenarios, 4 or 5 chosen chunks (the "trips"), real field
names, and a yes/no on re-ingest. Ask the team to confirm before Phase 1.

## 4. Architecture

```
 Dashcam video (S3)                         PRE-BUILT, already running
   -> YOLO11 detections
   -> Cosmos Reason captions  <- our custom ingest prompt (reingest_prompt.txt)
   -> Cosmos Embed vectors
   -> VastDB  <-  VSS backend API ($INGRESS_URL/api/v1)
                        |
                        v
 Dashi (what we build)
   core.py     VSS client + LLM client + the review pipeline
   analyze.py  CLI: review trips, write moments.json
   main.py     FastAPI app: serves the UI and the JSON API
   index.html  single-page UI, no build step
   LLM         W&B serverless inference (OpenAI-compatible)
   Tracing     W&B Weave on the review pipeline + the eval
```

Sponsor tools used, each doing real work: **VAST** (DataEngine pipeline, VastDB hybrid
search, S3 clips), **NVIDIA** (Cosmos Reason captions through our prompt, Cosmos Embed
search, YOLO person counts), **CoreWeave / Weights & Biases** (inference for the agent,
Weave traces and evaluation), **Cursor** (how it was built).

### Folder layout

```
dashi/
  README.md            inputs, outputs, how to run, evaluation, limitations
  BUILD_BRIEF.md  RUNBOOK.md  discovery.md
  app/                 FLAT. This whole folder becomes the ConfigMap.
    main.py  core.py  analyze.py  index.html
    playbook.json  trips.json  moments.json  requirements.txt
  eval/
    labels.json  run_eval.py  results.md
```

`kubectl create configmap --from-file=<dir>` does **not** recurse, so `app/` must stay
flat. Total size under 1 MiB.

## 5. The review pipeline (`core.py`, run by `analyze.py`)

One trip is one parent chunk (`original_video`). Its segments, in order, are the trip
timeline. For each trip:

**Stage 1, gather.** `GET /tools/segments?original_video=`. For each segment keep: clip
URI, caption, start and end seconds, order, and YOLO person and vehicle counts.

**Stage 2, classify (W&B LLM).** Send segments in batches of 6, in order, each with its
caption and counts. The system prompt contains the enabled scenarios from `playbook.json`
(`look_for`, `handled_well_when`, `coachable_when`) and the verdict definitions. The model
returns strict JSON, one object per segment:

```json
{"segment": 12, "scenario_id": "pedestrian_yield", "verdict": "handled_well",
 "severity": 2, "confidence": 0.82,
 "evidence_quote": "exact words copied from the caption",
 "what_happened": "one or two plain sentences, only facts present in the caption"}
```

Rules for the prompt: use `"scenario_id": "none"` unless the caption clearly supports a
scenario; `evidence_quote` must be an exact substring of the caption (verify in code and
drop the result if it is not); never mention speed in numbers; `temperature` 0; ask for
JSON output and retry once on a parse failure.

**Stage 3, merge.** Consecutive segments with the same scenario and verdict become one
**moment** (first start to last end, list of clip URIs). Drop confidence below 0.6.

**Stage 4, coach.** For each moment, `safer_next_time` and `why_it_matters` come from the
playbook `lesson` for that scenario. The LLM may adapt the wording to the moment in one
sentence, but must not add advice that is not in the playbook. For `handled_well`
moments write `what_you_did_right` instead.

**Stage 5, score the trip.**
`safety_score = clamp(100 - 10 * sum(severity of coachable moments) + 3 * count(handled_well), 0, 100)`.
Show this formula in the UI under "How is this calculated?".
`rating_mismatch`:
- `"underrated"` when rider rating is 3 or lower, there is at least one `handled_well`
  moment, and no coachable moment has severity 2 or more.
- `"missed_risk"` when rider rating is 5 and a coachable moment has severity 2 or more.
- otherwise `null`.

**Stage 6 (tier 3), verify with Cosmos Reason.** For the moments shown in the demo, send
the clip to Cosmos Reason directly (`gpu/` skills) with the scenario's `verify_question`
and store the answer as `verified_by_vlm`. Run this from the VM in `analyze.py`, not in
the pod.

### `moments.json` (the cache the app serves)

```json
{
  "generated_at": "2026-10-02T16:00:00Z",
  "model": "<W&B model id>",
  "simulated_fields": ["rider_rating", "rider_comment", "pickup", "dropoff", "driver"],
  "driver": {"driver_id": "driver-001", "display_name": "Alex", "rider_rating_avg": 4.71},
  "trips": [{
    "trip_id": "T-1041", "date": "2026-09-28", "start_time": "08:12",
    "pickup": "Kensington Market", "dropoff": "Union Station",
    "original_video": "s3://...", "duration_sec": 300,
    "rider_rating": 3, "rider_comment": "...",
    "safety_score": 94, "handled_well": 2, "coachable": 0,
    "rating_mismatch": "underrated",
    "summary": "two sentences"
  }],
  "moments": [{
    "moment_id": "T-1041-m1", "trip_id": "T-1041",
    "scenario_id": "pedestrian_yield", "scenario_title": "Pedestrians crossing ahead",
    "verdict": "handled_well", "severity": 2, "confidence": 0.82,
    "start_sec": 95, "end_sec": 115,
    "sources": ["s3://.../seg_0012.mp4", "s3://.../seg_0013.mp4"],
    "context_before": "s3://.../seg_0011.mp4", "context_after": "s3://.../seg_0014.mp4",
    "people_detected": 3,
    "evidence_quote": "...", "caption": "...",
    "what_happened": "...",
    "what_you_did_right": "...", "safer_next_time": null, "why_it_matters": "...",
    "verified_by_vlm": null
  }]
}
```

`analyze.py` usage: `python analyze.py --trips trips.json --out moments.json`
(`--trip T-1041` for one). It must be re-runnable and print a short summary table.
After the first full run, assign `story_role` values in `trips.json` following the
`assign_to` rules in `trips.seed.json`, then re-run so ratings and mismatches are filled.

### LLM client

```python
client = openai.OpenAI(base_url="https://api.inference.wandb.ai/v1",
                       api_key=os.environ["WANDB_API_KEY"],
                       project=f'{os.environ["WANDB_TEAM"]}/{os.environ["WANDB_PROJECT"]}')
```

List models with `client.models.list()` and pick a strong instruct model that returns
clean JSON. Put the id in env `DASHI_MODEL`. Weave tracing runs on the
VM only (`analyze.py` and `eval/`): wrap every LLM function there in `@weave.op` after
`weave.init("<team>/<project>")`. In `core.py` import Weave inside a `try` and fall back
to a no-op decorator, because the pod does not install Weave.

## 6. App API (`main.py`, FastAPI, routes at `/`)

The Ingress strips `/app`, so the container serves at `/`. The app's own JSON routes live
under `/ds/` so they are never confused with the VSS backend's `/api/v1/` on the same host.

| Route | Returns |
|-------|---------|
| `GET /health` | `{"ok": true}` immediately. Never wait on VSS or the LLM here. |
| `GET /` | `index.html` |
| `GET /ds/home` | driver, latest reviewed trip, proactive cards, totals (kudos, lessons done) |
| `GET /ds/trips` | trip list from `moments.json` |
| `GET /ds/trips/{trip_id}` | trip plus its moments in time order |
| `GET /ds/clip?source=<s3 uri>` | `{"url": "/api/v1/videos/stream?source=...&token=<jwt>"}` |
| `GET /ds/lessons` | one lesson per scenario seen in the driver's moments, with the driver's own example moment, `done` flag |
| `POST /ds/lessons/{scenario_id}/done` | marks a lesson consumed (in-memory) |
| `POST /ds/ask` | body `{"message": "..."}` returns `{"answer", "moment_ids", "trip_id", "next_steps"}` |
| `POST /ds/trips/{trip_id}/evidence` | evidence packet for a rating review (text plus moment list). Simulated send. |
| `POST /ds/analyze` | tier 2. Body `{"trip_id"}`. Starts a live review in a thread, returns `{"job_id"}` |
| `GET /ds/analyze/{job_id}` | tier 2. Stage-by-stage progress, then the new trip |

The app logs in to VSS server-side with `VSS_URL`, `VSS_USERNAME`, `VSS_PASSWORD` from
the Secret, caches the JWT and logs in again on a 401.

Clip playback: the browser plays
`/api/v1/videos/stream?source=<url-encoded>&token=<jwt>` on the same host (that path goes
to the VSS backend, so there is no CORS problem and no proxy code). This puts the team's
short-lived token in the page. Note it under Limitations in the README.

## 7. The Ask agent (`POST /ds/ask`)

Task-shaped tools, implemented in `core.py` over the cache and the VSS API:

- `get_trips()`: trips with rating, score, mismatch.
- `get_trip_moments(trip_id)`: moments for one trip.
- `find_in_my_footage(query)`: `POST /search` filtered to the dashcam camera and this
  driver's trips. Returns clips with captions. This is the live video-search path.
- `get_lesson(scenario_id)`: playbook lesson.

Tier 1: the four suggestion chips map to fixed tool sequences, then one LLM call writes
the answer. Tier 2: free text, with the LLM choosing tools (tool calling, or a JSON
"plan" step if the model has no tool calling).

Chips: "Help me improve my reviews", "How was my last trip?", "Show my best moments",
"Where can I be safer at pickups?".

Fallback: if the LLM call fails or takes longer than 8 seconds, return the same moment
cards with a templated sentence built from the trip and the playbook text. The chips
must never show an error in the demo.

Answer format, always: one sentence of context (which trip, which rating), the evidence
(moment ids, rendered as clip cards), then next steps the driver can choose from (open
the lesson, send evidence for a rating review, see the full trip). At most 60 words of
prose. Second person, warm, never punitive. If the question is not about the driver's
trips or driving, say what the assistant can help with instead.

"Help me improve my reviews" must: take the lowest-rated trips; for a trip with
`rating_mismatch: "underrated"` say the video shows the driver handled it well and offer
to send the evidence; for trips with coachable moments show the moment and its lesson.

## 8. UI (`index.html`, one file, vanilla JS, inline CSS, no build step)

Put `<base href="/app/">` in the head and use relative fetch paths (`ds/trips`). Without
it, the page at `/app` resolves relative paths against the host root and misses the app. For local testing make the
base configurable.

Layout: a centred driver-app column (max width about 480 px) so it reads as a phone app
on a projector, with three tabs.

1. **Coach** (home)
   - Greeting, rider rating (simulated) beside the Dashi safety score.
   - Proactive card for the latest reviewed trip: "New from your 8:12 trip: you yielded
     early to a pedestrian. Nice work." with a button to the moment.
   - Suggestion chips and a text box. Answers render as clip cards, not walls of text.
2. **Trips**
   - List: date, route, rider stars, safety score, and a badge when they disagree:
     "Rating doesn't match the video" (underrated) or "Rider missed this" (missed_risk).
   - Trip detail: a timeline bar with a marker per moment (green handled well, amber
     coachable). Moment card: video player (plays the moment clips in sequence; buttons
     for "5 s before" and "after"), timestamp, scenario tag, verdict chip, then two
     columns: **What happened** and **How it could be safer** (or **What you did
     right**). Under them: the caption quote as evidence, confidence, "AI-reviewed.
     Watch the clip and decide for yourself."
   - On an underrated trip: button "Send evidence for rating review" opens the evidence
     packet with a "Send (simulated)" button.
3. **Learn**
   - Lesson cards (headline, tip, why, the driver's own clip as the example). "Got it"
     marks it done. A small counter: lessons done and kudos (count of handled-well
     moments). Keep incentives to this counter. No leaderboard.

A small "Simulated demo data" note sits in the footer and next to every rider rating.
States to handle: loading, clip failed to load (show the caption instead), no moments in
a trip ("Clean trip. Nothing to flag.").

## 9. Evaluation (`eval/`)

Goal: show how often the agent agrees with a human who watched the clip.

1. `eval/make_sheet.py` samples 20 segments from the chosen trips: 10 the classifier
   flagged, 10 it did not. It prints each caption and a playable link.
2. A teammate watches each clip and fills `eval/labels.json`:
   `{"source", "expected_scenario", "expected_verdict"}`. Label from the video, not the
   caption.
3. `eval/run_eval.py` runs the classifier over the labels with `weave.Evaluation`.
   Scorers: scenario match, verdict match, false-alarm rate (flagged when the human said
   none), and an LLM-judge scorer for groundedness (does `what_happened` state only
   things present in the caption).
4. Write the numbers to `eval/results.md` and the README. Report them as measured, even
   if they are low.
5. If re-ingest was done, run the eval once on the old captions saved in
   `captions_before.json` and once on the new ones, and report both. That shows what the custom ingest prompt bought.

## 10. Deployment notes

- Follow `deployment/deploy-app-no-registry`. ConfigMap from `dashi/app/`. Ingress
  host from `$INGRESS_URL`, path `/app`.
- Add `WANDB_API_KEY`, `WANDB_TEAM`, `WANDB_PROJECT`, `DASHI_MODEL` to the app's
  Secret and to the Deployment env, next to the three VSS values.
- `requirements.txt` for the pod: `fastapi`, `uvicorn`, `requests`, `openai`. Nothing
  else. Do **not** add `weave` here: the container runs `pip install` under `set -e`
  before starting, and a slow or failed install stops the pod from serving. Install
  Weave on the VM for `analyze.py` and `eval/`.
- Check that the pod can reach W&B: `kubectl exec` into it and request
  `https://api.inference.wandb.ai/v1/models` with the key. If it cannot, the app still
  works from the cache (see the fallback in section 7); tell the team.
- Listen on `0.0.0.0:$PORT`. `pip install` runs at container start, so the first rollout
  takes a minute or two.
- After any code or data change: recreate the ConfigMap, then
  `kubectl rollout restart`. A running pod does not pick up ConfigMap changes.
- Verify with `curl http://<host>/app/health` and by opening `http://<host>/app/`.

## 11. Build order and acceptance checks

**Tier 1, the demo must have this**
- Phase 0 done, `discovery.md` written, scenarios pruned, trips chosen.
- `analyze.py` produces `moments.json` for 4 trips with at least one `handled_well` and
  one `coachable` moment that a human agrees with after watching the clip.
- App deployed at `/app/` with Coach, Trips and Learn working from the cache, clips
  playing, chips answering.
- README with inputs, outputs, how to run.

**Tier 2, do next, in this order**
1. Eval run in Weave with numbers in the README.
2. Evidence packet for the underrated trip.
3. Live review of one trip (`/ds/analyze`) with visible stages, ending in a new
   proactive card.
4. Free-text Ask with tool selection.

**Tier 3, only if everything above is solid**
- Cosmos Reason verification of demo moments (`verified_by_vlm`).
- Before/after caption comparison view for the custom ingest prompt.
- Voice input with Canary speech-to-text.

Check after each tier: the app works from a clean rollout with no manual fixing, and the
code is pushed.

## 12. README must contain

What it does (40 words), who it is for, architecture diagram, sponsor tools and what
each does, **inputs** (camera, chunks, ingest prompt, playbook, synthetic trips),
**outputs** (`moments.json` schema, app URL), **how to reproduce** (commands in order),
**evaluation** (method, numbers, link or screenshot of the Weave eval), and
**limitations** (synthetic ratings, research footage standing in for rideshare trips, no
telemetry, AI verdicts are suggestions for the driver and not findings of fault, token
in clip URLs).
