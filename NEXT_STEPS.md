# Dashi: next steps (9:55 PM to 11:05 PM freeze)

Written 9:50 PM UTC by the planner for the implementer agent (fresh session). Read this file
top to bottom and execute it in order. Stop at every **HUMAN DECISION** and ask Vaishnav.
Spec: `BUILD_BRIEF.md`. Team plan and ownership: `PLAN.md`. State: `PROGRESS.md`.

## 0. Summary

The app is finished and live at http://video-lab-team-7.cosmos.vastdata.com/app/, but it
serves hand-made sample data (`app/moments.sample.json`). What is left on the critical path
is the real review pipeline:

1. Discovery: search the dashcam footage for each playbook scenario, prune the playbook and
   pick candidate chunks.
2. Write `app/core.py` and `app/analyze.py`. They classify each segment caption with the W&B
   LLM, keep only quotes that really appear in the caption, merge segments into moments,
   coach from the playbook and score each trip.
3. Write `app/moments.json` and `app/trips.json`. The app switches to them automatically
   once `app/moments.json` exists.
4. Run a small Weave eval against 10 to 12 human labels.
5. Hand the facts to Teammate 1 for the README.

Do **not** rebuild or restyle the UI. Do **not** change `main.py` or `index.html`; their
read contract is listed in section 3.8. **Trip = one 30 s chunk** (decision and reasons in
section 3.1).

Facts the planner checked at 9:45 PM (read-only):

- There are 180 `pie_cam-3` chunks: sets `set01`..`set06`, 30 consecutive chunks each. Every
  chunk has `chunk_duration_sec` 30.0 and 6 segments of 5 s (0-5, 5-10, ... 25-30).
- `/tools/segments` returns `{"original_video", "total", "segments": [...]}`.
  `segment_start_sec` comes back as a float, `segment_number` as an int, and
  `object_counts` as a JSON **string**. Cast everything with `float()`, `int()` and
  `json.loads()` anyway.
- **`POST /search` rejects `llm_top_n: 0` with HTTP 422** (the minimum is 1). Use
  `llm_top_n: 1`. One search takes about 6 s. Hits are in `results[]`, with the fields
  `source`, `reasoning_content`, `similarity_score`, `original_video`, `segment_number`,
  `segment_start_sec`, `segment_end_sec`, `object_counts` and others.
- Similarity scores for good queries are only 0.34 to 0.39, so the score alone is not a
  usable "convincing" signal. Section 4 adds a caption check.
- Caption wording, from a sample of 180 segments:
  - 59% mention the ego or camera vehicle.
  - 18% say slow or slowing.
  - 7% say the ego vehicle stops or is stopped.
  - 2% say yield.
  - "cyclist" appears in 56%, but almost always as "No pedestrians, cyclists ... are
    visible". The checks below must remove negated sentences before matching keywords.
- `ask.py find_in_my_footage` uses `llm_top_n: 0`, so it would get a 422 if it were
  called. No route calls it today. Optional 1-line fix in step 6.
- The VM env has `INGRESS_URL`, `USERNAME`, `PASSWORD` (via `/config/team-7.config`),
  `WANDB_API_KEY`, `WANDB_TEAM`, `WANDB_PROJECT`, `S3_CHUNKS_BUCKET` and
  `S3_SEGMENTS_BUCKET`. `clients.setting()` already resolves these.
- The venv has pip. Weave is **not** installed.

### Schedule, ordered by judging value (brief section 11, tier 1 first)

| Time (UTC) | Step | Cut line |
|---|---|---|
| 9:55-10:00 | 1. Setup: install Weave in the background, `git pull --rebase` | |
| 10:00-10:15 | 2. Discovery script, `discovery.md`, prune playbook, `captions_before.json` | **10:15: HUMAN DECISION D1** (scenarios + candidate chunks) |
| 10:15-10:20 | 3. Start one re-ingest (optional, in the background) | **If not started by 10:20, skip it** (D2) |
| 10:15-10:38 | 4. `core.py` + `analyze.py`, run on ~10 candidates, assign roles, final `moments.json` | **10:38: if there is still no valid `moments.json`, ship with fewer trips (D4)**. Never ship the sample as if it were real |
| 10:38-10:48 | 5. Local check + redeploy + demo-path check on the public URL | **10:48: the live app must serve real data.** This is the tier 1 line |
| 10:38 | Send moment list to Teammate 1 (agree/disagree) and the eval sheet to Teammate 2 | **D3** happens while the redeploy runs |
| 10:48-10:58 | 6. Eval with Weave, `eval/results.md` | **10:58: stop the eval wherever it is.** Report n and what was measured |
| 10:58-11:02 | 7. Hand README facts to Teammate 1, commit + push | Push no later than 11:02 |
| 11:02-11:05 | 8. Freeze: clean redeploy, demo run-through | **11:05: no more code** |
| skip | Rider "Let your rider know" loop, `/ds/analyze`, Cosmos Reason verify | Cut. Only if everything above is done before 10:50 |

---

## 1. Step 1: setup (9:55, 3 min)

Goal: install Weave without blocking, and start from the latest code.

```sh
cd ~/vast-builders-challenge/dashi
git pull --rebase
.venv/bin/python -m pip install -q weave > /tmp/weave_install.log 2>&1 &   # background
mkdir -p work eval
env | cut -d= -f1 | sort | grep -E 'WANDB|INGRESS|USERNAME|S3_'          # names only
```

Shell rules for the implementer:

- Commands that reach the network or localhost need `required_permissions: ["all"]`.
- Never print secrets.
- Never run `pkill -f` with a pattern that could match the agent wrapper. Kill the local
  server by PID instead (`kill <pid>`).
- **Never** add `weave` to `app/requirements.txt`. It stays `fastapi uvicorn requests openai`.

Acceptance: `git status` is clean. `.venv/bin/python -c "import weave"` works by 10:15
(check `/tmp/weave_install.log` if it does not).

---

## 2. Step 2: discovery (10:00-10:15)

### 2.1 Files

- `dashi/discover.py` (new, at the repo root, **not** in `app/`)
- `dashi/discovery_hits.json` (raw hits)
- `dashi/candidates.txt` (one `original_video` per line, ranked)
- `dashi/discovery.md`
- `dashi/playbook.json` (flip `enabled`), then copy it to `dashi/app/playbook.json`
- `dashi/captions_before.json`

