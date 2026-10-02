# Dashi discovery

## Footage

- `camera_id`: `pie_cam-3` (Toronto dashcam research set standing in for rideshare trips).
- Chunks per set: set01 30, set02 30, set03 30, set04 30, set05 30, set06 30 (total 180).
- Every chunk is 30 s, split into 6 segments of 5 s.

## Real field names (`/tools/segments`)

- clip URI `source`, caption `reasoning_content`, timing `segment_start_sec` / `segment_end_sec`,
  order `segment_number`, YOLO `object_classes` / `object_counts` (JSON string).
- `POST /search` rejects `llm_top_n: 0` with HTTP 422; we use `llm_top_n: 1`.
- All segment fields: `cached_prompt_tokens`, `camera_id`, `capture_type`, `cosmos_model`, `detection_count`, `detection_frame_count`, `detection_sidecar_uri`, `duration`, `filename`, `is_public`, `location`, `object_classes`, `object_counts`, `original_video`, `perception_ok`, `perception_source`, `reasoning_content`, `segment_end_sec`, `segment_number`, `segment_start_sec`, `source`, `tags`, `tokens_used`, `total_segments`, `upload_timestamp`.

## Scenarios

A hit is *convincing* when the caption, after dropping negated sentences ("No pedestrians ..."),
matches the scenario's keyword regexes. Similarity scores alone (0.3 to 0.4) do not separate good hits.

### `pedestrian_yield`: Pedestrians crossing ahead (enabled)

- Queries: "pedestrian crossing the road in front of the vehicle"; "person stepping off the curb into the roadway ahead of the car"
- Hits: 19, convincing: 12
- Example `20261001_072246_set06_video_chunk_0029_segment_004_of_006.mp4` (score 0.3888): "The scene is captured from a vehicle stopped at an intersection on a partly cloudy day. The road is a two-way street with a single lane in each direction, and the vehicle is positioned at the intersection, waiting for pedestrians to cross. There are no traffic lights or stop signs visible in the imm"
- Example `20261001_070645_set05_video_chunk_0021_segment_005_of_006.mp4` (score 0.365): "The scene is a residential street intersection under a partly cloudy sky. The road has a single lane in each direction with a yellow center line. A stop sign is visible on the right side of the intersection. A beige minivan is stopped at the intersection, facing away from the camera. Two pedestrians"

### `curb_crowd`: Crowded curb (enabled)

- Queries: "group of pedestrians crowding the curb or sidewalk edge next to traffic"; "people standing in the road near parked cars"
- Hits: 18, convincing: 4
- Example `20261001_065150_set04_video_chunk_0016_segment_005_of_006.mp4` (score 0.2922): "The scene is a city street with a red traffic light ahead. A white SUV is stopped directly in front of the camera vehicle, with its brake lights illuminated. To the left of the SUV, a white sedan is also stopped. On the right side of the road, a group of pedestrians is standing on the sidewalk near "
- Example `20261001_065358_set04_video_chunk_0021_segment_005_of_006.mp4` (score 0.2875): "The scene unfolds on a narrow, busy urban street lined with parked cars on both sides. The road surface is dry and appears to be a single-lane, two-way street with no visible lane markings. A silver SUV is directly ahead of the camera vehicle, moving forward at a slow pace. To the right, a group of "

### `stopped_in_lane`: Stopping in the middle of the road (enabled)

- Queries: "vehicle stopped in the travel lane with traffic passing around it"; "car double parked blocking a lane"
- Hits: 19, convincing: 7
- Example `20261001_071419_set06_video_chunk_0009_segment_003_of_006.mp4` (score 0.1906): "The scene is a narrow, two-lane city street with parked cars lining both sides. A dark blue SUV is stopped in the lane ahead of the camera vehicle, with its brake lights illuminated. A black sedan approaches from the opposite direction and passes the SUV on the left. A white delivery truck is visibl"
- Example `20261001_071510_set06_video_chunk_0011_segment_002_of_006.mp4` (score 0.188): "The scene is a narrow, one-way urban street with a single lane in each direction. The ego vehicle is traveling behind a dark SUV that is stopped in the middle of the road. A blue sedan is parked on the left side of the street, partially blocking the lane. A pedestrian is walking along the left side "

### `curb_pullover`: Pulling over and pulling out (disabled)

- Queries: "car pulling over to the curb near pedestrians"; "vehicle pulling out from the curb into traffic"
- Hits: 20, convincing: 0

### `following_distance`: Following distance (disabled)

- Queries: "driving very close behind the vehicle ahead"; "vehicle ahead braking with little gap"
- Hits: 0, convincing: 0

### `turn_across_crosswalk`: Turning across a crosswalk (disabled)

- Queries: "vehicle turning at an intersection while pedestrians are in the crosswalk"; "turning right with people crossing"
- Hits: 18, convincing: 1
- Example `20261001_065754_set05_video_chunk_0000_segment_005_of_006.mp4` (score 0.3487): "The camera vehicle is in the left lane of a two-lane road, approaching an intersection. It is moving forward slowly and preparing to turn left. The traffic light ahead is red. A pedestrian is crossing the street in front of the vehicle, using the crosswalk. The camera vehicle is stopped, waiting for"

