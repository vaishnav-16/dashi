# run from dashi/app so `import clients` works:  cd app && ../.venv/bin/python ../discover.py
"""Phase 0 discovery: search the pie_cam-3 footage for each playbook scenario, prune the
playbook, rank candidate chunks and dump their captions before any re-ingest."""
import collections
import concurrent.futures
import json
import pathlib
import re
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent / "app"))
import clients  # noqa: E402

ROOT = pathlib.Path(__file__).parent
CAM = "pie_cam-3"
vss = clients.VSS()

NEG = re.compile(r"\b(no|not|none|without|absence|neither|nor)\b", re.I)
CONVINCING = {
    "pedestrian_yield": [r"pedestrian|person|people",
                         r"cross|crosswalk|step(s|ping)? (off|into)|in the road|roadway"],
    "curb_crowd": [r"(group|several|crowd|multiple|many) (of )?(pedestrians|people)"],
    "stopped_in_lane": [r"double[- ]?park|stopped in the (travel )?lane|blocking (a|the) lane|stopped in the (middle|road)"],
    "curb_pullover": [r"pull(s|ed|ing)? (over|out|in|away|to the curb|from the curb)"],
    "following_distance": [r"(directly|immediately) ahead|close(ly)? behind|brake lights|same lane ahead"],
    "turn_across_crosswalk": [r"turn(s|ed|ing)?", r"crosswalk|pedestrian"],
    "cyclist_nearby": [r"cyclist|bicycl|bike"],
    "poor_conditions": [r"night|rain|wet road|glare|construction|roadwork|cones?\b|blocked lane"],
}
WORDING = {
    "ego/camera vehicle": r"\b(ego|camera) vehicle",
    "slow": r"\bslow(s|ing|ed|ly)?\b",
    "stop": r"\b(ego|camera) vehicle[^.]*\bstop(s|ped|ping)?\b",
    "yield": r"\byield",
}


def list_chunks():
    out, off = [], 0
    while True:
        r = vss.get("videos/explore", scope="all", limit=100, offset=off)
        items = r.get("chunks") or []
        out += items
        off += len(items)
        if not items or off >= int(r.get("total", 0)):
            break
    cam = [c for c in out if c.get("camera_id") == CAM]
    by_set = collections.defaultdict(list)
    for c in cam:
        name = c["original_video"].split("/")[-1]
        m = re.search(r"_(set\d+)_", name)
        by_set[m.group(1) if m else "?"].append(name)
    print(f"explore total {len(out)}, {CAM} chunks {len(cam)}")
    for s in sorted(by_set):
        names = sorted(by_set[s])
        print(f"  {s}: {len(names):3d}  {names[0]} .. {names[-1]}")
    return cam, {s: len(v) for s, v in by_set.items()}


def search(q):
    r = vss.post("search", {"query": q, "top_k": 10, "llm_top_n": 1, "min_similarity": 0.3,
                            "metadata_filters": {"camera_id": CAM}})
    keys = ("source", "original_video", "segment_number", "similarity_score", "reasoning_content")
    return [{k: h.get(k) for k in keys} for h in r.get("results") or []]


def affirmative(caption):
    sents = re.split(r"(?<=[.!?])\s+", caption or "")
    return " ".join(s for s in sents if not NEG.search(s))


def convincing(sid, caption):
    aff = affirmative(caption)
    return all(re.search(p, aff, re.I) for p in CONVINCING[sid])