### 2.2 `discover.py`

```python
# run from dashi/app so `import clients` works:  cd app && ../.venv/bin/python ../discover.py
import sys, json, re, collections, concurrent.futures, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent / "app"))
import clients
ROOT = pathlib.Path(__file__).parent
CAM = "pie_cam-3"
vss = clients.VSS()
```

Functions:

- `list_chunks() -> list[dict]`
  - Page `vss.get("videos/explore", scope="all", limit=100, offset=off)` over `r["total"]`.
    The items are in `r["chunks"]`.
  - Keep those with `camera_id == CAM`.
  - Print a compact table: per set, the count plus the first and last filename. Do not
    print all 180 rows.
- `search(query) -> list[dict]`
  - `vss.post("search", {"query": q, "top_k": 10, "llm_top_n": 1, "min_similarity": 0.3, "metadata_filters": {"camera_id": CAM}})`.
  - Return `results` with these keys: `source`, `original_video`, `segment_number`,
    `similarity_score`, `reasoning_content`.
  - **`llm_top_n` must be at least 1.** 0 gives HTTP 422.
- `affirmative(caption) -> str`
  - Split on `(?<=[.!?])\s+`.
  - Drop sentences matching `r"\b(no|not|none|without|absence|neither|nor)\b"` (case
    insensitive).
  - Rejoin the rest. This stops "No pedestrians or cyclists are visible" from counting as
    a hit.
- `CONVINCING = {...}` holds one or two regexes per scenario. All must match
  `affirmative(caption)`, case insensitive:

  | scenario | regexes (all must match) |
  |---|---|
  | `pedestrian_yield` | `pedestrian\|person\|people` AND `cross\|crosswalk\|step(s\|ping)? (off\|into)\|in the road\|roadway` |
  | `curb_crowd` | `(group\|several\|crowd\|multiple\|many) (of )?(pedestrians\|people)` |
  | `stopped_in_lane` | `double[- ]?park\|stopped in the (travel )?lane\|blocking (a\|the) lane\|stopped in the (middle\|road)` |
  | `curb_pullover` | `pull(s\|ed\|ing)? (over\|out\|in\|away\|to the curb\|from the curb)` |
  | `following_distance` | `(directly\|immediately) ahead\|close(ly)? behind\|brake lights\|same lane ahead` |
  | `turn_across_crosswalk` | `turn(s\|ed\|ing)?` AND `crosswalk\|pedestrian` |
  | `cyclist_nearby` | `cyclist\|bicycl\|bike` |
  | `poor_conditions` | `night\|rain\|wet road\|glare\|construction\|roadwork\|cones?\b\|blocked lane` |

- `main()`:
  1. Run `list_chunks()`. Print the field names of one segment
     (`vss.get("tools/segments", original_video=...)["segments"][0].keys()`) and one full
     caption.
  2. For every scenario in `playbook.json` (all 8, ignoring `enabled`) and every
     `search_queries` entry, run `search()`. Use `ThreadPoolExecutor(max_workers=4)`;
     16 queries take about 30 s.
  3. Mark each hit `convincing = all(re.search(p, affirmative(cap), re.I) for p in CONVINCING[sid])`.
     Dedupe hits per scenario by `source`.
  4. Save `discovery_hits.json` as
     `{scenario_id: [{"query", "source", "original_video", "segment_number", "score", "convincing", "caption"}]}`.
  5. Per scenario, print: hits, convincing count, and the top 2 convincing captions (first
     200 characters plus the segment filename).
  6. **Disable rule:** `enabled = convincing_count >= 3`. If more than 5 survive, keep the 5
     with the most convincing hits. Write `playbook.json` with only the `enabled` values
     changed (`json.dump(..., indent=2, ensure_ascii=False)`). Then
     `cp playbook.json app/playbook.json`.
  7. Rank chunks.
     - `chunk_score[ov] = 2 * (number of distinct enabled scenarios with a convincing hit in ov) + sum(score of convincing hits in ov)`.
     - Add `+3` for any chunk Teammate 2 named. Put their filenames in
       `dashi/teammate2_chunks.txt`, one basename per line; ignore the file if it is
       missing.
     - Complete each basename to `s3://{S3_CHUNKS_BUCKET}/{USERNAME}/<basename>` and match
       it against the explore `original_video`. Prefer the explore value.
     - Write the top 12 to `candidates.txt`. Print them with their scenarios.
  8. Write `captions_before.json`:
     `{original_video: [segment dicts as returned by /tools/segments]}` for the 12
     candidates. This file must exist **before** any re-ingest.
- `discovery.md` (write it with Python from the same run, then hand-edit the decision
  lines). Contents:
  1. The `camera_id` used (`pie_cam-3`), chunk counts per set, and "30 s per chunk, 6 x 5 s
     segments".
  2. Real field names: clip URI `source`, caption `reasoning_content`, timing
     `segment_start_sec`/`segment_end_sec`, order `segment_number`, YOLO
     `object_classes`/`object_counts` (JSON string). Plus the 422 note on `llm_top_n`.
  3. Per scenario: queries, number of hits, number of convincing hits, two example captions
     with filename and score, and enabled yes/no.
  4. Caption wording stats over the candidates: share of segments mentioning
     ego/camera vehicle, slow, stop, yield. Use the regexes from section 0; the planner's
     sample gave 59 / 18 / 7 / 2 %.
  5. The candidate chunk list.
  6. The re-ingest decision (step 3), and later the two before/after caption pairs.
  7. "Trip = one 30 s chunk" and why (section 3.1).

Command:

```sh
cd ~/vast-builders-challenge/dashi/app && ../.venv/bin/python ../discover.py
```

Acceptance:

- `discovery_hits.json`, `candidates.txt` (12 lines), `captions_before.json` (12 keys) and
  `discovery.md` all exist.
- `app/playbook.json` equals `playbook.json`.
- Between 3 and 5 scenarios are enabled. If fewer than 3 pass, keep the 3 with the most
  convincing hits enabled and say so in `discovery.md`.

