# cd dashi/app && ../.venv/bin/python ../eval/make_sheet.py
"""Write eval/sheet.md: 6 flagged and 6 unflagged segments from the reviewed trips, for hand labelling."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import clients  # noqa: E402
import core  # noqa: E402

doc = json.loads((ROOT / "app" / "moments.json").read_text())
vss = clients.VSS()
segs = {t["trip_id"]: core.gather(vss, t["original_video"]) for t in doc["trips"]}
by_src = {s["source"]: (tid, s) for tid, ss in segs.items() for s in ss}

flagged = [m["sources"][0] for m in doc["moments"]]
for m in sorted(doc["moments"], key=lambda m: -len(m["sources"])):
    flagged += [s for s in m["sources"][1:] if s not in flagged]
flagged = flagged[:6]
covered = {s for m in doc["moments"] for s in m["sources"]}
unflagged = [s for ss in segs.values() for s in (x["source"] for x in ss) if s not in covered]
step = max(1, len(unflagged) // 6)
unflagged = unflagged[::step][:6]

out = ["# Dashi eval sheet", "",
       "Watch the clip in the VSS UI (search the filename) or the Dashi app; label from the VIDEO not the caption.",
       "For each row write `expected_scenario` (one of: " + ", ".join(s["id"] for s in core.enabled_scenarios(core.load_playbook()))
       + ", or none) and `expected_verdict` (handled_well, coachable or none) into `eval/labels.json`.", "",
       "| # | flagged | trip | time | segment file | caption (first 200 chars) |", "|---|---|---|---|---|---|"]
rows = [(s, True) for s in flagged] + [(s, False) for s in unflagged]
for i, (src, f) in enumerate(rows, 1):
    tid, s = by_src[src]
    cap = s["caption"][:200].replace("|", "/").replace("\n", " ")
    out.append(f"| {i} | {'yes' if f else 'no'} | {tid} | {int(s['start_sec'])}-{int(s['end_sec'])} s | `{src.split('/')[-1]}` | {cap} |")
out += ["", "Sources (for labels.json):", ""] + [f"- `{src}`" for src, _ in rows]
(ROOT / "eval" / "sheet.md").write_text("\n".join(out) + "\n")
print(f"wrote eval/sheet.md with {len(rows)} rows")
