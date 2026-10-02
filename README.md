# Dashi

## What it does

Dashi is a video agent on the rideshare driver's side. It reviews each trip's dashcam footage, finds
the moments that matter, shows the clip as evidence, coaches from a fixed playbook, and offers to send
evidence when a low rider rating doesn't match the video.

## Who it is for

Rideshare drivers who want to contest unfair ratings and learn from their own clips. A rider rates
from the back seat and cannot see why the driver braked; sensor telematics knows the car stopped, not
that a pedestrian stepped out. The video shows the cause.

All ratings, rider comments, routes and the driver ("Alex") are **simulated**. The footage is a
Toronto dashcam research set (`camera_id` `pie_cam-3`) standing in for a driver's trips.

## Two ways into the agent

- **Proactive.** After a trip is reviewed, Dashi posts cards without being asked: kudos cards on the
  **Coach** tab for moments the driver handled well, and lesson cards on the **Learn** tab built from
  the driver's own clip, with a "Mark as learned" button.
- **Ask.** The driver types in plain English, for example "Help me improve my rating". Dashi finds the
  lowest-rated trip, shows the moment as a clip card, and offers next steps such as "Send evidence for
  a rating review" or opening the lesson. Free-text questions that match no topic run a live VAST
  hybrid search over the driver's dashcam footage and answer with the trip and timestamp.
- **Ideal replay (stretch).** For each coachable moment, Dashi writes a prompt for a video generation
  model (Cosmos Predict / Transfer style) describing the same scene driven the playbook way. It is
  shown under "✦ Ideal replay" on the moment card. The video itself is not generated, because no
  generation model is deployed in the event stack.

## Architecture

```
 Dashcam video (S3, pie_cam-3)            PRE-BUILT (VAST DataEngine)
   -> YOLO11 detections
   -> Cosmos Reason captions  <- our custom prompt (reingest_prompt.txt, 1 chunk)
   -> Cosmos Embed vectors -> VastDB  <-  VSS backend API
                        |
 Dashi                  v
   discover.py   scenario searches (/search), prune playbook, rank chunks
   app/core.py   gather -> classify (W&B LLM) -> validate (exact quote) -> merge -> coach -> ideal prompt -> score
   app/analyze.py  CLI: candidate scan, role assignment, writes app/moments.json
   app/main.py   FastAPI JSON API under /ds/, serves the UI
   app/ask.py    task-shaped tools + chip intents, one LLM call, templated fallback
   app/index.html  single-page driver app (Coach, Trips, Learn)
   app/clients.py  VSS client (JWT) + W&B inference client
   eval/         make_sheet.py, run_eval.py (weave.Evaluation), results.md
```

The app serves from the cached `app/moments.json`. If the LLM call for an Ask answer fails or takes
longer than 8 seconds, a templated answer built from the same data is returned instead.

## Sponsor tools and what each does

| Tool | What it does in Dashi |
|---|---|
| **VAST** | DataEngine pipeline; VastDB hybrid search via `/search` (discovery: 16 queries over 180 chunks; live search in Ask); `/tools/segments` for captions and object counts; S3 clips streamed via `/videos/stream`; one re-ingest via `/dashboard/reingest`. |
| **NVIDIA Cosmos Reason** | Writes every caption the classifier reads. Our custom prompt was used on `set03_chunk_0026` and on a teammate's re-ingested chunks, including T-1042. |
| **NVIDIA Cosmos Embed** | Embeddings behind search. |
| **NVIDIA YOLO** | `object_counts` feeds `people_detected` on each moment. |
| **CoreWeave / W&B Inference** | `deepseek-ai/DeepSeek-V4-Flash` for classify, coach, ideal-replay prompt and Ask. |
| **W&B Weave** | Traces every pipeline op and runs the eval (project `vastdata/team-7`). |
| **Cursor** | The app, pipeline, eval and docs were built with Cursor agents. |

## Inputs

- **Camera** `pie_cam-3`: Toronto research dashcam, 180 chunks of 30 s (sets 01 to 06), each split
  into 6 segments of 5 s. It stands in for rideshare trips.