**Brief section 3.6 fallback** (only if no curb or stop scenario survives): run
`curb_crowd` / `stopped_in_lane` queries once without `metadata_filters` and record which
`camera_id` values show them, in `discovery.md`. Do not use those clips in trips; this is
only a note for the README.

### HUMAN DECISION D1 (about 10:15)

Show Vaishnav:

- the enabled scenarios and the convincing count for each;
- the 12 candidates with the scenarios each one matches;
- whether Teammate 2's filenames were folded in.

Ask: "Confirm these scenarios and candidates? Any chunk from Teammate 2 to add?" Default if
there is no answer in 2 minutes: proceed as printed.

---

## 3. Step 3: one re-ingest (optional, 10:15-10:20 start, runs in the background)

Recommendation: **GO for exactly one chunk, used only for the README before/after
caption pairs**. Captions describe the scene well, but say what the camera car does in only
about 7 to 18% of segments. That is exactly the gap the custom prompt is meant to fix, and
it gives Cosmos Reason a visible job in the write-up.

Pick a chunk that is **not** among the trips. Choose candidate #11 or #12 from
`candidates.txt`, ideally one with a `pedestrian_yield` hit. Re-ingest replaces captions,
so it would invalidate cached analysis and eval inputs for any trip chunk.

### HUMAN DECISION D2

Ask: "Re-ingest chunk `<filename>` once with `reingest_prompt.txt` as the custom prompt,
keeping camera_id, capture_type and location? Only this one chunk will change." This
follows the `ingest/reingest-chunk` skill, which requires the user to confirm the chunk,
the prompt mode and the metadata. If the answer is no, or it is already past 10:20, skip
this step and write "Re-ingest: not done (time)" in `discovery.md`.

If GO, use this procedure (Python via `clients.VSS`, from `dashi/app`):

```python
import clients, json, time, pathlib
v = clients.VSS()
ov = "<exact original_video from explore>"
before = json.loads(pathlib.Path("../captions_before.json").read_text())
assert ov in before, "dump captions_before.json first"
prompt = pathlib.Path("../reingest_prompt.txt").read_text().strip()
assert len(prompt) <= 800
job = v.post("dashboard/reingest", {"original_video": ov, "chunk_count": 1, "custom_prompt": prompt})
print({k: job[k] for k in job if k != "token"})          # find the job id key, e.g. job_id
jid = job.get("job_id") or job.get("id")
while True:
    s = v.get(f"dashboard/reingest/{jid}")
    print(s.get("status"), s.get("completed_chunks"), s.get("indexed_segments"), s.get("total_segments"))
    if s.get("status") in ("completed", "failed", "error"): break
    time.sleep(4)
```

Run it as a background shell (`block_until_ms: 0`) and continue with step 4.

When it completes:

1. Fetch `tools/segments` for `ov` again and write `../captions_after.json`
   (`{ov: segments}`).
2. Check that it still has 6 segments.
3. Put two before/after pairs (same `segment_number`, the 300 characters around the
   difference) into `discovery.md` under "Custom ingest prompt: before / after".

Never re-ingest a second chunk.

---

## 4. Step 4: the pipeline (10:15-10:38)

### 4.1 Trip length: decided, one chunk per trip

What the app assumes about a trip:

- `trip.original_video` is a **string**. `ask.py find_in_my_footage` builds a `set` of
  them, and a list would raise `TypeError`.
- `index.html` draws the timeline with `dur = t.duration_sec || max(30, end_sec)`.
- Moment `start_sec`/`end_sec` are seconds from the start of the trip.
- `context_before`/`context_after` are single URIs.

One chunk is exactly one classifier batch of 6 segments, and discovery hits are
segment-level inside one chunk. Combining chunks adds offsets, cross-chunk merging and
more LLM calls, with no judging upside.

So:

- `trip.original_video` = the chunk URI (string)
- `duration_sec` = 30
- `start_sec` = `segment_start_sec`

**Fallback (only for the `mixed` role, only if no single candidate has both a handled_well
and a coachable moment):** `core.review_trip` accepts an optional
`trip["original_videos"]` list of 2 consecutive same-set chunks.

- `original_video` stays the first URI (string).
- Segments from chunk k get `start_sec += 30 * k`.
- `duration_sec = 30 * len(list)`.
- Merging may cross the chunk boundary.
- `context_before`/`context_after` come from the concatenated segment list.
- No app change is needed (`find_in_my_footage` is unused).

### 4.2 Files

- `app/core.py`: pipeline functions, no CLI, importable on the VM. Do **not** import it
  from `main.py`.
- `app/analyze.py`: the CLI.
- `app/trips.json`, `app/moments.json`: outputs.
- `work/classify_cache.json`: cache of LLM classifier outputs. It makes reruns stable and
  fast, so role assignment does not change between runs. Keep it out of `app/`.

### 4.3 `core.py` skeleton

```python
"""Dashi review pipeline: gather segments, classify captions, merge, coach, score."""
import hashlib, json, pathlib, re
import clients
try:
    import weave
    op = weave.op
except Exception:          # the pod does not install weave
    def op(f=None, **_):
        return f if f else (lambda g: g)

CONF_MIN = 0.6
BATCH = 6
CACHE = pathlib.Path(__file__).resolve().parent.parent / "work" / "classify_cache.json"
```

Functions and signatures:

1. `load_playbook(path="playbook.json") -> dict`
2. `enabled_scenarios(pb) -> list[dict]`: `[s for s in pb["scenarios"] if s["enabled"]]`
3. `gather(vss, original_video) -> list[dict]` (stage 1)
   - `vss.get("tools/segments", original_video=ov)["segments"]`, sorted by
     `int(segment_number)`.
   - Each item becomes:
     ```python
     {"segment": int(s["segment_number"]), "start_sec": float(s["segment_start_sec"]),
      "end_sec": float(s["segment_end_sec"]), "source": s["source"],
      "caption": s.get("reasoning_content") or "", "counts": counts,
      "people": int(counts.get("person", 0)),
      "vehicles": sum(int(counts.get(k, 0)) for k in ("car","truck","bus","motorcycle","bicycle"))}
     ```
   - `counts = json.loads(s["object_counts"] or "{}")` if it is a string, else the dict
     itself. On a parse error use `{}`.
