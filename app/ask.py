"""The Ask agent: task-shaped tools over the moments cache, chip intents, LLM wording.

Tier 1: each chip maps to a fixed tool sequence, then one LLM call phrases the answer.
If the LLM fails or exceeds LLM_BUDGET_SEC, the templated answer is returned instead,
so the chips never show an error.
"""
import concurrent.futures
import json
import re

import clients

LLM_BUDGET_SEC = 8
CAMERA_ID = "pie_cam-3"
PICKUP_SCENARIOS = {"curb_crowd", "curb_pullover", "stopped_in_lane"}

CHIPS = {
    "improve": "Help me improve my reviews",
    "last_trip": "How was my last trip?",
    "best": "Show my best moments",
    "pickups": "Where can I be safer at pickups?",
}

_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)


class Tools:
    """Task-shaped tools. The model never sees raw endpoints."""

    def __init__(self, data, playbook, vss=None):
        self.data = data
        self.playbook = {s["id"]: s for s in playbook["scenarios"]}
        self.vss = vss

    def get_trips(self):
        return self.data["trips"]

    def get_trip(self, trip_id):
        return next((t for t in self.data["trips"] if t["trip_id"] == trip_id), None)

    def get_trip_moments(self, trip_id):
        ms = [m for m in self.data["moments"] if m["trip_id"] == trip_id]
        return sorted(ms, key=lambda m: m["start_sec"])

    def latest_trip(self):
        trips = self.get_trips()
        return max(trips, key=lambda t: (t["date"], t["start_time"])) if trips else None

    def get_lesson(self, scenario_id):
        s = self.playbook.get(scenario_id)
        return s and {"scenario_id": scenario_id, "title": s["title"], **s["lesson"]}

    def find_in_my_footage(self, query, top_k=6):
        """Live hybrid search, restricted to the dashcam and this driver's trips."""
        if not self.vss:
            return []
        mine = {t["original_video"] for t in self.get_trips()}
        res = self.vss.post("search", {"query": query, "top_k": 30, "llm_top_n": 1,
                                       "min_similarity": 0.3,
                                       "metadata_filters": {"camera_id": CAMERA_ID}})
        hits = [r for r in res.get("results", []) if r.get("original_video") in mine]
        return [{"source": r["source"], "original_video": r["original_video"],
                 "caption": r.get("reasoning_content", ""),
                 "score": r.get("similarity_score")} for r in hits[:top_k]]


def _ts(sec):
    sec = int(sec or 0)
    return f"{sec // 60}:{sec % 60:02d}"


def _trip_label(t):
    return f"your {t['start_time']} trip on {t['date']} ({t['pickup']} to {t['dropoff']})"


def _step(label, action, target):
    return {"label": label, "action": action, "target": target}


def _rank(m):
    return (m["severity"], m["confidence"])


def plan_improve(tools):
    trips = sorted(tools.get_trips(), key=lambda t: (t["rider_rating"], t["date"]))
    low = [t for t in trips if t["rider_rating"] < 5][:2] or trips[:1]
    moments, steps, facts = [], [], []
    for t in low:
        ms = tools.get_trip_moments(t["trip_id"])
        if t.get("rating_mismatch") == "underrated":
            good = sorted([m for m in ms if m["verdict"] == "handled_well"], key=_rank, reverse=True)[:1]
            moments += good
            steps.append(_step("Send evidence for a rating review", "send_evidence", t["trip_id"]))
            facts.append(f"{_trip_label(t)} got {t['rider_rating']} stars, but the video shows you "
                         f"handled it well" + (f": {good[0]['what_you_did_right']}" if good else "."))
        else:
            co = sorted([m for m in ms if m["verdict"] == "coachable"], key=_rank, reverse=True)[:1]
            moments += co
            for m in co:
                steps.append(_step(f"Open lesson: {m['scenario_title']}", "open_lesson", m["scenario_id"]))
                facts.append(f"On {_trip_label(t)} ({t['rider_rating']} stars) there is one thing to "
                             f"work on: {m['scenario_title'].lower()} at {_ts(m['start_sec'])}.")
    if not moments:
        co = sorted([m for m in tools.data["moments"] if m["verdict"] == "coachable"], key=_rank, reverse=True)[:1]
        moments += co
        steps += [_step(f"Open lesson: {m['scenario_title']}", "open_lesson", m["scenario_id"]) for m in co]
    trip_id = low[0]["trip_id"] if low else None
    if trip_id:
        steps.append(_step("See the full trip", "open_trip", trip_id))
    lead = (f"Your lowest rating was {low[0]['rider_rating']} stars on {_trip_label(low[0])}."
            if low else "Here is what your reviewed trips show.")
    return lead, facts, moments, trip_id, steps


