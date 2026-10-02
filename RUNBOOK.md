# Dashi: team runbook

For the humans. The specification the coding agent follows is `BUILD_BRIEF.md`.

## The idea in one breath

Dashi is a video agent on the rideshare driver's side. It reviews each trip's
dashcam footage, shows the driver what happened with the clip as evidence, coaches them
on how it could be safer, and gives them credit, including evidence to contest a low
rating, when the video shows they drove well.

## Get the files onto the VM

Clone the team repo as described at the end of `PLAN.md`. `PLAN.md` also overrides
this runbook on scope, timing and who owns which file (we are 3 people, not 4).

```sh
cd ~/vast-builders-challenge
agent                                       # start Cursor here, then /model -> Auto
```

Work inside `~/vast-builders-challenge` so Cursor loads the VAST skills.

## Who does what (two VMs, up to four people)

| Person | Seat | Owns |
|--------|------|------|
| A | VM 1 | Discovery, re-ingest, `analyze.py`, `moments.json`. The only person who re-ingests. |
| B | VM 2 | `main.py`, `index.html`, deployment to `/app`. |
| C | With A | Watches clips: confirms moments, labels the 20 eval clips, assigns trip story roles. |
| D | With B | README, submission, demo script, pitch rehearsal, public repo. |

Share code between the two VMs through a Git repository (step 2 below). B can build the
whole app against a hand-made `moments.json` that follows the schema in the brief, and
swap in the real one when A has it.

## Prompts to give Cursor, in order

Paste one at a time. Read what comes back before the next one.

**1. Orient (both VMs)**
```
Read dashi/BUILD_BRIEF.md, dashi/playbook.json and dashi/trips.seed.json
in full. Then run a git pull and check that everything is working (login, dashboard).
Tell me in five lines what you will build and anything in the brief that conflicts
with the skills in .cursor/skills.
```

**2. Repository (person D, once)**
```
Set up Git so both VMs can share the dashi/ folder: I have created an empty public
GitHub repo at <URL>. Add it as a remote named team, make sure no secrets or /config
values are tracked, commit dashi/, and push. Tell me the exact pull command for
my teammate. Do not commit SUBMISSION.md contents that include secrets.
```
(If pushing from the VM is blocked, ask an organiser how teams are expected to publish
code. The submission needs a public code link.)

**3. Discovery (person A). The most important step.**
```
Do Phase 0 of dashi/BUILD_BRIEF.md, steps 1 to 6. Show me the table of dashcam
chunks, the real segment field names, one full caption, and per scenario how many
convincing hits there are with two example captions each. Write dashi/discovery.md.
Do not re-ingest anything yet.
```
Person C: open three or four of the returned clips in the Video Search & Summary UI and
check that the captions match what you see.

**4. Decide and re-ingest (person A)**
```
First save the current captions: dump /tools/segments for every dashcam chunk we may
use to dashi/captions_before.json (re-ingest replaces them). Then, based on
discovery.md: do the captions describe what the camera vehicle itself does
(slows, stops, yields, pulls over)? Show me three captions that do and three that do
not. Then re-ingest ONE dashcam chunk using the custom prompt in
dashi/reingest_prompt.txt, keeping the original metadata. Wait for it to finish and
show me the same segments' captions before and after, side by side.
```
If the new captions are clearly better, re-ingest the other chosen chunks (four or five
in total, not the whole archive). If the old captions are already good, skip re-ingest
and say so in the README. Save two before/after pairs for the demo.

**5. Pick the trips (persons A and C)**
```
Update playbook.json: disable scenarios with fewer than three convincing hits. Create
dashi/app/trips.json from trips.seed.json, filling original_video with the four or
five dashcam chunks that have the most scenario hits. Leave story_role unassigned.
```

**6. The review pipeline (person A)**
```
Build dashi/app/core.py and analyze.py as specified in sections 5 and the LLM
client part of BUILD_BRIEF.md (stages 1 to 5). List the W&B inference models, pick one
that returns clean JSON and tell me which. Trace every LLM call with Weave. Run it on
one trip first and show me every moment it found with caption, verdict and clip link.
```
Person C watches each moment's clip and says agree or disagree. Tune the classifier
prompt until the moments are right, then run all trips. Then:
```
Assign story_role to each trip using the assign_to rules in trips.seed.json and what
the analysis found. Show me your assignment and the reason for each before writing it.
Re-run analyze.py and write dashi/app/moments.json.
```

**7. The app (person B, can start right after prompt 1)**
```
Build dashi/app/main.py and index.html as specified in sections 6, 7 (tier 1 only)
and 8 of BUILD_BRIEF.md. Start from a small hand-written moments.json that follows the
schema so the UI can be built before the real analysis exists. Run it locally on the VM
and tell me the URL. The UI should look like a polished driver phone app: calm, large
type, green for handled well, amber for coachable, no red alarm styling.
```

