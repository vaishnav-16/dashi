"""Dashi review pipeline: gather segments, classify captions, merge, coach, score."""
import collections
import hashlib
import json
import pathlib
import re
import threading
import time

import clients

try:
    import weave
    op = weave.op
except Exception:          # the pod does not install weave
    def op(f=None, **_):
        return f if f else (lambda g: g)

CONF_MIN = 0.6
BATCH = 6
HERE = pathlib.Path(__file__).resolve().parent
CACHE = HERE.parent / "work" / "classify_cache.json"
_cache_lock = threading.Lock()
DROPS = collections.Counter()

BANNED_HAPPENED = re.compile(r"speed(ing)?|hard brak|braked hard|slammed", re.I)
BANNED_COACH = re.compile(r"speed|brak|mph|km/h|fault|ticket|illegal", re.I)
WORD = re.compile(r"[a-z]{4,}")


def load_playbook(path=HERE / "playbook.json"):
    return json.loads(pathlib.Path(path).read_text())


def enabled_scenarios(pb):
    return [s for s in pb["scenarios"] if s["enabled"]]


def _scenario(pb, sid):
    return next(s for s in pb["scenarios"] if s["id"] == sid)


# ---- stage 1: gather ----------------------------------------------------------------

def _counts(raw):
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}


def gather(vss, original_video):
    for attempt in range(4):
        try:
            segs = vss.get("tools/segments", original_video=original_video)["segments"]
            break
        except clients.VSSError:
            if attempt == 3:
                raise
            time.sleep(5)
    out = []
    for s in sorted(segs, key=lambda s: int(s["segment_number"])):
        counts = _counts(s.get("object_counts"))
        out.append({
            "segment": int(s["segment_number"]), "start_sec": float(s["segment_start_sec"]),
            "end_sec": float(s["segment_end_sec"]), "source": s["source"],
            "caption": s.get("reasoning_content") or "", "counts": counts,
            "people": int(counts.get("person", 0)),
            "vehicles": sum(int(counts.get(k, 0)) for k in ("car", "truck", "bus", "motorcycle", "bicycle")),
        })
    return out


# ---- stage 2: classify --------------------------------------------------------------

def system_prompt(pb):
    scen = "\n".join(
        f"- id: {s['id']}\n  title: {s['title']}\n  look for: {s['look_for']}\n"
        f"  handled well when: {s['handled_well_when']}\n  coachable when: {s['coachable_when']}"
        for s in enabled_scenarios(pb))
    verdicts = "\n".join(f"- {k}: {v}" for k, v in pb["verdicts"].items())
    severity = "\n".join(f"- {k}: {v}" for k, v in pb["severity"].items())
    return f"""You review captions of forward-facing dashcam video from a rideshare driver's car. The car
with the camera is the "camera vehicle"; captions may call it the "ego vehicle". You never
see the video. You only see, for each 5-second segment, a caption written by a vision model
and object-detector counts. The counts are noisy: ignore animals, kites and airplanes, and
person counts are often too low.

For every segment, decide whether the caption clearly shows one of these scenarios and how
the camera vehicle handled it.

Scenarios:
{scen}

Verdicts:
{verdicts}

Severity (only for handled_well and coachable; for handled_well it is how serious the
hazard was):
{severity}

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
{{"segments": [{{"segment": <int>, "scenario_id": "<id or none>",
  "verdict": "handled_well|coachable|none", "severity": <1-3 or 0 for none>,
  "confidence": <0-1>, "evidence_quote": "<exact words or empty>",
  "what_happened": "<sentences or empty>"}}]}}"""


def _load_cache():
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def _save_cache(key, value):
    with _cache_lock:
        c = _load_cache()
        c[key] = value
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(c, indent=1, ensure_ascii=False))


USE_CACHE = True