4. `system_prompt(pb) -> str`: built exactly as in 4.4.
5. `classify_batch(segs, pb, model=clients.MODEL) -> list[dict]` (stage 2), decorated with
   `@op`.
   - Build `payload = {"segments": [{"segment", "start_sec", "caption", "object_counts": counts}]}`.
   - Cache key: `sha256(model + system_prompt + json.dumps(payload, sort_keys=True))`.
     Return the cached value if present.
   - Call
     `clients.llm(timeout=60).chat.completions.create(model=model, temperature=0, max_tokens=2000, response_format={"type": "json_object"}, messages=[system, user=json.dumps(payload, ensure_ascii=False)])`.
   - Parse `json.loads(content)["segments"]`. If parsing fails, or the list length differs
     from the batch, or the segment numbers differ, **retry once**. If the retry also
     fails, return `[]` for that batch and print a warning.
   - Store the raw list in the cache. Validation happens in `validate`, not here.
6. `validate(raw, segs, pb) -> list[dict]`. Keep an item only if all of these hold:
   - `item["segment"]` is one of the batch segment numbers.
   - `scenario_id` is in the enabled ids and is not `"none"`.
   - `verdict` is in `{"handled_well", "coachable"}`.
   - `severity` is an int in 1..3. Clamp it; non-numeric means drop the item.
   - `confidence` is a float of at least `CONF_MIN`.
   - `quote` is non-empty and `quote in caption`, where
     `quote = item["evidence_quote"].strip().strip('"').strip()` and `caption` is that
     segment's caption. The check is an **exact substring**; no fuzzy matching.
   - `what_happened` is non-empty, has no digits followed by `km` or `mph`, and does not
     match `r"speed(ing)?|hard brak|braked hard|slammed"`.

   Each kept item is joined with its segment data. Return the kept items. Also count the
   drops by reason (`bad_quote`, `low_conf`, `bad_id`, `none`) and print them.
7. `merge(items, segs, trip_id, pb) -> list[dict]` (stage 3)
   - Sort by segment number. Consecutive segments (`n+1`) with the same `scenario_id` and
     `verdict` form one moment:
     - `start_sec` = the first segment's start, `end_sec` = the last segment's end.
     - `sources` = the URIs in order.
     - `severity` = the max; `confidence` = `round(min, 2)`.
     - `evidence_quote`, `caption` and `what_happened` come from the highest-confidence
       segment, so the quote stays a substring of the stored `caption`.
     - `people_detected` = the max of `people`.
     - `context_before` = the `source` of the segment just before the first one (`None` at
       the start of the trip); `context_after` likewise.
   - `moment_id = f"{trip_id}-m{i}"` for i = 1, 2, ... in time order.
   - `scenario_title` comes from the playbook.
8. `coach(moment, pb) -> dict` (stage 4), decorated with `@op`. One LLM call, temperature
   0, JSON. Prompt in 4.5.
   - `why_it_matters` = the playbook `lesson.why`, verbatim.
   - For coachable moments:
     - `safer_next_time` = the LLM sentence if it passes the checks below, else
       `lesson.tip` verbatim.
     - `what_you_did_right = None`.
   - For handled_well moments:
     - `what_you_did_right` = the LLM sentence if it passes the checks, else
       `"You handled this the way the playbook recommends."`
     - `safer_next_time = None`.
   - Checks on the LLM sentence:
     - at most 30 words and ends with `.`;
     - no digits;
     - does not match `r"speed|brak|mph|km/h|fault|ticket|illegal"`;
     - for coachable moments it must share at least 2 content words (4+ letters) with
       `lesson.tip`.
   - Set `verified_by_vlm = None`.
9. `score(moments) -> int` (stage 5), exactly as the brief:
   `max(0, min(100, 100 - 10 * sum(m["severity"] for coachable) + 3 * count(handled_well)))`.
10. `rating_mismatch(rating, moments) -> str | None`, exactly as the brief:
    - `"underrated"` if `rating <= 3` and there is at least 1 handled_well moment and no
      coachable moment with severity of 2 or more;
    - `"missed_risk"` if `rating == 5` and some coachable moment has severity of 2 or more;
    - else `None`.
11. `summary(moments) -> str`: a two-sentence template, no LLM.
    - Sentence 1: `"{hw} moment(s) handled well and {co} to work on."`, or
      `"Clean trip. Nothing to flag."` when there are no moments.
    - Sentence 2: the `what_happened` of the highest-severity moment, if there is one.
12. `review_trip(vss, trip, pb, roles) -> (trip_out, moments)`, decorated with `@op`:
    1. Gather segments (or concatenate them for `original_videos`).
    2. Classify in batches of 6, validate, merge, coach.
    3. `rider_rating`/`rider_comment` come from `roles[trip["story_role"]]`. If the role is
       missing or `ASSIGN_AFTER_ANALYSIS`, use `None` for both.
    4. Build the trip fields from 4.8. `rating_mismatch` is `None` when the rating is
       `None`.

### 4.4 Classifier system prompt (build it with this exact text)

`{SCENARIOS}` is filled with one block per **enabled** scenario:

```
- id: {id}
  title: {title}
  look for: {look_for}
  handled well when: {handled_well_when}
  coachable when: {coachable_when}
```

`{VERDICTS}` lists the three lines from `playbook["verdicts"]` as `- {key}: {text}`.
`{SEVERITY}` lists `playbook["severity"]` as `- {key}: {text}`.