### `cyclist_nearby`: Sharing the road with cyclists (enabled)

- Queries: "cyclist riding in the lane ahead of the car"; "car passing a cyclist"
- Hits: 11, convincing: 11
- Example `20261001_070258_set05_video_chunk_0012_segment_001_of_006.mp4` (score 0.4192): "The scene is captured from a vehicle traveling along a two-lane residential street with a yellow center line. The road is lined with trees and houses, and the weather is clear with daylight. A cyclist wearing a helmet and light-colored shorts is riding ahead in the same direction, positioned near th"
- Example `20261001_070258_set05_video_chunk_0012_segment_002_of_006.mp4` (score 0.3274): "The scene is captured from a vehicle’s dashboard camera, showing a residential street intersection under a clear sky. The road is paved with a single lane in each direction, separated by a dashed yellow centerline. A stop sign is visible on the right side of the road, and a traffic light hangs over "

### `poor_conditions`: Driving for the conditions (enabled)

- Queries: "driving at night in rain with poor visibility"; "construction zone or blocked lane ahead"
- Hits: 10, convincing: 10
- Example `20261001_071651_set06_video_chunk_0015_segment_004_of_006.mp4` (score 0.373): "The scene is captured from a vehicle’s dashboard camera, showing a road intersection under a partly cloudy sky. The road surface is dry and marked with white lane lines. A person wearing a bright yellow-green high-visibility jacket stands in the middle of the intersection, directing traffic. This in"
- Example `20261001_071742_set06_video_chunk_0017_segment_006_of_006.mp4` (score 0.3604): "The scene unfolds on a narrow, single-lane urban street with a sidewalk on the right. The road is lined with orange traffic cones that narrow the driving lane and guide traffic around a large white truck parked on the left side of the street. This truck has a cylindrical tank and is marked with the "

## Caption wording over the candidate chunks

Over 72 segments: ego/camera vehicle 57%, slow 33%, stop 24%, yield 7%.
Captions describe the scene well but rarely say what the camera vehicle does.

## Candidate chunks (ranked)

1. `20261001_072155_set06_video_chunk_0027.mp4`: pedestrian_yield, poor_conditions, stopped_in_lane
2. `20261001_063740_set03_video_chunk_0014.mp4`: cyclist_nearby
3. `20261001_065754_set05_video_chunk_0000.mp4`: pedestrian_yield
4. `20261001_071626_set06_video_chunk_0014.mp4`: pedestrian_yield
5. `20261001_071510_set06_video_chunk_0011.mp4`: stopped_in_lane
6. `20261001_071742_set06_video_chunk_0017.mp4`: poor_conditions, stopped_in_lane
7. `20261001_063353_set03_video_chunk_0005.mp4`: cyclist_nearby, pedestrian_yield
8. `20261001_064154_set03_video_chunk_0024.mp4`: cyclist_nearby, poor_conditions
9. `20261001_063650_set03_video_chunk_0012.mp4`: (teammate 2 pick)
10. `20261001_070258_set05_video_chunk_0012.mp4`: cyclist_nearby
11. `20261001_071651_set06_video_chunk_0015.mp4`: poor_conditions
12. `20261001_065358_set04_video_chunk_0021.mp4`: curb_crowd

Teammate 2 chunks folded in: 5.

## Re-ingest

Re-ingest: done for exactly one non-trip chunk, `20261001_064244_set03_video_chunk_0026.mp4`, with
`reingest_prompt.txt` as the custom prompt and camera_id / capture_type / location kept. Still 6 segments.
The backend restarted during the job and lost its status, but the new captions landed.

- Before: camera/ego vehicle 3/6, slow 0/6, stop 4/6, yield 0/6
- After: camera/ego vehicle 6/6, slow 3/6, stop 5/6, yield 3/6

### Custom ingest prompt: before / after

**Segment 1, before:** "The scene unfolds on a two-lane, one-way road with a dedicated bicycle lane on the right side. The road surface is dry and marked with clear lane lines. A bicycle lane symbol is visible on the pavement. There are no traffic lights or stop signs visible in the immediate area. A black car is driving a"

**Segment 1, after:** "The camera vehicle drives straight along a city street, following a black car ahead at a moderate distance. It proceeds through an intersection and continues forward, passing a construction site on the right with orange traffic cones and a large crane. Pedestrians are visible on the sidewalk to the "

**Segment 3, before:** "The scene unfolds on a multi-lane urban road under a bright, partly cloudy sky. The road surface is dry and marked with white lane lines and crosswalks. The ego vehicle is traveling in the left lane of a two-lane road, following a black SUV directly ahead. A blue car is visible in the right lane, an"

**Segment 3, after:** "The camera vehicle drives straight in the left lane of a two-lane road, approaching an intersection. It follows a dark-colored SUV ahead at a safe distance, maintaining a steady pace. The vehicle slows slightly as it nears the intersection, where a pedestrian is standing on the sidewalk near the cro"


## Trip length

Trip = one 30 s chunk. One chunk is one classifier batch of 6 segments, discovery hits are
segment-level inside one chunk, and the app's timeline and `original_video` expect a single URI.
Combining chunks would add offsets, cross-chunk merging and LLM calls with no judging upside.
