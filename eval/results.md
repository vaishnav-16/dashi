# Dashi eval results

Method: each 5 s segment was labelled for scenario and verdict from the video, by Cursor agent from 4 video frames per clip (not a human).
The classifier (same prompt, validation and confidence floor as the app pipeline) saw only the caption and YOLO counts.
Groundedness is an LLM judge checking that `what_happened` states only facts in the caption.

| metric | value |
|---|---|
| n (labelled segments) | 12 |
| scenario accuracy | 83% |
| verdict accuracy | 100% |
| false-alarm rate (of 5 labelled none) | 0% |
| groundedness (of 7 flagged) | 43% |
| model | `deepseek-ai/DeepSeek-V4-Flash` |

Weave project: https://wandb.ai/vastdata/team-7/weave (evaluation `dashi-classifier`).

| segment | expected | predicted | confidence |
|---|---|---|---|
| `20261001_071651_set06_video_chunk_0015_segment_001_of_006.mp4` | poor_conditions / handled_well | poor_conditions / handled_well | 0.85 |
| `20261001_071651_set06_video_chunk_0015_segment_004_of_006.mp4` | pedestrian_yield / handled_well | poor_conditions / handled_well | 0.85 |
| `20261001_071651_set06_video_chunk_0015_segment_005_of_006.mp4` | poor_conditions / handled_well | pedestrian_yield / handled_well | 0.90 |
| `20261001_065754_set05_video_chunk_0000_segment_005_of_006.mp4` | pedestrian_yield / handled_well | pedestrian_yield / handled_well | 0.95 |
| `20261001_065754_set05_video_chunk_0000_segment_006_of_006.mp4` | pedestrian_yield / coachable | pedestrian_yield / coachable | 0.90 |
| `20261001_071510_set06_video_chunk_0011_segment_001_of_006.mp4` | pedestrian_yield / handled_well | pedestrian_yield / handled_well | 0.90 |
| `20261001_071651_set06_video_chunk_0015_segment_002_of_006.mp4` | poor_conditions / handled_well | poor_conditions / handled_well | 0.85 |
| `20261001_065754_set05_video_chunk_0000_segment_001_of_006.mp4` | none / none | none / none | 0.00 |
| `20261001_065754_set05_video_chunk_0000_segment_003_of_006.mp4` | none / none | none / none | 0.00 |
| `20261001_071510_set06_video_chunk_0011_segment_002_of_006.mp4` | none / none | none / none | 0.00 |
| `20261001_071510_set06_video_chunk_0011_segment_004_of_006.mp4` | none / none | none / none | 0.00 |
| `20261001_071510_set06_video_chunk_0011_segment_006_of_006.mp4` | none / none | none / none | 0.00 |

Measured on 12 labelled clips; labels from the video, predictions from captions only.
Labeller: Cursor agent from 4 video frames per clip (not a human). A human review of these labels is still needed; treat the numbers as indicative.

Before/after eval: not run (re-ingested chunk not in labels).
