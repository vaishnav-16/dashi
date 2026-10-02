# Dashi: README facts for Teammate 1

Everything below is measured or read from the repo at 10:30 PM UTC. Numbers marked TBD come from
`eval/results.md` once the labels are in.

## What it does (40 words)

Dashi is a video agent on the rideshare driver's side. It reviews each trip's dashcam footage, finds
the moments that matter, shows the clip as evidence, coaches from a fixed playbook, and offers to send
evidence when a low rider rating doesn't match the video.

## Who it is for

Rideshare drivers: contesting unfair ratings, and learning from their own clips.

## Two ways in (the demo walks both)

- **Proactive:** after a trip is reviewed, Dashi posts kudos cards on Coach and lesson cards on Learn,
  built from the driver's own clips, unasked.
- **Ask:** the driver types or taps "Help me improve my reviews". Dashi finds the 3-star trip, shows
  the moment where they yielded to a pedestrian, and offers "Send evidence for a rating review".
- **Ideal replay (stretch):** for each coachable moment, Dashi writes a prompt for a video generation
  model (Cosmos Predict / Transfer style) that re-renders the same scene driven the playbook way.
  Shown under "✦ Ideal replay" on the moment card. The video itself is not generated (no generation
  model is deployed in the event stack).

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

## Sponsor tools and what each does here

- **VAST:** DataEngine pipeline; VastDB hybrid search via `/search` (discovery: 16 queries over 180
  chunks); `/tools/segments` for captions and counts; S3 clips streamed via `/videos/stream`; one
  re-ingest via `/dashboard/reingest`.
- **NVIDIA:** Cosmos Reason writes every caption the classifier reads; our custom prompt was used on 1
  chunk. Cosmos Embed powers search. YOLO `object_counts` feeds `people_detected`.
- **CoreWeave / W&B:** `deepseek-ai/DeepSeek-V4-Flash` on W&B Inference for classify, coach, ideal-replay
  prompt and Ask; Weave traces every pipeline op and the eval (project `vastdata/team-7`).
- **Cursor:** built with Cursor agents.

## Inputs

- Camera `pie_cam-3`: Toronto research dashcam (180 chunks of 30 s, sets 01 to 06) standing in for
  rideshare trips.
- Trips: T-1041 `set06_chunk_0015`, T-1042 `set05_chunk_0000`, T-1043 `set06_chunk_0011`,
  T-1044 `set06_chunk_0017` (one 30 s chunk per trip).
- `reingest_prompt.txt` (737 characters).
- `playbook.json`: enabled `pedestrian_yield` (12 convincing hits), `cyclist_nearby` (11),
  `poor_conditions` (10), `stopped_in_lane` (7), `curb_crowd` (4). Disabled for fewer than 3 convincing
  hits: `turn_across_crosswalk` (1), `curb_pullover` (0), `following_distance` (0 hits).
- `app/trips.json`: synthetic ratings, comments, routes, driver.

## Outputs

- `app/moments.json`: trips (`trip_id`, rating, `safety_score`, `rating_mismatch`, `summary`, ...)
  and moments (`verdict`, `severity`, `confidence`, `start_sec`/`end_sec`, `sources`, `evidence_quote`,
  `caption`, `what_happened`, `what_you_did_right` / `safer_next_time`, `why_it_matters`,
  `ideal_video_prompt`). Schema: BUILD_BRIEF section 5, plus `ideal_video_prompt`.
- App: http://video-lab-team-7.cosmos.vastdata.com/app/ (event network only).

## Reproduce

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

## Evaluation

TBD from `eval/results.md` (n, scenario accuracy, verdict accuracy, false-alarm rate, groundedness).
Weave: https://wandb.ai/vastdata/team-7/weave

## Discovery numbers

- Convincing hits per scenario: see Inputs. A hit is convincing only if the caption, with negated
  sentences removed, matches the scenario's keywords. Similarity scores (0.3 to 0.4) can't separate them.
- Caption wording over 72 candidate segments: mention the camera/ego vehicle 57%, slow 33%, stop 24%,
  yield 7%.
- 22 chunks scanned by the pipeline: 25 moments, only 1 coachable.

## Custom ingest prompt: before / after (chunk `set03_chunk_0026`)

- Segments mentioning the camera vehicle: 3/6 before, 6/6 after. "Slow": 0/6 to 3/6. "Yield": 0/6 to 3/6.
- Segment 1 before: "The scene unfolds on a two-lane, one-way road with a dedicated bicycle lane on the right side..."
- Segment 1 after: "The camera vehicle drives straight along a city street, following a black car ahead at a
  moderate distance. It proceeds through an intersection..."
- More pairs in `discovery.md`.

## Validation stats (grounded pipeline)

Over the 132 segment verdicts in the two candidate scans: 74 "none", 21 dropped because the quote was
not an exact substring of the caption, 0 dropped for low confidence. Every `evidence_quote` in
`moments.json` is an exact substring of its stored caption (checked in code).

## Limitations

- Synthetic ratings, comments, routes and driver (labelled "Simulated" in the UI).
- Research footage standing in for rideshare trips; trips are 30 s chunks.
- No telemetry: no speed or braking claims.
- AI verdicts are suggestions for the driver, not findings of fault.
- Caption-only classification; the VLM does not re-check moments (`verified_by_vlm` is null).
- Captions rarely describe the camera car's own risky choices, so coachable moments are rare (1 in 22
  chunks). The re-ingest prompt fixes this per chunk, but we re-ingested only one.
- The JWT is in clip URLs. Lessons-done state is in memory.
- Ideal-replay prompts are generated text only; no video was rendered.

## Next steps for the pitch

Live `/ds/analyze`, Cosmos Reason verification, render the ideal replay with Cosmos Transfer, the rider
"Let your rider know" loop, re-ingest all trips with the custom prompt, and a post-trained classifier.
