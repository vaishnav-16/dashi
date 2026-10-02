# Dashi: 3-minute demo script

Live app: http://video-lab-team-7.cosmos.vastdata.com/app/ (event network only).

Before you start: open the app once so the first page load and clips are warm. Use trips T-1041 and
T-1042 only. **Avoid trip T-1044**: its simulated rider comment ("Drop-off was a bit rushed") contradicts
its video, which shows only handled-well moments.

Say out loud, once: ratings, comments, routes and the driver are simulated; the footage is a
Toronto dashcam research set standing in for a driver's trips.

| Time | Say | Show |
|---|---|---|
| 0:00 | "A rideshare rating comes from the back seat. The rider felt a hard stop and didn't see why. Sensor scoring knows the car stopped, not what was in front of it. Dashi is a video agent on the driver's side." | Coach tab: simulated rider rating next to the Dashi safety score |
| 0:15 | "It works two ways. First, proactively: after each trip is reviewed, Dashi posts cards without being asked. Here's a kudos card for a moment Alex handled well." | Coach tab: kudos card; tap it to open the moment |
| 0:30 | "On Learn, it turns Alex's own clip into a short lesson. Alex watches it and marks it learned." | Learn tab: lesson card with the driver's own clip, tap **Mark as learned**, counter updates |
| 0:45 | "Second, Alex can just ask, in plain English." | Coach tab: type **Help me improve my rating**, send |
| 0:55 | "Dashi finds the 3-star trip, T-1041 at 8:12, Kensington Market to Union Station, and the video shows Alex yielding to pedestrians. Handled well. That rating wasn't on Alex." | Answer with the clip card; open the trip; play moment **T-1041-m3** (pedestrians crossing, handled well) |
| 1:15 | "So Dashi offers to send the evidence for a rating review." | Tap **Send evidence for rating review**, then **Send (simulated)**: an `RR-` reference appears |
| 1:30 | "This trip is the opposite: five stars, T-1042 at 17:40, Yonge-Dundas Square to The Annex. The rider was happy, but the video shows something to fix." | Trips tab: T-1042 with the **Rider missed this** badge; open it |
| 1:40 | "Alex turned left while a pedestrian was still crossing. What happened, and a better way, from our playbook, with Alex's own clip." | Coachable moment **T-1042-m2**: play the clip, then the **A better way** column and the caption quote as evidence |
| 1:55 | "And as a stretch: Dashi writes a prompt for a video generation model, Cosmos Predict or Transfer style, showing how this moment should have been driven. No generation model is in the event stack, so we show the prompt, not a video." | Expand **✦ Ideal replay** on the moment card |
| 2:10 | "Ask also searches the footage live. Any question that doesn't match a topic runs a VAST hybrid search over Alex's dashcam video and answers with the trip and timestamp." | Coach tab: type **show me pedestrians crossing in front of me**; show the answer with trip and timestamp |
| 2:25 | "Under the hood: VAST DataEngine and VastDB search over the video; NVIDIA Cosmos Reason writes the captions, through our own prompt so it describes what the driver's car does; Cosmos Embed powers search; YOLO counts people. DeepSeek on W&B Inference on CoreWeave does the coaching, Weave traces it, and we built it with Cursor. The one coachable moment in 22 chunks came from a chunk we re-ingested with our prompt." | Architecture diagram in the README; before/after caption table |
| 2:45 | "We checked the classifier against clips we labelled by watching the video." | Weave project https://wandb.ai/vastdata/team-7/weave and `eval/results.md` (read the measured numbers from there; do not quote numbers that are not in it) |
| 2:55 | "Dashi: your record should reflect how you drove." | Coach tab |

## If something fails

- **A clip doesn't play:** the moment card shows the caption instead. Read the evidence quote aloud and
  move on.
- **An Ask answer is slow or the LLM is down:** the app returns a templated answer from the same data
  after 8 seconds. Keep talking through it.
- **The free-text search returns nothing:** say that live search runs over the driver's four trips, then
  move on to the architecture.
- **The app doesn't load at all:** switch to the backup screen recording of this same path.