```
You review captions of forward-facing dashcam video from a rideshare driver's car. The car
with the camera is the "camera vehicle"; captions may call it the "ego vehicle". You never
see the video. You only see, for each 5-second segment, a caption written by a vision model
and object-detector counts. The counts are noisy: ignore animals, kites and airplanes, and
person counts are often too low.

For every segment, decide whether the caption clearly shows one of these scenarios and how
the camera vehicle handled it.

Scenarios:
{SCENARIOS}

Verdicts:
{VERDICTS}

Severity (only for handled_well and coachable; for handled_well it is how serious the
hazard was):
{SEVERITY}

Rules:
1. Default to "scenario_id": "none" and "verdict": "none". Only pick a scenario when the
   caption clearly describes it. A person on the sidewalk, or a sentence saying no
   pedestrians or cyclists are visible, is NOT a scenario.
2. Judge the camera vehicle only by what the caption says or clearly implies it does
   (for example "the vehicle is stopped at the crosswalk while a pedestrian crosses").
   If the caption does not say how the camera vehicle behaved, use verdict "none".
3. "coachable" only when the caption describes the camera vehicle's own choice creating
   risk. Never invent a mistake.
4. "evidence_quote": copy 5 to 25 consecutive words from THIS segment's caption, character
   for character, that support the verdict. Do not paraphrase, fix spelling or join
   sentences. Use "" when the verdict is "none".
5. "what_happened": one or two plain sentences in second person ("you" is the camera
   vehicle), using only facts in the caption. Use "" when the verdict is "none".
6. Never mention speed, speed numbers, speeding, braking force or hard braking. There is no
   telemetry.
7. "confidence": 0 to 1, how clearly the caption supports BOTH the scenario and the
   verdict.
8. Return one object per input segment, same order, same "segment" number.

Return strict JSON only:
{"segments": [{"segment": <int>, "scenario_id": "<id or none>",
  "verdict": "handled_well|coachable|none", "severity": <1-3 or 0 for none>,
  "confidence": <0-1>, "evidence_quote": "<exact words or empty>",
  "what_happened": "<sentences or empty>"}]}
```

User message: `json.dumps({"segments": [{"segment": 1, "start_sec": 0.0, "caption": "...", "object_counts": {"car": 13, "person": 1}}, ...]}, ensure_ascii=False)`.

### 4.5 Coach prompt

System:

```
You are Dashi, a calm driving coach on the rideshare driver's side. Write ONE sentence to
the driver in second person about this moment.
- If verdict is handled_well: say what they did right, using only the facts in
  "what_happened" and the playbook's "handled_well_when".
- If verdict is coachable: restate the playbook "tip" adapted to this moment. Do not add
  any advice that is not in the tip.
Warm, never punitive. No numbers, no speed, no braking claims. At most 30 words.
Return strict JSON: {"sentence": "<text>"}
```

User: `json.dumps({"verdict", "scenario_title", "what_happened", "handled_well_when", "tip"})`.
Use `max_tokens=120`, `timeout=30`. On any exception, use the fallback from 4.3.8.

### 4.6 `analyze.py` CLI

```
python analyze.py --trips trips.json --out moments.json [--trip T-1041] [--no-weave] [--no-cache]
python analyze.py --chunks ../candidates.txt --out ../work/candidates_review.json      # candidate scan
python analyze.py --assign ../work/candidates_review.json --trips trips.json            # writes trips.json roles
```

- At start, unless `--no-weave` is passed:
  `import weave; weave.init(f"{clients.setting('WANDB_TEAM')}/{clients.setting('WANDB_PROJECT')}")`
  inside `try`. Print one line on failure and continue.
- Run trips with `ThreadPoolExecutor(max_workers=4)`.
- **`--chunks` mode** turns each line into a pseudo-trip:
  `{"trip_id": f"C-{i:02d}", "original_video": ov, "story_role": None}`. It writes the
  normal output shape.
- **`--trip T-xxxx`** re-reviews one trip and replaces only its trip and moments in the
  existing `--out` file.
- Output file: `{"generated_at": utc iso Z, "model": clients.MODEL, "simulated_fields": [...], "driver": ..., "trips": [...], "moments": [...]}`.
  `driver` and `simulated_fields` come from `trips.json`. Do **not** write a `"sample"`
  key; its absence removes the sample banner.
- Print a summary table: trip_id, filename (last 40 characters), role, rating, hw, co,
  max coachable severity, score, mismatch.
- Also print the validation drop counts.

**`--assign` rules**, deterministic and mapped from `trips.seed.json` `story_roles` (moved
into `app/trips.json`). Process the roles in this order, and never reuse a chunk:

1. `unfair_low_rating` (gets T-1041): chunks with at least 1 handled_well and no coachable
   moment of severity 2 or more. Prefer one with a `pedestrian_yield` handled_well. Then
   prefer the most handled_well moments, then the highest max confidence.
2. `missed_risk` (gets T-1042): chunks with a coachable moment of severity 2 or more.
   Prefer the highest `severity * confidence`.
3. `clean` (gets T-1043): chunks with 0 coachable moments. Prefer at least 1 handled_well.
4. `mixed` (gets T-1044): chunks with at least 1 handled_well and at least 1 coachable
   moment of any severity.
5. `live_demo` (gets T-1045): the best remaining chunk. It is **excluded from
   `moments.json`**; `analyze.py --trips` skips `story_role == "live_demo"`.

The assigner prints which role could not be filled.

### 4.7 `app/trips.json` shape

This is the seed with values filled in:

```json
{
  "about": "SYNTHETIC ratings/comments/routes/driver; video is real pie_cam-3 Toronto dashcam.",
  "driver": {"driver_id": "driver-001", "display_name": "Alex", "city": "Toronto", "rider_rating_avg": 4.71},
  "simulated_fields": ["rider_rating", "rider_comment", "pickup", "dropoff", "driver"],
  "story_roles": { ...copied verbatim from trips.seed.json... },
  "trips": [{"trip_id": "T-1041", "date": "2026-09-28", "start_time": "08:12",
             "pickup": "Kensington Market", "dropoff": "Union Station",
             "original_video": "s3://team-7-vss-chunks/team-7/<chunk>.mp4",
             "story_role": "unfair_low_rating"}, ...]
}
```

Keep the seed's trip ids, dates, times and routes, assigned to roles as listed in 4.6.

### 4.8 Exact fields the existing app reads (do not rename)

The source of each field: `main.py`, `ask.py`, and a grep of `index.html`.

- **Top level:**
  - `driver.display_name` and `driver.rider_rating_avg`
  - `trips`, `moments`, `model`, `generated_at`, `simulated_fields`
  - `sample`: omit it.
- **Trip:**
  - `trip_id`, `date` (YYYY-MM-DD), `start_time` (HH:MM), `pickup`, `dropoff`
  - `original_video` (string), `duration_sec` (30), `story_role`
  - `rider_rating` (int, **never null** in the final file), `rider_comment`
  - `safety_score` (int), `handled_well` (count), `coachable` (count)
  - `rating_mismatch` (`"underrated"`, `"missed_risk"` or `null`), `summary`
