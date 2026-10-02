"""Dashi CLI: review trips and write moments.json.

python analyze.py --trips trips.json --out moments.json [--trip T-1041] [--no-weave] [--no-cache]
python analyze.py --chunks ../candidates.txt --out ../work/candidates_review.json
python analyze.py --assign ../work/candidates_review.json --trips trips.json
"""
import argparse
import concurrent.futures
import datetime
import json
import pathlib

import clients
import core

ROLE_TRIP = {"unfair_low_rating": "T-1041", "missed_risk": "T-1042", "clean": "T-1043",
             "mixed": "T-1044", "live_demo": "T-1045"}


def init_weave():
    try:
        import weave
        weave.init(f"{clients.setting('WANDB_TEAM')}/{clients.setting('WANDB_PROJECT')}")
    except Exception as e:  # noqa: BLE001
        print("weave unavailable:", str(e)[:120])


def run(trips, pb, roles):
    vss = clients.VSS()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        return list(ex.map(lambda t: core.review_trip(vss, t, pb, roles), trips))


def print_table(trips_out, moments):
    print(f"\n{'trip':7} {'chunk':40} {'role':18} {'rate':4} {'hw':>2} {'co':>2} {'sev':>3} {'score':>5} mismatch")
    for t in trips_out:
        ms = [m for m in moments if m["trip_id"] == t["trip_id"]]
        sev = max([m["severity"] for m in ms if m["verdict"] == "coachable"] or [0])
        print(f"{t['trip_id']:7} {t['original_video'][-40:]:40} {str(t.get('story_role')):18} "
              f"{str(t.get('rider_rating')):4} {t['handled_well']:>2} {t['coachable']:>2} {sev:>3} "
              f"{t['safety_score']:>5} {t['rating_mismatch']}")
    print("validation drops:", dict(core.DROPS))


def write_out(path, meta, trips_out, moments):
    doc = {"generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "model": clients.MODEL, "simulated_fields": meta.get("simulated_fields", []),
           "driver": meta.get("driver"), "trips": trips_out, "moments": moments}
    pathlib.Path(path).write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    print(f"wrote {path}: {len(trips_out)} trips, {len(moments)} moments")


def assign(review_path, trips_path):
    rev = json.loads(pathlib.Path(review_path).read_text())
    tdoc = json.loads(pathlib.Path(trips_path).read_text())
    by_chunk = {t["original_video"]: [m for m in rev["moments"] if m["trip_id"] == t["trip_id"]]
                for t in rev["trips"]}
    order = [t["original_video"] for t in rev["trips"]]
    used, picks = set(), {}

    def hw(ms): return [m for m in ms if m["verdict"] == "handled_well"]
    def co(ms): return [m for m in ms if m["verdict"] == "coachable"]
    def maxconf(ms): return max([m["confidence"] for m in ms] or [0])

    def pick(role, ok, key, closest=None):
        cands = [ov for ov in order if ov not in used and ok(by_chunk[ov])]
        if not cands and closest:
            cands = [ov for ov in order if ov not in used and closest(by_chunk[ov])]
            if cands:
                print(f"role {role}: no exact match, using the closest chunk with its real verdicts")
        if not cands:
            print(f"role {role}: could not be filled")
            return
        best = max(cands, key=lambda ov: key(by_chunk[ov]))
        used.add(best)
        picks[role] = best

    pick("unfair_low_rating",
         lambda ms: hw(ms) and not any(m["severity"] >= 2 for m in co(ms)),
         lambda ms: (any(m["scenario_id"] == "pedestrian_yield" for m in hw(ms)), len(hw(ms)), maxconf(ms)))
    pick("missed_risk", lambda ms: any(m["severity"] >= 2 for m in co(ms)),
         lambda ms: max(m["severity"] * m["confidence"] for m in co(ms)))
    pick("clean", lambda ms: not co(ms), lambda ms: (len(hw(ms)) >= 1, maxconf(ms)))
    pick("mixed", lambda ms: hw(ms) and co(ms), lambda ms: (len(ms), maxconf(ms)),
         closest=lambda ms: bool(ms))
    pick("live_demo", lambda ms: True, lambda ms: (len(ms), maxconf(ms)))

    for t in tdoc["trips"]:
        role = next((r for r, tid in ROLE_TRIP.items() if tid == t["trip_id"]), None)
        if role in picks:
            t["original_video"], t["story_role"] = picks[role], role
        else:
            t["story_role"] = None
    pathlib.Path(trips_path).write_text(json.dumps(tdoc, indent=2, ensure_ascii=False) + "\n")
    for role, ov in picks.items():
        ms = by_chunk[ov]
        print(f"{ROLE_TRIP[role]} {role:18} {ov.split('/')[-1]}  hw {len(hw(ms))} co {len(co(ms))} "
              f"co_sev {[m['severity'] for m in co(ms)]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trips")
    ap.add_argument("--chunks")
    ap.add_argument("--assign")
    ap.add_argument("--out")
    ap.add_argument("--trip")
    ap.add_argument("--no-weave", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()

    if a.assign:
        return assign(a.assign, a.trips)
    if not a.no_weave:
        init_weave()
    core.USE_CACHE = not a.no_cache
    pb = core.load_playbook()

    if a.chunks:
        ovs = [l.strip() for l in pathlib.Path(a.chunks).read_text().splitlines() if l.strip()]
        trips = [{"trip_id": f"C-{i:02d}", "original_video": ov, "story_role": None}
                 for i, ov in enumerate(ovs, 1)]
        meta = {}
        roles = {}
    else:
        meta = json.loads(pathlib.Path(a.trips).read_text())
        roles = meta.get("story_roles", {})
        trips = [t for t in meta["trips"] if t.get("story_role") and t["story_role"] != "live_demo"]
        if a.trip:
            trips = [t for t in trips if t["trip_id"] == a.trip]

    results = run(trips, pb, roles)
    trips_out = [t for t, _ in results]
    moments = [m for _, ms in results for m in ms]

    if a.trip and pathlib.Path(a.out).exists():
        old = json.loads(pathlib.Path(a.out).read_text())
        trips_out = [t for t in old["trips"] if t["trip_id"] != a.trip] + trips_out
        trips_out.sort(key=lambda t: t["trip_id"])
        moments = [m for m in old["moments"] if m["trip_id"] != a.trip] + moments
    print_table(trips_out, moments)
    write_out(a.out, meta, trips_out, moments)


if __name__ == "__main__":
    main()
