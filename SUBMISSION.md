# team-7

## Project
Dashi is a video agent on the rideshare driver's side. It reviews each trip's dashcam footage, shows
the clip as evidence, coaches from a fixed playbook, and offers to send evidence when a low rider
rating doesn't match the video.

**Stack:**
- VAST DataEngine pipeline, VastDB hybrid search (`/search`), `/tools/segments`, S3 clip streaming, re-ingest with a custom prompt
- NVIDIA Cosmos Reason (captions, custom ingest prompt), Cosmos Embed (search), YOLO (object counts)
- CoreWeave / W&B Inference (`deepseek-ai/DeepSeek-V4-Flash`) for classify, coach, ideal-replay prompt and Ask
- W&B Weave for tracing and evaluation
- Python, FastAPI, single-page vanilla JS UI, deployed on Kubernetes from a ConfigMap
- Built with Cursor

**Code:** Cursor repo `vaishnav-ajai/dashi` (access for judges to be confirmed)
**Live app:** http://video-lab-team-7.cosmos.vastdata.com/app/ (event network)
**Supplementary:** Weave project https://wandb.ai/vastdata/team-7/weave; `README.md` and `DEMO.md` in the repo

## Feedback
The stack let us go from footage to a working agent in a day: hybrid search, captions and detections
were all available behind one API. Two specific issues: `POST /search` rejects `llm_top_n: 0` with
HTTP 422, although a skill example uses 0 (we use 1). A re-ingest job's status was lost when the
backend restarted, even though the re-ingest itself completed and the new captions landed. Default
captions rarely describe what the camera vehicle itself does; a custom ingest prompt fixed that, so
surfacing that option earlier would help other teams.