- **Moment:**
  - `moment_id` (`T-1041-m1`), `trip_id`, `scenario_id`, `scenario_title`
  - `verdict`, `severity` (int), `confidence` (float)
  - `start_sec`, `end_sec` (floats, trip-relative)
  - `sources` (list of segment URIs), `context_before`, `context_after` (URI or null)
  - `people_detected`, `evidence_quote`, `caption`, `what_happened`
  - `what_you_did_right` (str or null), `safer_next_time` (str or null),
    `why_it_matters`, `verified_by_vlm` (null)
- **Wording:**
  - `what_you_did_right` must be a full sentence ending in `.`. `main.py` builds
    `"New from your 08:12 trip: {what_you_did_right} Nice work."`.
  - `ask.py` uses `what_happened` and `scenario_title.lower()` mid-sentence.

### 4.9 Commands, in order

```sh
cd ~/vast-builders-challenge/dashi/app
cp ../trips.seed.json trips.json   # then edit to the 4.7 shape (driver, simulated_fields, story_roles, trips)
../.venv/bin/python analyze.py --chunks ../candidates.txt --out ../work/candidates_review.json
../.venv/bin/python analyze.py --assign ../work/candidates_review.json --trips trips.json
../.venv/bin/python analyze.py --trips trips.json --out moments.json         # uses cache: same verdicts, fast
../.venv/bin/python -c "import json;d=json.load(open('moments.json'));c={m['moment_id']:m for m in d['moments']};assert all(m['evidence_quote'] in m['caption'] for m in d['moments']);assert all(t['rider_rating'] for t in d['trips']);print(len(d['trips']),'trips',len(d['moments']),'moments')"
```

If the candidate scan leaves roles unfilled, take the next 10 chunks from
`discovery_hits.json` (append them to `candidates.txt`) and scan again. This should take
about 3 minutes. Prefer chunks whose hits are `following_distance`, `cyclist_nearby` or
`pedestrian_yield`.

Acceptance (tier 1):

- 4 trips are in `moments.json`.
- At least 1 handled_well and at least 1 coachable moment.
- Every `evidence_quote` is a substring of its `caption`.
- No `"sample"` key.
- T-1041 has `rating_mismatch == "underrated"`.
- Ideally T-1042 has `"missed_risk"`.
- `app/` stays under 1 MiB (`du -cb app/*.* | tail -1`).

### HUMAN DECISION D4 (only if roles are unfilled at 10:38)

Show the table. Options:

- (a) Ship the trips that are filled, with 3 trips, dropping `missed_risk` or `mixed`.
- (b) Use the 2-chunk `original_videos` fallback for `mixed`.
- (c) Assign the closest chunk to `missed_risk` with its real verdicts. Its badge will
  then not show; that is honest.

Never edit verdicts by hand, never lower `CONF_MIN`, never fabricate a coachable moment.
Recommended: (a) if `underrated` exists, because it is the core demo beat.

---

## 5. Step 5: local check, redeploy, demo path (10:38-10:48)

```sh
cd ~/vast-builders-challenge/dashi/app && DASHI_LOCAL=1 PORT=8090 ../.venv/bin/python main.py &   # note the PID
curl -s localhost:8090/ds/home | head -c 600
curl -s localhost:8090/ds/trips | python3 -m json.tool | head -40
curl -s -X POST localhost:8090/ds/ask -H 'Content-Type: application/json' -d '{"message":"Help me improve my reviews"}'
curl -s -X POST localhost:8090/ds/trips/T-1041/evidence -H 'Content-Type: application/json' -d '{}' | head -c 400
kill <PID>
cd ~/vast-builders-challenge/dashi && KUBECONFIG=/config/team-7-k8s.yaml deploy/deploy.sh code
sleep 15; curl -s http://video-lab-team-7.cosmos.vastdata.com/app/health
curl -s http://video-lab-team-7.cosmos.vastdata.com/app/ds/home | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['sample'],d['model'],d['totals'])"
```

Acceptance:

- `sample` is `False`.
- The "Help me improve my reviews" answer names the 3-star trip and offers "Send evidence
  for a rating review".
- The local and public responses match.
- Open the public URL in the browser and click through the demo path (section 8). One clip
  must play.

`ConfigMap` note: `--from-file=app/` takes only top-level files, so `app/__pycache__` is
ignored. Do not add subfolders.

### HUMAN DECISION D3 (10:38, send while redeploying)

Vaishnav relays to the teammates:

- **To Teammate 1:** the moment list (moment_id, trip, timestamp, verdict, segment
  filename) printed by:

  ```sh
  python -c "import json;[print(m['moment_id'],m['start_sec'],m['verdict'],m['scenario_id'],m['sources'][0].split('/')[-1]) for m in json.load(open('app/moments.json'))['moments']]"
  ```

  Ask them to watch each clip and report agree or disagree. A moment that a human
  disagrees with stays in, but Vaishnav must decide whether to keep it in the demo path.
  Tier 1 needs one handled_well and one coachable that a human agrees with.
- **To Teammate 2:** the eval sheet from step 6.1, if their own labels are not ready yet.

---

## 6. Step 6: eval with Weave (10:48-10:58)

### 6.1 `eval/make_sheet.py`

- Write `eval/sheet.md` with 12 segments from the 4 trips:
  - 6 flagged: the first source of each moment, topped up from moments with more sources;
  - 6 not flagged: segments in the same chunks that no moment covers.
- For each row print `source`, the segment filename, the trip and timestamp, the first 200
  characters of the caption, and the labelling instruction: "Watch the clip in the VSS UI
  (search the filename) or the Dashi app; label from the VIDEO not the caption".
- No tokens or links with tokens go in the file.

Run it:

```sh
cd ~/vast-builders-challenge/dashi/app && ../.venv/bin/python ../eval/make_sheet.py
```

### 6.2 `eval/labels.json` (owned by Teammate 2)

Shape: `[{"source": "s3://team-7-vss-chunks-segments/segments/<...>_segment_00N_of_006.mp4", "expected_scenario": "<enabled id or none>", "expected_verdict": "handled_well|coachable|none"}]`.

They may label their own clips or the sheet's clips; any `pie_cam-3` segment works.

**HUMAN DECISION D5:** if Teammate 2 sends values in chat rather than pushing, Vaishnav
approves the implementer writing `eval/labels.json` from them verbatim.

