"""Dashi web app: serves the driver UI and the /ds/ JSON API from the moments cache.

The Ingress strips /app, so routes live at /. Set DASHI_LOCAL=1 to run on the VM:
the page then uses base href "/" and clip URLs point at the VSS host directly.
"""
import json
import os
import pathlib
import threading
import time
import uuid

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import ask
import clients

HERE = pathlib.Path(__file__).parent
LOCAL = os.environ.get("DASHI_LOCAL") == "1"

app = FastAPI(title="Dashi")
vss = clients.VSS()
_lessons_done = set()
_sent_evidence = {}
_cache = {"key": None, "data": None, "playbook": None}
_cache_lock = threading.Lock()


def _data_file():
    real = HERE / "moments.json"
    return real if real.exists() else HERE / "moments.sample.json"


def load():
    f, pb = _data_file(), HERE / "playbook.json"
    key = (str(f), f.stat().st_mtime, pb.stat().st_mtime)
    with _cache_lock:
        if _cache["key"] != key:
            _cache.update(key=key, data=json.loads(f.read_text()), playbook=json.loads(pb.read_text()))
        return _cache["data"], _cache["playbook"]


def tools():
    data, playbook = load()
    return ask.Tools(data, playbook, vss)


def _trip_or_404(t, trip_id):
    trip = t.get_trip(trip_id)
    if not trip:
        raise HTTPException(404, f"unknown trip {trip_id}")
    return trip


def _lessons(t):
    by_scenario = {}
    for m in sorted(t.data["moments"], key=lambda m: (m["verdict"] != "coachable", -m["severity"])):
        by_scenario.setdefault(m["scenario_id"], m)
    out = []
    for sid, example in by_scenario.items():
        lesson = t.get_lesson(sid)
        if lesson:
            out.append({**lesson, "example_moment": example, "done": sid in _lessons_done})
    return out


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index():
    html = (HERE / "index.html").read_text()
    if LOCAL:
        html = html.replace('<base href="/app/">', '<base href="/">', 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/ds/home")
def home():
    t = tools()
    data = t.data
    latest = t.latest_trip()
    cards = []
    for trip in sorted(t.get_trips(), key=lambda x: (x["date"], x["start_time"]), reverse=True)[:2]:
        for m in sorted(t.get_trip_moments(trip["trip_id"]), key=lambda m: (m["verdict"] != "handled_well", -m["severity"]))[:1]:
            if m["verdict"] == "handled_well":
                text = f"New from your {trip['start_time']} trip: {m['what_you_did_right']} Nice work."
            else:
                text = f"From your {trip['start_time']} trip: a quick tip on {m['scenario_title'].lower()}."
            cards.append({"trip_id": trip["trip_id"], "moment_id": m["moment_id"],
                          "verdict": m["verdict"], "text": text})
    lessons = _lessons(t)
    return {"driver": data["driver"], "latest_trip": latest, "cards": cards[:3],
            "chips": list(ask.CHIPS.values()),
            "totals": {"kudos": sum(m["verdict"] == "handled_well" for m in data["moments"]),
                       "lessons_done": sum(l["done"] for l in lessons),
                       "lessons_total": len(lessons)},
            "sample": bool(data.get("sample")), "model": data.get("model"),
            "generated_at": data.get("generated_at"),
            "simulated_fields": data.get("simulated_fields", [])}


@app.get("/ds/trips")
def trips():
    t = tools()
    return {"trips": sorted(t.get_trips(), key=lambda x: (x["date"], x["start_time"]), reverse=True),
            "sample": bool(t.data.get("sample"))}


@app.get("/ds/trips/{trip_id}")
def trip(trip_id: str):
    t = tools()
    return {"trip": _trip_or_404(t, trip_id), "moments": t.get_trip_moments(trip_id)}


@app.get("/ds/moments/{moment_id}")
def moment(moment_id: str):
    m = next((m for m in tools().data["moments"] if m["moment_id"] == moment_id), None)
    if not m:
        raise HTTPException(404, f"unknown moment {moment_id}")
    return m


@app.get("/ds/clip")
def clip(source: str):
    try:
        path = vss.stream_path(source)
    except Exception:
        return JSONResponse({"error": "clip service unavailable"}, status_code=503)
    return {"url": (vss.url + path) if LOCAL else path}


@app.get("/ds/lessons")
def lessons():
    ls = _lessons(tools())
    return {"lessons": ls, "done": sum(l["done"] for l in ls), "total": len(ls)}


@app.post("/ds/lessons/{scenario_id}/done")
def lesson_done(scenario_id: str):
    _lessons_done.add(scenario_id)
    return {"ok": True, "done": sorted(_lessons_done)}


class AskBody(BaseModel):
    message: str


@app.post("/ds/ask")
def ask_route(body: AskBody):
    t = tools()
    try:
        return ask.answer(t, body.message)
    except Exception:
        return {"answer": ask.HELP_TEXT, "moment_ids": [], "trip_id": None,
                "next_steps": [{"label": c, "action": "ask", "target": c} for c in ask.CHIPS.values()],
                "source": "error-fallback"}


class EvidenceBody(BaseModel):
    send: bool = False


def _fmt_range(m):
    return f"{ask._ts(m['start_sec'])} to {ask._ts(m['end_sec'])}"


@app.post("/ds/trips/{trip_id}/evidence")
def evidence(trip_id: str, body: EvidenceBody = EvidenceBody()):
    t = tools()
    tr = _trip_or_404(t, trip_id)
    good = [m for m in t.get_trip_moments(trip_id) if m["verdict"] == "handled_well"]
    lines = [f"Rating review request: trip {tr['trip_id']}, {tr['date']} {tr['start_time']}, "
             f"{tr['pickup']} to {tr['dropoff']}.",
             f"Rider rating: {tr['rider_rating']} stars (simulated). Rider comment: \"{tr['rider_comment']}\"",
             "", "What the dashcam shows:"]
    for m in good:
        lines.append(f"- {_fmt_range(m)}, {m['scenario_title']}: {m['what_happened']} "
                     f"Camera description: \"{m['evidence_quote']}\"")
    lines += ["", f"Dashi safety score for this trip: {tr['safety_score']}/100.",
              "This review was produced by AI from the dashcam video and is offered as evidence, "
              "not as a finding of fault. The clips are attached."]
    packet = {"trip_id": trip_id, "subject": f"Rating review for trip {trip_id}",
              "text": "\n".join(lines), "moments": good, "simulated": True}
    if body.send:
        ref = _sent_evidence.setdefault(trip_id, "RR-" + uuid.uuid4().hex[:6].upper())
        packet.update(sent=True, reference=ref, sent_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    else:
        packet.update(sent=trip_id in _sent_evidence, reference=_sent_evidence.get(trip_id))
    return packet


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
