# Dashi eval sheet

Watch the clip in the VSS UI (search the filename) or the Dashi app; label from the VIDEO not the caption.
For each row write `expected_scenario` (one of: pedestrian_yield, curb_crowd, stopped_in_lane, cyclist_nearby, poor_conditions, or none) and `expected_verdict` (handled_well, coachable or none) into `eval/labels.json`.

| # | flagged | trip | time | segment file | caption (first 200 chars) |
|---|---|---|---|---|---|
| 1 | yes | T-1041 | 0-5 s | `20261001_071651_set06_video_chunk_0015_segment_001_of_006.mp4` | The scene is captured from a vehicle’s dashboard camera, showing a street intersection under a partly cloudy sky. The road surface is dry asphalt with painted lane markings. On the right side of the f |
| 2 | yes | T-1041 | 15-20 s | `20261001_071651_set06_video_chunk_0015_segment_004_of_006.mp4` | The scene is captured from a vehicle’s dashboard camera, showing a road intersection under a partly cloudy sky. The road surface is dry and marked with white lane lines. A person wearing a bright yell |
| 3 | yes | T-1041 | 20-25 s | `20261001_071651_set06_video_chunk_0015_segment_005_of_006.mp4` | The scene is captured from a vehicle stopped at an intersection on a partly cloudy day. A traffic officer in a high-visibility yellow jacket and dark cap stands on the right side of the road, directin |
| 4 | yes | T-1042 | 20-25 s | `20261001_065754_set05_video_chunk_0000_segment_005_of_006.mp4` | The camera vehicle is in the left lane of a two-lane road, approaching an intersection. It is moving forward slowly and preparing to turn left. The traffic light ahead is red. A pedestrian is crossing |
| 5 | yes | T-1042 | 25-30 s | `20261001_065754_set05_video_chunk_0000_segment_006_of_006.mp4` | The camera vehicle is stopped at an intersection with a green traffic light. A pedestrian wearing a backpack is crossing the street in front of the vehicle. The vehicle then begins to move forward and |
| 6 | yes | T-1043 | 0-5 s | `20261001_071510_set06_video_chunk_0011_segment_001_of_006.mp4` | The scene is captured from a vehicle’s dashboard camera on a narrow, single-lane, one-way street. The road is lined with brick buildings on both sides, and overhead power lines run along the left side |
| 7 | no | T-1041 | 5-10 s | `20261001_071651_set06_video_chunk_0015_segment_002_of_006.mp4` | A silver SUV drives through an intersection on a two-lane road. A person in a high-visibility yellow jacket stands in the middle of the road, directing traffic. Orange and black striped traffic cones  |
| 8 | no | T-1042 | 0-5 s | `20261001_065754_set05_video_chunk_0000_segment_001_of_006.mp4` | The camera vehicle is stopped on a one-way road with a single lane in each direction. The camera vehicle is positioned behind a black SUV. The camera vehicle is stopped behind a black SUV. The camera  |
| 9 | no | T-1042 | 10-15 s | `20261001_065754_set05_video_chunk_0000_segment_003_of_006.mp4` | The camera vehicle moves forward along a straight city street, remaining in its lane without turning. The traffic light ahead is red, requiring the vehicle to stop. Pedestrians are visible on the side |
| 10 | no | T-1043 | 5-10 s | `20261001_071510_set06_video_chunk_0011_segment_002_of_006.mp4` | The scene is a narrow, one-way urban street with a single lane in each direction. The ego vehicle is traveling behind a dark SUV that is stopped in the middle of the road. A blue sedan is parked on th |
| 11 | no | T-1043 | 15-20 s | `20261001_071510_set06_video_chunk_0011_segment_004_of_006.mp4` | The scene is captured from a vehicle’s dashboard camera, showing a view of a road with a bench visible on the right side. The road is a two-lane street with vehicles traveling in both directions. On t |
| 12 | no | T-1043 | 25-30 s | `20261001_071510_set06_video_chunk_0011_segment_006_of_006.mp4` | The scene is a narrow, one-way street with a single lane in each direction. The sky is overcast with clouds. A dark-colored SUV is stopped in the lane ahead of the camera vehicle, with its brake light |

Sources (for labels.json):

- `s3://team-7-vss-chunks-segments/segments/20261001_071651_set06_video_chunk_0015_segment_001_of_006.mp4`
- `s3://team-7-vss-chunks-segments/segments/20261001_071651_set06_video_chunk_0015_segment_004_of_006.mp4`
- `s3://team-7-vss-chunks-segments/segments/20261001_071651_set06_video_chunk_0015_segment_005_of_006.mp4`
- `s3://team-7-vss-chunks-segments/segments/reingest/f60a4abef5584570ae37fbb8868ba596/20261001_065754_set05_video_chunk_0000_segment_005_of_006.mp4`
- `s3://team-7-vss-chunks-segments/segments/reingest/f60a4abef5584570ae37fbb8868ba596/20261001_065754_set05_video_chunk_0000_segment_006_of_006.mp4`
- `s3://team-7-vss-chunks-segments/segments/20261001_071510_set06_video_chunk_0011_segment_001_of_006.mp4`
- `s3://team-7-vss-chunks-segments/segments/20261001_071651_set06_video_chunk_0015_segment_002_of_006.mp4`
- `s3://team-7-vss-chunks-segments/segments/reingest/f60a4abef5584570ae37fbb8868ba596/20261001_065754_set05_video_chunk_0000_segment_001_of_006.mp4`
- `s3://team-7-vss-chunks-segments/segments/reingest/f60a4abef5584570ae37fbb8868ba596/20261001_065754_set05_video_chunk_0000_segment_003_of_006.mp4`
- `s3://team-7-vss-chunks-segments/segments/20261001_071510_set06_video_chunk_0011_segment_002_of_006.mp4`
- `s3://team-7-vss-chunks-segments/segments/20261001_071510_set06_video_chunk_0011_segment_004_of_006.mp4`
- `s3://team-7-vss-chunks-segments/segments/20261001_071510_set06_video_chunk_0011_segment_006_of_006.mp4`