- **Chunks per trip:** one 30 s chunk per trip.

  | Trip | Chunk |
  |---|---|
  | T-1041 | `set06_chunk_0015` |
  | T-1042 | `set05_chunk_0000` |
  | T-1043 | `set06_chunk_0011` |
  | T-1044 | `set06_chunk_0017` |

- **`reingest_prompt.txt`** (737 characters, limit 800): a custom Cosmos Reason prompt that asks the
  model to describe what the camera vehicle itself does (slows, stops, yields, turns).
- **`playbook.json`:** scenarios with what to look for, when it counts as handled well or coachable,
  and the lesson. Discovery enabled a scenario only if it had at least 3 convincing hits in the footage:

  | Scenario | Convincing hits | Status |
  |---|---|---|
  | `pedestrian_yield` | 12 | enabled |
  | `cyclist_nearby` | 11 | enabled |
  | `poor_conditions` | 10 | enabled |
  | `stopped_in_lane` | 7 | enabled |
  | `curb_crowd` | 4 | enabled |
  | `turn_across_crosswalk` | 1 | disabled (fewer than 3) |
  | `curb_pullover` | 0 | disabled (fewer than 3) |
  | `following_distance` | 0 | disabled (fewer than 3) |

  A hit is convincing only if the caption, with negated sentences removed, matches the scenario's
  keywords. Similarity scores (0.3 to 0.4) alone could not separate good hits from bad ones.
- **`app/trips.json`:** synthetic (simulated) ratings, rider comments, routes and driver.

## Outputs

- **`app/moments.json`**, the cache the app serves. Schema is BUILD_BRIEF section 5 plus one extra
  field, `ideal_video_prompt`.
  - Top level: `generated_at`, `model`, `simulated_fields`, `driver`, `trips`, `moments`.
  - Trip: `trip_id`, `date`, `start_time`, `pickup`, `dropoff`, `original_video`, `duration_sec`,
    `story_role`, `rider_rating`, `rider_comment`, `safety_score`, `handled_well`, `coachable`,
    `rating_mismatch` (`underrated`, `missed_risk` or null), `summary`.
  - Moment: `moment_id`, `trip_id`, `scenario_id`, `scenario_title`, `verdict` (`handled_well` or
    `coachable`), `severity`, `confidence`, `start_sec`, `end_sec`, `sources` (segment clip URIs),
    `context_before`, `context_after`, `people_detected`, `evidence_quote`, `caption`,
    `what_happened`, `what_you_did_right` / `safer_next_time`, `why_it_matters`, `verified_by_vlm`
    (null), `ideal_video_prompt` (text for coachable moments, otherwise null).
  - Safety score: `clamp(100 - 10 * sum(severity of coachable moments) + 3 * count(handled_well), 0, 100)`.
- **Current data:** 4 trips, 8 moments (7 handled well, 1 coachable).

  | Trip | Simulated route | Simulated rating | Safety score | Mismatch |
  |---|---|---|---|---|
  | T-1041 | 08:12 Kensington Market to Union Station | 3 | 100 | underrated |
  | T-1042 | 17:40 Yonge-Dundas Square to The Annex | 5 | 83 | missed_risk |
  | T-1043 | 12:05 Liberty Village to Distillery District | 5 | 100 | none |
  | T-1044 | 09:30 Bloor-Yonge to Harbourfront | 4 | 100 | none |

- **App:** http://video-lab-team-7.cosmos.vastdata.com/app/ (reachable on the event network only).

## How to reproduce

From the repo root, on a VM with the VSS and W&B environment variables set (`INGRESS_URL`, `USERNAME`,
`PASSWORD`, `WANDB_API_KEY`, `WANDB_TEAM`, `WANDB_PROJECT`, `DASHI_MODEL`):

```sh
python3 -m venv --without-pip .venv && curl -fsSL https://bootstrap.pypa.io/get-pip.py | .venv/bin/python
.venv/bin/python -m pip install fastapi uvicorn requests openai weave
cd app
../.venv/bin/python ../discover.py
../.venv/bin/python analyze.py --chunks ../candidates.txt --out ../work/candidates_review.json
../.venv/bin/python analyze.py --assign ../work/candidates_review.json --trips trips.json
../.venv/bin/python analyze.py --trips trips.json --out moments.json
../.venv/bin/python ../eval/make_sheet.py
../.venv/bin/python ../eval/run_eval.py
cd .. && KUBECONFIG=/config/team-7-k8s.yaml deploy/deploy.sh code
```