def plan_last_trip(tools):
    t = tools.latest_trip()
    if not t:
        return "No trips have been reviewed yet.", [], [], None, []
    ms = tools.get_trip_moments(t["trip_id"])
    hw = [m for m in ms if m["verdict"] == "handled_well"]
    co = [m for m in ms if m["verdict"] == "coachable"]
    lead = (f"On {_trip_label(t)} you scored {t['safety_score']} for safety, "
            f"with a {t['rider_rating']}-star rider rating.")
    facts = []
    if hw:
        facts.append(f"{len(hw)} moment(s) handled well, for example: {hw[0]['what_you_did_right']}")
    if co:
        facts.append(f"{len(co)} thing(s) to work on, starting with {co[0]['scenario_title'].lower()}.")
    if not ms:
        facts.append("Clean trip. Nothing to flag.")
    steps = [_step("See the full trip", "open_trip", t["trip_id"])]
    if t.get("rating_mismatch") == "underrated":
        steps.insert(0, _step("Send evidence for a rating review", "send_evidence", t["trip_id"]))
    steps += [_step(f"Open lesson: {m['scenario_title']}", "open_lesson", m["scenario_id"]) for m in co[:1]]
    return lead, facts, (hw[:1] + co[:1]) or ms[:2], t["trip_id"], steps


def plan_best(tools):
    good = sorted([m for m in tools.data["moments"] if m["verdict"] == "handled_well"],
                  key=_rank, reverse=True)[:3]
    if not good:
        return "No handled-well moments yet in your reviewed trips.", [], [], None, []
    trips = {t["trip_id"]: t for t in tools.get_trips()}
    lead = f"You have {len([m for m in tools.data['moments'] if m['verdict'] == 'handled_well'])} handled-well moments. Here are your best."
    facts = [f"{trips[m['trip_id']]['start_time']} trip: {m['what_you_did_right']}" for m in good]
    underrated = [t for t in tools.get_trips() if t.get("rating_mismatch") == "underrated"]
    steps = [_step("See the full trip", "open_trip", good[0]["trip_id"])]
    steps += [_step("Send evidence for a rating review", "send_evidence", t["trip_id"]) for t in underrated[:1]]
    return lead, facts, good, good[0]["trip_id"], steps


def plan_pickups(tools):
    ms = sorted([m for m in tools.data["moments"] if m["scenario_id"] in PICKUP_SCENARIOS],
                key=_rank, reverse=True)[:3]
    lesson_id = next((m["scenario_id"] for m in ms if m["verdict"] == "coachable"), None) or "curb_pullover"
    lesson = tools.get_lesson(lesson_id)
    steps = [_step(f"Open lesson: {lesson['title']}", "open_lesson", lesson_id)] if lesson else []
    if not ms:
        lead = "Your reviewed trips have no pickup or drop-off moments flagged yet."
        facts = [f"A tip for your next pickup: {lesson['tip']}"] if lesson else []
        return lead, facts, [], None, steps
    lead = f"Here are {len(ms)} pickup and drop-off moments from your trips."
    facts = [f"{m['scenario_title']}: {m['what_happened']}" for m in ms]
    return lead, facts, ms, ms[0]["trip_id"], steps