**8. Deploy (person B)**
```
Deploy dashi/app to Kubernetes with the deploy-app-no-registry skill, following
section 10 of BUILD_BRIEF.md, including the W&B variables in the Secret. Verify
/app/health and that /app/ loads, a clip plays, and a chip answers. Also check from
inside the pod that https://api.inference.wandb.ai/v1/models is reachable. Give me the URL.
```

**9. Evaluation (persons C and A)**
```
Build dashi/eval as specified in section 9 of BUILD_BRIEF.md. Generate the sheet
of 20 clips for me to label.
```
Label them from the video, then:
```
Run the eval with Weave, write eval/results.md, and add the numbers to the README.
Give me the Weave link for the evaluation.
```

**10. Tier 2 features (person B)**
```
Add the tier 2 items from section 11 of BUILD_BRIEF.md, in order: evidence packet, live
review of one trip with visible stages, free-text Ask. Redeploy after each and verify.
```

**11. README and submission (person D)**
```
Write dashi/README.md with every item in section 12 of BUILD_BRIEF.md, using the
real numbers and the real model id. Then help me submit our project.
```

## Stop building 45 minutes before the deadline

Use that time to: redeploy from clean and click through the whole demo twice, push the
code, record a screen capture of the demo as a backup, finish `SUBMISSION.md`.

## If something goes wrong

| Problem | What to do |
|---------|------------|
| The dashcam has no curb or stopped-in-lane moments | Lead with pedestrian yielding, following distance and turns, which this footage is strong on. Keep "crowded curb" only if discovery found real clips. |
| Captions do not say what the camera vehicle does | Re-ingest with the custom prompt. If still weak, add the tier 3 Cosmos Reason check for the few demo moments. |
| The classifier flags too much | Raise the confidence cut to 0.7 and require the evidence quote. Fewer, correct moments beat many doubtful ones. |
| The LLM is slow or rate-limited | The app serves from `moments.json`, so the demo still works. Ask the W&B team for credits. |
| Deployment fails | Ask Cursor to run `/ask-cosmos` and post the note. Keep the local run as a rehearsal fallback only. |
| Clip will not play | Check the token is fresh (re-login on 401) and the `source` is URL-encoded. |

## Three-minute demo

| Time | Say | Show |
|------|-----|------|
| 0:00 | "A rideshare driver's rating comes from the back seat. The rider felt a hard brake. They did not see why. And sensor-based scoring knows the car stopped, not what was in front of it." | Title slide or the Coach tab |
| 0:25 | "Dashi is an agent on the driver's side. It reviews every trip's dashcam video on VAST." | Coach tab: rider rating next to safety score |
| 0:40 | "Alex got three stars on this trip. Alex asks:" tap **Help me improve my reviews** | The answer: trip, rating, clip card |
| 1:00 | "The video shows a pedestrian stepping out and Alex yielding early. Handled well. That rating was not on Alex, and the agent can send the evidence." | Play the clip, verdict chip, evidence packet |
| 1:30 | "This five-star trip is the opposite. The rider was happy, and the video shows something to fix." | Trips tab: "Rider missed this" badge, then the moment |
| 1:50 | "What happened, and how it could be safer, from our playbook, with Alex's own clip." | The two columns, then the Learn card, tap Got it |
| 2:10 | "How it works: we re-ingested the footage with our own prompt so Cosmos Reason describes what the driver's car does. Cosmos Embed and VastDB find the moments, YOLO counts the people, and an agent on Weights & Biases inference turns them into coaching." | Architecture slide, before/after caption |
| 2:35 | "We checked it against clips we labelled by hand: it agreed on N of 20." | Weave evaluation page |
| 2:50 | "Next: live trips, fused with telematics, and safe-driving rewards. Dashi: your record should reflect how you drove." | Coach tab |

Say out loud that the ratings are simulated and the footage is a public research
dashcam set standing in for a driver's trips. Judges trust a demo more when its limits
are stated.

## How this maps to the judging criteria

| Criterion | What we show |
|-----------|--------------|
| Idea | Video search and summary used for something riders and sensors cannot do: explain why. |
| Technical implementation | README with inputs, outputs and reproduce steps; a cached, re-runnable pipeline; a measured eval. |
| Design | One driver-app column, evidence on every card, calm coaching tone. |
| Impact (3+ sponsor tools) | VAST pipeline and VastDB search; NVIDIA Cosmos Reason, Cosmos Embed and YOLO; W&B inference and Weave; built with Cursor. |
| Presentation | The script above, rehearsed twice, with a recorded backup. |