### 6.3 `eval/run_eval.py`

1. `sys.path.insert(0, "<dashi>/app")`, then import `core`, `clients`, `weave`, `asyncio`.
2. `weave.init(f"{clients.setting('WANDB_TEAM')}/{clients.setting('WANDB_PROJECT')}")`.
3. Build the rows.
   - For each label, get the caption from `captions_before.json`, else from
     `vss.get("tools/segments", original_video=ov)`. Find the segment whose `source` equals
     the label source.
   - Derive `ov` from the filename: strip `_segment_\d+_of_\d+`, then
     `s3://{S3_CHUNKS_BUCKET}/{USERNAME}/<chunk>.mp4`.
   - Row: `{"source", "caption", "counts", "segment", "start_sec", "expected_scenario", "expected_verdict"}`.
4. Model, decorated with `@weave.op`:

   ```python
   def dashi_classifier(caption, counts, segment, start_sec, source) -> dict
   ```

   - Build the same seg dict as `gather`, call `core.classify_batch([seg], pb)` (no cache
     write is fine), then `core.validate`.
   - Return `{"scenario_id", "verdict", "confidence", "evidence_quote", "what_happened"}`.
   - If validation dropped the item, or it was none, return `scenario_id="none"`,
     `verdict="none"`.
5. Scorers, each decorated with `@weave.op` (recent Weave uses the parameter name
   `output`):
   - `scenario_match(expected_scenario, output) -> {"correct": output["scenario_id"] == expected_scenario}`
   - `verdict_match(expected_verdict, output) -> {"correct": output["verdict"] == expected_verdict}`
   - `false_alarm(expected_scenario, output) -> {"false_alarm": expected_scenario == "none" and output["scenario_id"] != "none"}`
   - `grounded(caption, output)`: if `output["verdict"] == "none"`, return
     `{"grounded": None}`. Otherwise make one LLM judge call (temperature 0, JSON) with
     the system prompt: `Does the STATEMENT state only facts that are present in the CAPTION? Answer strict JSON {"grounded": true|false, "reason": "<one sentence>"}.`
     The user content is `json.dumps({"CAPTION": caption, "STATEMENT": output["what_happened"]})`.
6. `asyncio.run(weave.Evaluation(name="dashi-classifier", dataset=rows, scorers=[...]).evaluate(dashi_classifier))`.
7. Also compute the numbers **locally**: run the model and scorers once in a plain loop
   (or reuse the evaluation output) so `results.md` does not depend on parsing Weave
   summaries. Report:
   - n;
   - scenario accuracy;
   - verdict accuracy;
   - false-alarm rate = false alarms / rows labelled none;
   - groundedness = grounded / flagged rows;
   - the model id;
   - the Weave project URL `https://wandb.ai/{WANDB_TEAM}/{WANDB_PROJECT}/weave`, plus the
     evaluation link that Weave prints.
8. Write `eval/results.md`: method (3 lines), a numbers table, the per-row table (filename,
   expected, predicted, confidence), and the line "Measured on n hand-labelled clips;
   labels from watching video, predictions from captions only." Report low numbers as they
   are.
9. If the re-ingest chunk has labelled segments, also run those rows with
   `captions_after.json` captions and report before/after. Otherwise write "Before/after
   eval: not run (re-ingested chunk not in labels)".

Command:

```sh
cd ~/vast-builders-challenge/dashi/app && ../.venv/bin/python ../eval/run_eval.py
```

Acceptance: `eval/results.md` has real numbers and n, and the Weave UI shows the evaluation.
Cut at 10:58: if there are no labels by 10:52, write `results.md` saying "eval harness ready;
labels not completed in time" and give Teammate 1 that wording. Never invent labels.

Optional 1-line fix while waiting (step 6 or 7): in `app/ask.py`
`find_in_my_footage`, change `"llm_top_n": 0` to `"llm_top_n": 1`. No route calls it, so
this does not need a redeploy; it goes out with the freeze redeploy.

---

## 7. Step 7: README handover + push (10:58-11:02)

Teammate 1 writes `README.md` (brief section 12). The implementer posts this fact sheet to
Vaishnav (paste it into chat, and also save it as `dashi/HANDOVER.md`):

- **What it does (40 words):** a draft based on brief section 1.
- **Who it is for:** rideshare drivers, rating disputes, coaching.
- **Architecture:** the diagram from brief section 4, with the real files `core.py`,
  `analyze.py`, `main.py`, `ask.py`, `index.html` and `clients.py`.
- **Sponsor tools and what each does here:**
  - VAST: DataEngine pipeline, VastDB hybrid search via `/search`, S3 clips via
    `/videos/stream`.
  - NVIDIA: Cosmos Reason captions; the custom prompt was used on 1 chunk, if done.
    Cosmos Embed powers search; YOLO `object_counts` feeds `people_detected`.
  - CoreWeave / W&B: model id `clients.MODEL` for classify, coach and Ask; Weave traces
    and the eval.
  - Cursor: how it was built.
- **Inputs:**
  - camera `pie_cam-3` (Toronto research dashcam standing in for rideshare trips);
  - the list of chunk filenames per trip;
  - `reingest_prompt.txt` (737 characters);
  - `playbook.json`, with the enabled scenarios and why the others were disabled (from
    `discovery.md`);
  - `trips.json` (synthetic ratings).
- **Outputs:** the `moments.json` schema (section 4.8), and the app URL
  http://video-lab-team-7.cosmos.vastdata.com/app/ (event network only).
- **Reproduce:** the venv setup from `PLAN.md`, `discover.py`, the three `analyze.py`
  commands from 4.9, `make_sheet.py`, `run_eval.py`, `deploy/deploy.sh`.
- **Evaluation:** the numbers from `eval/results.md` and the Weave URL.
- **Discovery numbers:** convincing hits per scenario, and the caption-wording stats.
- **Before/after caption pair** (if re-ingest was done).
- **Validation stats:** the number of LLM outputs dropped for a non-verbatim quote or low
  confidence. This is good evidence of a grounded pipeline.