PLANS = {"improve": plan_improve, "last_trip": plan_last_trip, "best": plan_best, "pickups": plan_pickups}

_ROUTES = [
    ("pickups", r"pick ?up|drop ?off|curb|pull(ing)? over|double.?park"),
    ("last_trip", r"last trip|latest trip|recent trip|my trip|how was"),
    ("best", r"best|good|well|kudos|proud|nice"),
    ("improve", r"improve|review|rating|star|better|safer|coach|feedback|tip"),
]

HELP_TEXT = ("I can help with your trips and driving: why a rating was low, how your last trip "
             "went, your best moments, and safer pickups. Try one of the suggestions below.")


def route(message):
    text = (message or "").strip().lower()
    for key, label in CHIPS.items():
        if text == label.lower():
            return key
    for key, pattern in _ROUTES:
        if re.search(pattern, text):
            return key
    return None


SYSTEM_PROMPT = """You are Dashi, a warm driving coach on the rideshare driver's side.
Rewrite the context and facts as one short answer to the driver.
Rules:
- Second person ("you"), warm, never punitive or alarming.
- Start from the context sentence. Cover every fact briefly.
- Do not offer actions or ask questions; the app shows next_steps as buttons below your text.
- Rider ratings: only use the ratings listed in "trips", exactly as given. Never guess one.
- Use only what is given. Do not add advice, numbers, speeds or braking claims.
- At most 60 words. No lists, no markdown.
Return strict JSON: {"answer": "<text>"}"""

_RATING_RE = re.compile(r"\b([1-5])[- ]stars?\b", re.I)


def _phrase(question, lead, facts, trips, steps):
    resp = clients.llm(timeout=LLM_BUDGET_SEC).chat.completions.create(
        model=clients.MODEL, temperature=0, max_tokens=200,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": json.dumps(
                      {"driver_question": question, "context": lead, "facts": facts,
                       "trips": [{"trip": f"{t['start_time']} {t['pickup']} to {t['dropoff']}",
                                  "rider_rating": t["rider_rating"]} for t in trips],
                       "next_steps": [s["label"] for s in steps]})}])
    answer = json.loads(resp.choices[0].message.content)["answer"].strip()
    if not answer or len(answer.split()) > 80:
        raise ValueError("answer out of bounds")
    allowed = {str(t["rider_rating"]) for t in trips}
    if any(r not in allowed for r in _RATING_RE.findall(answer)):
        raise ValueError("answer states a rating that is not in the data")
    if re.search(r"\b(send|sent|evidence)\b", answer, re.I) and not any(s["action"] == "send_evidence" for s in steps):
        raise ValueError("answer offers evidence that is not available")
    return answer


def answer(tools, message):
    intent = route(message)
    if intent is None:
        return {"answer": HELP_TEXT, "moment_ids": [], "trip_id": None,
                "next_steps": [_step(label, "ask", label) for label in CHIPS.values()],
                "source": "help"}
    lead, facts, moments, trip_id, steps = PLANS[intent](tools)
    template = " ".join([lead] + facts[:2])
    ref_ids = list(dict.fromkeys([trip_id] + [m["trip_id"] for m in moments]))
    trips = [t for t in (tools.get_trip(i) for i in ref_ids if i) if t]
    source = "llm"
    try:
        text = _pool.submit(_phrase, message, lead, facts, trips, steps[:3]).result(timeout=LLM_BUDGET_SEC)
    except Exception:
        text, source = template, "template"
    seen, ids = set(), []
    for m in moments:
        if m["moment_id"] not in seen:
            seen.add(m["moment_id"])
            ids.append(m["moment_id"])
    return {"answer": text, "moment_ids": ids, "trip_id": trip_id,
            "next_steps": steps[:3], "intent": intent, "source": source}