def main():
    cam, set_counts = list_chunks()
    explore_ovs = {c["original_video"] for c in cam}
    seg0 = vss.get("tools/segments", original_video=cam[0]["original_video"])["segments"][0]
    print("segment fields:", sorted(seg0.keys()))
    print("sample caption:", seg0.get("reasoning_content"))

    pb_path = ROOT / "playbook.json"
    pb = json.loads(pb_path.read_text())
    jobs = [(s["id"], q) for s in pb["scenarios"] for q in s["search_queries"]]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(lambda j: (j, search(j[1])), jobs))

    hits = collections.defaultdict(dict)
    for (sid, q), rs in results:
        for h in rs:
            if h["source"] in hits[sid]:
                continue
            cap = h.get("reasoning_content") or ""
            hits[sid][h["source"]] = {
                "query": q, "source": h["source"], "original_video": h["original_video"],
                "segment_number": int(h["segment_number"]) if h.get("segment_number") is not None else None,
                "score": round(float(h.get("similarity_score") or 0), 4),
                "convincing": convincing(sid, cap), "caption": cap}
    hits = {sid: sorted(v.values(), key=lambda h: -h["score"]) for sid, v in hits.items()}
    (ROOT / "discovery_hits.json").write_text(json.dumps(hits, indent=2, ensure_ascii=False))

    conv_count = {}
    for s in pb["scenarios"]:
        hs = hits.get(s["id"], [])
        conv = [h for h in hs if h["convincing"]]
        conv_count[s["id"]] = len(conv)
        print(f"\n== {s['id']}: hits {len(hs)}, convincing {len(conv)}")
        for h in conv[:2]:
            print(f"   [{h['score']}] {h['source'].split('/')[-1]}: {h['caption'][:200]}")

    ranked = sorted(conv_count, key=lambda k: -conv_count[k])
    passing = [k for k in ranked if conv_count[k] >= 3][:5]
    note = ""
    if len(passing) < 3:
        passing = ranked[:3]
        note = "Fewer than 3 scenarios had 3+ convincing hits; kept the top 3 by convincing count."
    for s in pb["scenarios"]:
        s["enabled"] = s["id"] in passing
    pb_path.write_text(json.dumps(pb, indent=2, ensure_ascii=False) + "\n")
    shutil.copy(pb_path, ROOT / "app" / "playbook.json")
    print("\nenabled:", passing, note)

    chunk_sc = collections.defaultdict(lambda: {"scen": set(), "sum": 0.0})
    for sid in passing:
        for h in hits.get(sid, []):
            if h["convincing"]:
                chunk_sc[h["original_video"]]["scen"].add(sid)
                chunk_sc[h["original_video"]]["sum"] += h["score"]
    t2 = ROOT / "teammate2_chunks.txt"
    t2_folded = []
    if t2.exists():
        bucket, user = clients.setting("S3_CHUNKS_BUCKET"), clients.setting("USERNAME")
        for line in t2.read_text().split():
            base = line.strip().split("/")[-1]
            match = [ov for ov in explore_ovs if ov.endswith("/" + base)]
            ov = match[0] if match else f"s3://{bucket}/{user}/{base}"
            chunk_sc[ov]["sum"] += 3
            t2_folded.append(ov)
    scored = {ov: 2 * len(v["scen"]) + v["sum"] for ov, v in chunk_sc.items()}
    top = sorted(scored, key=lambda ov: -scored[ov])[:12]
    (ROOT / "candidates.txt").write_text("\n".join(top) + "\n")
    print("\ncandidates:")
    for i, ov in enumerate(top, 1):
        print(f"  {i:2d}. {ov.split('/')[-1]}  score {scored[ov]:.2f}  {sorted(chunk_sc[ov]['scen'])}")

    # Keep earlier dumps: once a chunk is re-ingested its original captions are gone.
    before_path = ROOT / "captions_before.json"
    before = json.loads(before_path.read_text()) if before_path.exists() else {}
    todo = [ov for ov in top if ov not in before]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        for ov, segs in zip(todo, ex.map(lambda o: vss.get("tools/segments", original_video=o)["segments"], todo)):
            before[ov] = segs
    before_path.write_text(json.dumps(before, indent=2, ensure_ascii=False))

    caps = [s.get("reasoning_content") or "" for ov in top for s in before[ov]]
    stats = {k: round(100 * sum(bool(re.search(p, c, re.I)) for c in caps) / max(1, len(caps)))
             for k, p in WORDING.items()}
    print("\nwording stats over", len(caps), "candidate segments:", stats)

    md = ["# Dashi discovery", "",
          "## Footage", "",
          f"- `camera_id`: `{CAM}` (Toronto dashcam research set standing in for rideshare trips).",
          f"- Chunks per set: " + ", ".join(f"{s} {n}" for s, n in sorted(set_counts.items())) + f" (total {sum(set_counts.values())}).",
          "- Every chunk is 30 s, split into 6 segments of 5 s.", "",
          "## Real field names (`/tools/segments`)", "",
          "- clip URI `source`, caption `reasoning_content`, timing `segment_start_sec` / `segment_end_sec`,",
          "  order `segment_number`, YOLO `object_classes` / `object_counts` (JSON string).",
          "- `POST /search` rejects `llm_top_n: 0` with HTTP 422; we use `llm_top_n: 1`.",
          f"- All segment fields: {', '.join('`'+k+'`' for k in sorted(seg0.keys()))}.", "",
          "## Scenarios", "",
          "A hit is *convincing* when the caption, after dropping negated sentences (\"No pedestrians ...\"),",
          "matches the scenario's keyword regexes. Similarity scores alone (0.3 to 0.4) do not separate good hits.", ""]
    for s in pb["scenarios"]:
        hs = hits.get(s["id"], [])
        conv = [h for h in hs if h["convincing"]]
        md += [f"### `{s['id']}`: {s['title']} ({'enabled' if s['enabled'] else 'disabled'})", "",
               "- Queries: " + "; ".join(f"\"{q}\"" for q in s["search_queries"]),
               f"- Hits: {len(hs)}, convincing: {len(conv)}"]
        for h in conv[:2]:
            md.append(f"- Example `{h['source'].split('/')[-1]}` (score {h['score']}): \"{h['caption'][:300]}\"")
        md.append("")
    if note:
        md += [note, ""]
    md += ["## Caption wording over the candidate chunks", "",
           f"Over {len(caps)} segments: " + ", ".join(f"{k} {v}%" for k, v in stats.items()) + ".",
           "Captions describe the scene well but rarely say what the camera vehicle does.", "",
           "## Candidate chunks (ranked)", ""]
    for i, ov in enumerate(top, 1):
        md.append(f"{i}. `{ov.split('/')[-1]}`: {', '.join(sorted(chunk_sc[ov]['scen'])) or '(teammate 2 pick)'}")
    md += ["", f"Teammate 2 chunks folded in: {len(t2_folded)}." if t2.exists() else "Teammate 2 chunks: none received at discovery time.",
           "", "## Re-ingest", "", "Re-ingest: pending decision.", "",
           "## Trip length", "",
           "Trip = one 30 s chunk. One chunk is one classifier batch of 6 segments, discovery hits are",
           "segment-level inside one chunk, and the app's timeline and `original_video` expect a single URI.",
           "Combining chunks would add offsets, cross-chunk merging and LLM calls with no judging upside.", ""]
    (ROOT / "discovery.md").write_text("\n".join(md))
    print("\nwrote discovery_hits.json, candidates.txt, captions_before.json, discovery.md")


if __name__ == "__main__":
    main()