- **Limitations:**
  - synthetic ratings, comments, routes and driver;
  - research footage standing in for rideshare trips;
  - no telemetry, so no speed or braking claims;
  - AI verdicts are suggestions, not findings of fault;
  - trips are 30 s chunks;
  - the JWT is in clip URLs;
  - caption-only classification (the VLM does not verify; `verified_by_vlm` is null);
  - lessons-done state is in memory.
- **Next steps for the pitch:** live `/ds/analyze`, Cosmos Reason verification, the rider
  "Let your rider know" loop, re-ingest of all trips with the custom prompt, and a
  post-trained classifier.

Commit and push (Vaishnav approves the commit at freeze; the implementer runs it):

```sh
cd ~/vast-builders-challenge/dashi && git pull --rebase
git add discover.py discovery.md discovery_hits.json candidates.txt captions_before.json \
  captions_after.json playbook.json app/core.py app/analyze.py app/trips.json app/moments.json \
  app/playbook.json app/ask.py eval/make_sheet.py eval/run_eval.py eval/results.md eval/sheet.md \
  work/classify_cache.json HANDOVER.md NEXT_STEPS.md
git status --short    # check: no *.config, no tokens, no .env
git commit -m "Pipeline: discovery, core/analyze, real moments.json, eval" && git push
```

`git add` errors on a missing path such as `captions_after.json`. Drop that path from the
list. Do not stage `eval/labels.json`
unless Teammate 2 asked you to write it.

---

## 8. Step 8: freeze checklist (11:02-11:05)

1. `git status` is clean and `git log origin/main -1` equals local.
2. Do a clean redeploy from the pushed tree:
   `cd ~/vast-builders-challenge/dashi && KUBECONFIG=/config/team-7-k8s.yaml deploy/deploy.sh code`.
   Wait 15 s, then `curl .../app/health`.
3. Demo path on the public URL, in a fresh browser tab with no fixing:
   1. Coach: tap the chip **Help me improve my reviews**. The answer names the 3-star
      T-1041 and shows the clip card.
   2. Open the **underrated trip** T-1041 ("Rating doesn't match the video" badge). The
      handled_well moment plays and the evidence quote shows.
   3. Tap **Send evidence for rating review**, then **Send (simulated)**. A reference
      `RR-xxxxxx` appears.
   4. Trips: open the **missed_risk trip** T-1042 ("Rider missed this"). The coachable
      moment shows "How it could be safer".
   5. Learn: the lesson for that scenario shows the driver's own clip. Tap **Mark as
      learned**; the counter goes up.
4. If any step fails, the fallback is to say it plainly in the demo and use Teammate 2's
   backup recording. Do not live-patch after 11:05.
5. `SUBMISSION.md` (Teammate 1) uses the `submission` skill at
   `~/vast-builders-challenge/.cursor/skills/submission/SKILL.md`:
   - team number from `$USERNAME` (team-7);
   - a description of 40 words or fewer;
   - the stack list;
   - the code link (Cursor repo `vaishnav-ajai/dashi`: **HUMAN DECISION D6**, confirm the
     judges can open it);
   - the live app URL;
   - feedback.

   No personal details. Do not commit it unless asked.

---

## 9. Human decision points (in order)

| # | When | Question | Default if silent |
|---|---|---|---|
| D1 | ~10:15 | Confirm the enabled scenarios and the 12 candidate chunks; add Teammate 2's filenames | Proceed as printed |
| D2 | ~10:16 | Re-ingest one non-trip chunk with `reingest_prompt.txt`, keeping the metadata? | Skip if no answer by 10:20 |
| D3 | ~10:38 | Relay the moment list to Teammate 1 (agree/disagree) and the eval sheet to Teammate 2; decide whether a disputed moment stays in the demo path | Keep it, but avoid it in the demo |
| D4 | ~10:38, only if roles are unfilled | Ship 3 trips / use the 2-chunk mixed fallback / assign the closest chunk honestly | (a) ship the filled trips |
| D5 | ~10:50 | OK to write `eval/labels.json` from Teammate 2's chat message? | Wait; do not invent |
| D6 | ~11:00 | Commit + push now; confirm the repo link judges can open | Push |

## 10. Risks and fallbacks

- **Captions rarely say what the camera car does, so there are few or no coachable
  moments.** This is the most likely problem.
  - Scan 10 more candidates, favouring `following_distance` and `cyclist_nearby` hits.
  - Then go to D4.
  - Never lower `CONF_MIN`, edit verdicts, or relax the exact-quote check. In the README,
    say that the measured eval shows this limit.
- **The LLM returns quotes that are not verbatim**, so many drops. Print the drop counts.
  If more than 50% are `bad_quote`, add one sentence to rule 4 ("The quote will be checked
  by exact string match; if unsure, copy a whole sentence from the caption") and rerun
  with `--no-cache`. Prompt changes alter the cache key automatically.
- **Reruns change verdicts and break role assignment.** The classifier cache in
  `work/classify_cache.json` prevents this. Never use `--no-cache` after `--assign`.
- **`/search` 422.** Use `llm_top_n` of at least 1. Searches are slow (about 6 s), so use
  4 threads.
- **Weave install or init fails.** `analyze.py --no-weave` still works. `run_eval.py` falls
  back to the local loop and writes `results.md` without a Weave link; say "Weave
  unavailable" in it.
- **W&B is slow or rate-limited.** Use 4 threads, at most 1 retry, and a 60 s timeout. The
  cache keeps finished batches.
- **The pod restart serves errors for ~15 s** while pip runs. Wait, then curl
  `/app/health`. If the rollout hangs for more than 2 minutes, run
  `kubectl -n team-7 logs deploy/dashi --tail=50` with `KUBECONFIG=/config/team-7-k8s.yaml`.
  If it is still broken at 11:00, `git stash` the data, redeploy, and demo the
  sample-labelled app with the backup video. Last resort only.
- **A clip will not play.** The UI already shows the caption instead. Also check that the
  `sources` URIs come from `/tools/segments` unchanged.
- **The re-ingest is slow or fails.** It is not on the critical path. Report its status
  and never start a second one.
- **`app/` passes 1 MiB.** `moments.json` should be under 100 KB. Never copy
  `captions_before.json` into `app/`.
- **Secrets.** `.gitignore` already excludes `*.config`, `*-k8s.yaml`, `*secret*.yaml` and
  `.env`. Never print the token that `stream_path` returns.