@op
def classify_batch(segs, pb, model=clients.MODEL):
    payload = {"segments": [{"segment": s["segment"], "start_sec": s["start_sec"],
                             "caption": s["caption"], "object_counts": s["counts"]} for s in segs]}
    sysp = system_prompt(pb)
    key = hashlib.sha256((model + sysp + json.dumps(payload, sort_keys=True)).encode()).hexdigest()
    if USE_CACHE:
        hit = _load_cache().get(key)
        if hit is not None:
            return hit
    want = [s["segment"] for s in segs]
    for attempt in range(2):
        try:
            r = clients.llm(timeout=60).chat.completions.create(
                model=model, temperature=0, max_tokens=2000,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": sysp},
                          {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
            raw = json.loads(r.choices[0].message.content)["segments"]
            if [int(x.get("segment")) for x in raw] != want:
                raise ValueError("segment numbers differ")
            _save_cache(key, raw)
            return raw
        except Exception as e:  # noqa: BLE001
            err = e
    print(f"WARN classify_batch failed for segments {want}: {str(err)[:120]}")
    return []


def validate(raw, segs, pb):
    by_seg = {s["segment"]: s for s in segs}
    ids = {s["id"] for s in enabled_scenarios(pb)}
    kept = []
    for item in raw:
        try:
            seg = by_seg.get(int(item.get("segment")))
        except (TypeError, ValueError):
            seg = None
        if seg is None:
            DROPS["bad_id"] += 1
            continue
        sid, verdict = item.get("scenario_id"), item.get("verdict")
        if sid == "none" or verdict == "none":
            DROPS["none"] += 1
            continue
        if sid not in ids or verdict not in ("handled_well", "coachable"):
            DROPS["bad_id"] += 1
            continue
        try:
            sev = max(1, min(3, int(item.get("severity"))))
            conf = float(item.get("confidence"))
        except (TypeError, ValueError):
            DROPS["bad_id"] += 1
            continue
        if conf < CONF_MIN:
            DROPS["low_conf"] += 1
            continue
        quote = (item.get("evidence_quote") or "").strip().strip('"').strip()
        if not quote or quote not in seg["caption"]:
            DROPS["bad_quote"] += 1
            continue
        wh = (item.get("what_happened") or "").strip()
        if not wh or re.search(r"\d+\s*(km|mph)", wh, re.I) or BANNED_HAPPENED.search(wh):
            DROPS["bad_text"] += 1
            continue
        kept.append({**seg, "scenario_id": sid, "verdict": verdict, "severity": sev,
                     "confidence": conf, "evidence_quote": quote, "what_happened": wh})
    return kept


# ---- stage 3: merge -----------------------------------------------------------------

def merge(items, segs, trip_id, pb):
    items = sorted(items, key=lambda i: i["segment"])
    groups = []
    for it in items:
        g = groups[-1] if groups else None
        if (g and it["segment"] == g[-1]["segment"] + 1 and it["scenario_id"] == g[0]["scenario_id"]
                and it["verdict"] == g[0]["verdict"]):
            g.append(it)
        else:
            groups.append([it])
    idx = {s["segment"]: i for i, s in enumerate(segs)}
    moments = []
    for n, g in enumerate(groups, 1):
        best = max(g, key=lambda i: i["confidence"])
        first, last = idx[g[0]["segment"]], idx[g[-1]["segment"]]
        moments.append({
            "moment_id": f"{trip_id}-m{n}", "trip_id": trip_id,
            "scenario_id": g[0]["scenario_id"], "scenario_title": _scenario(pb, g[0]["scenario_id"])["title"],
            "verdict": g[0]["verdict"], "severity": max(i["severity"] for i in g),
            "confidence": round(min(i["confidence"] for i in g), 2),
            "start_sec": g[0]["start_sec"], "end_sec": g[-1]["end_sec"],
            "sources": [i["source"] for i in g],
            "context_before": segs[first - 1]["source"] if first > 0 else None,
            "context_after": segs[last + 1]["source"] if last + 1 < len(segs) else None,
            "people_detected": max(i["people"] for i in g),
            "evidence_quote": best["evidence_quote"], "caption": best["caption"],
            "what_happened": best["what_happened"],
        })
    return moments


# ---- stage 4: coach -----------------------------------------------------------------

COACH_SYSTEM = """You are Dashi, a calm driving coach on the rideshare driver's side. Write ONE sentence to
the driver in second person about this moment.
- If verdict is handled_well: say what they did right, using only the facts in
  "what_happened" and the playbook's "handled_well_when".
- If verdict is coachable: restate the playbook "tip" adapted to this moment. Do not add
  any advice that is not in the tip.
Warm, never punitive. No numbers, no speed, no braking claims. At most 30 words.
Return strict JSON: {"sentence": "<text>"}"""

IDEAL_SYSTEM = """You write a text prompt for a world-generation video model (NVIDIA Cosmos Predict /
Cosmos Transfer style) that will render a forward-facing dashcam clip showing how the
camera vehicle SHOULD have driven through this moment.
- Keep the same scene: reuse the road layout, lanes, vehicles, people, signs, weather and
  lighting described in the caption. Do not add new hazards or people.
- Change only the camera vehicle's behaviour, so it follows the playbook tip exactly.
- Describe the 5 to 10 seconds in present tense and time order, as one paragraph of
  60 to 120 words. Start with "Forward-facing dashcam view from a car".
- Name the camera vehicle "the camera car". No brand names, no numbers or speeds, no text
  overlays.
Return strict JSON: {"prompt": "<paragraph>"}"""


def _sentence_ok(text, verdict, tip):
    if not text or len(text.split()) > 30 or not text.endswith("."):
        return False
    if re.search(r"\d", text) or BANNED_COACH.search(text):
        return False
    if verdict == "coachable":
        shared = set(WORD.findall(text.lower())) & set(WORD.findall(tip.lower()))
        return len(shared) >= 2
    return True


def _llm_json(system, user, max_tokens, timeout=30):
    r = clients.llm(timeout=timeout).chat.completions.create(
        model=clients.MODEL, temperature=0, max_tokens=max_tokens,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": json.dumps(user, ensure_ascii=False)}])
    return json.loads(r.choices[0].message.content)


@op
def coach(moment, pb):
    s = _scenario(pb, moment["scenario_id"])
    tip = s["lesson"]["tip"]
    try:
        sent = _llm_json(COACH_SYSTEM, {
            "verdict": moment["verdict"], "scenario_title": moment["scenario_title"],
            "what_happened": moment["what_happened"],
            "handled_well_when": s["handled_well_when"], "tip": tip}, 120).get("sentence", "").strip()
    except Exception:  # noqa: BLE001
        sent = ""
    ok = _sentence_ok(sent, moment["verdict"], tip)
    out = dict(moment, why_it_matters=s["lesson"]["why"], verified_by_vlm=None)
    if moment["verdict"] == "coachable":
        out["safer_next_time"] = sent if ok else tip
        out["what_you_did_right"] = None
    else:
        out["what_you_did_right"] = sent if ok else "You handled this the way the playbook recommends."
        out["safer_next_time"] = None
    return out


@op
def ideal_video_prompt(moment, pb):
    """Stretch: a prompt for a video model to render what the driver should have done."""
    s = _scenario(pb, moment["scenario_id"])
    fallback = ("Forward-facing dashcam view from a car. " + moment["caption"].split(". ")[0].rstrip(".")
                + ". The camera car follows this guidance: " + s["lesson"]["tip"])
    try:
        p = _llm_json(IDEAL_SYSTEM, {"caption": moment["caption"], "what_happened": moment["what_happened"],
                                     "playbook_tip": s["lesson"]["tip"],
                                     "handled_well_when": s["handled_well_when"]}, 400, timeout=45)
        p = (p.get("prompt") or "").strip()
    except Exception:  # noqa: BLE001
        p = ""
    if not p.startswith("Forward-facing dashcam view") or re.search(r"\d", p) or not 40 <= len(p.split()) <= 160:
        p = fallback
    return p


# ---- stage 5: score -----------------------------------------------------------------

def score(moments):
    co = sum(m["severity"] for m in moments if m["verdict"] == "coachable")
    hw = sum(1 for m in moments if m["verdict"] == "handled_well")
    return max(0, min(100, 100 - 10 * co + 3 * hw))


def rating_mismatch(rating, moments):
    if rating is None:
        return None
    hw = any(m["verdict"] == "handled_well" for m in moments)
    big = any(m["verdict"] == "coachable" and m["severity"] >= 2 for m in moments)
    if rating <= 3 and hw and not big:
        return "underrated"
    if rating == 5 and big:
        return "missed_risk"
    return None


def summary(moments):
    if not moments:
        return "Clean trip. Nothing to flag."
    hw = sum(1 for m in moments if m["verdict"] == "handled_well")
    co = len(moments) - hw
    top = max(moments, key=lambda m: (m["severity"], m["verdict"] == "coachable", m["confidence"]))
    return f"{hw} moment(s) handled well and {co} to work on. {top['what_happened']}"


@op
def review_trip(vss, trip, pb, roles):
    ovs = trip.get("original_videos") or [trip["original_video"]]
    segs = []
    for k, ov in enumerate(ovs):
        for s in gather(vss, ov):
            s["start_sec"] += 30 * k
            s["end_sec"] += 30 * k
            s["segment"] += BATCH * k
            segs.append(s)
    items = []
    for i in range(0, len(segs), BATCH):
        batch = segs[i:i + BATCH]
        items += validate(classify_batch(batch, pb), batch, pb)
    moments = [coach(m, pb) for m in merge(items, segs, trip["trip_id"], pb)]
    for m in moments:
        m["ideal_video_prompt"] = ideal_video_prompt(m, pb) if m["verdict"] == "coachable" else None
    role = roles.get(trip.get("story_role") or "") or {}
    rating = role.get("rider_rating")
    out = {k: trip[k] for k in ("trip_id", "date", "start_time", "pickup", "dropoff") if k in trip}
    out.update({
        "original_video": ovs[0], "duration_sec": 30 * len(ovs), "story_role": trip.get("story_role"),
        "rider_rating": rating, "rider_comment": role.get("rider_comment"),
        "safety_score": score(moments),
        "handled_well": sum(1 for m in moments if m["verdict"] == "handled_well"),
        "coachable": sum(1 for m in moments if m["verdict"] == "coachable"),
        "rating_mismatch": rating_mismatch(rating, moments), "summary": summary(moments),
    })
    return out, moments