In order: discovery searches and ranks chunks; the first `analyze.py` scans candidate chunks; the
second assigns trip roles; the third writes `moments.json`; `make_sheet.py` builds the labelling sheet;
`run_eval.py` scores the classifier; `deploy.sh code` refreshes the ConfigMap and restarts the pod.

Run the app locally for testing: `cd app && DASHI_LOCAL=1 PORT=8090 ../.venv/bin/python main.py`.

## Evaluation

Method (`eval/run_eval.py`):

1. `eval/make_sheet.py` samples segments from the chosen trips, both flagged and not flagged by the
   classifier (`eval/sheet.md`, 12 rows).
2. A teammate watches each 5 s clip and labels the scenario and verdict from the **video**, not the
   caption, into `eval/labels.json`.
3. `run_eval.py` runs the same classifier as the app (same prompt, exact-quote validation and
   confidence floor) on each segment's caption and YOLO counts, inside `weave.Evaluation`.
4. Scorers: scenario match, verdict match, false-alarm rate (flagged when the human said none), and an
   LLM-judge groundedness check (does `what_happened` state only facts present in the caption).

Results: see eval/results.md (being filled from hand labels at submission time).

Weave project: https://wandb.ai/vastdata/team-7/weave

## Custom ingest prompt: before and after

The default captions describe the scene well but rarely say what the camera vehicle does. Over 72
candidate segments: camera/ego vehicle mentioned 57%, "slow" 33%, "stop" 24%, "yield" 7%.

We re-ingested chunk `set03_chunk_0026` with `reingest_prompt.txt` (same 6 segments):

| Segments mentioning | Before | After |
|---|---|---|
| the camera vehicle | 3/6 | 6/6 |
| "slow" | 0/6 | 3/6 |
| "stop" | 4/6 | 5/6 |
| "yield" | 0/6 | 3/6 |

- Segment 1 before: "The scene unfolds on a two-lane, one-way road with a dedicated bicycle lane on the right side..."
- Segment 1 after: "The camera vehicle drives straight along a city street, following a black car ahead at a
  moderate distance. It proceeds through an intersection..."
- More pairs in `discovery.md`.

**The only coachable moment in 22 scanned chunks (T-1042, `set05_chunk_0000`) came from a chunk that
had been re-ingested with the custom prompt.** Its caption says "The vehicle then begins to move
forward and turns left" while a pedestrian crosses, the kind of camera-car behaviour the default
captions leave out. Its pre-re-ingest captions were not saved, so there is no before/after pair for
that chunk.

## Validation stats

- Over the 132 segment verdicts in the two candidate scans: 74 "none", 21 dropped because the
  evidence quote was not an exact substring of the caption, 0 dropped for low confidence.
- Every `evidence_quote` in `moments.json` is an exact substring of its stored caption (checked in code).
- 22 chunks scanned by the pipeline produced 25 moments, only 1 coachable.

## Limitations

- Ratings, rider comments, routes and driver are synthetic (labelled "Simulated" in the UI).
- Research footage stands in for rideshare trips; each trip is one 30 s chunk.
- No telemetry: no speed or braking claims.
- AI verdicts are suggestions for the driver, not findings of fault.
- Classification is caption-only; the VLM does not re-check moments (`verified_by_vlm` is null).
- Captions rarely describe the camera car's own risky choices, so coachable moments are rare (1 in 22
  chunks). The re-ingest prompt fixes this per chunk, but only a small number of chunks were re-ingested.
- The short-lived VSS JWT is included in clip URLs in the page. Lessons-done state is in memory.
- Ideal-replay prompts are text only; no video was rendered.
- Trip T-1044's simulated rider comment ("Drop-off was a bit rushed") is not supported by its video,
  which shows only handled-well moments.

## Next steps

- Live trip review (`/ds/analyze`) with visible stages, ending in a new proactive card.
- Cosmos Reason verification of each moment (`verified_by_vlm`).
- Render the ideal replay with Cosmos Transfer.
- The rider "Let your rider know" loop.
- Re-ingest all trips with the custom prompt.
- A post-trained classifier.
