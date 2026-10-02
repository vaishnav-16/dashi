# cd dashi/app && ../.venv/bin/python ../eval/run_eval.py
"""Score the Dashi classifier against hand labels (eval/labels.json) with weave.Evaluation."""
import asyncio
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import clients  # noqa: E402
import core  # noqa: E402

try:
    import weave
    weave.init(f"{clients.setting('WANDB_TEAM')}/{clients.setting('WANDB_PROJECT')}")
    op = weave.op
except Exception as e:  # noqa: BLE001
    print("weave unavailable:", str(e)[:120])
    weave = None
    op = core.op

PB = core.load_playbook()
vss = clients.VSS()
_seg_cache = {}


def chunk_of(source):
    base = re.sub(r"_segment_\d+_of_\d+", "", source.split("/")[-1])
    return f"s3://{clients.setting('S3_CHUNKS_BUCKET')}/{clients.setting('USERNAME')}/{base}"


def find_segment(source, captions_file):
    ov = chunk_of(source)
    caps = json.loads((ROOT / captions_file).read_text()) if (ROOT / captions_file).exists() else {}
    segs = caps.get(ov)
    if segs is None:
        segs = _seg_cache.get(ov) or vss.get("tools/segments", original_video=ov)["segments"]
        _seg_cache[ov] = segs
    for s in segs:
        if s["source"] == source or s["source"].split("/")[-1] == source.split("/")[-1]:
            return s
    return None


def build_rows(labels, captions_file="captions_before.json"):
    rows = []
    for lab in labels:
        s = find_segment(lab["source"], captions_file)
        if s is None:
            print("no caption for", lab["source"].split("/")[-1])
            continue
        rows.append({"source": lab["source"], "caption": s.get("reasoning_content") or "",
                     "counts": core._counts(s.get("object_counts")), "segment": int(s["segment_number"]),
                     "start_sec": float(s["segment_start_sec"]),
                     "expected_scenario": lab["expected_scenario"], "expected_verdict": lab["expected_verdict"]})
    return rows


@op
def dashi_classifier(caption, counts, segment, start_sec, source):
    seg = {"segment": segment, "start_sec": start_sec, "end_sec": start_sec + 5, "source": source,
           "caption": caption, "counts": counts, "people": int(counts.get("person", 0)), "vehicles": 0}
    kept = core.validate(core.classify_batch([seg], PB), [seg], PB)
    if not kept:
        return {"scenario_id": "none", "verdict": "none", "confidence": 0.0, "evidence_quote": "", "what_happened": ""}
    k = kept[0]
    return {key: k[key] for key in ("scenario_id", "verdict", "confidence", "evidence_quote", "what_happened")}


@op
def scenario_match(expected_scenario, output):
    return {"correct": output["scenario_id"] == expected_scenario}


@op
def verdict_match(expected_verdict, output):
    return {"correct": output["verdict"] == expected_verdict}


@op
def false_alarm(expected_scenario, output):
    return {"false_alarm": expected_scenario == "none" and output["scenario_id"] != "none"}


@op
def grounded(caption, output):
    if output["verdict"] == "none":
        return {"grounded": None}
    try:
        r = clients.llm(timeout=30).chat.completions.create(
            model=clients.MODEL, temperature=0, max_tokens=150, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": 'Does the STATEMENT state only facts that are present in the CAPTION? Answer strict JSON {"grounded": true|false, "reason": "<one sentence>"}.'},
                      {"role": "user", "content": json.dumps({"CAPTION": caption, "STATEMENT": output["what_happened"]})}])
        return {"grounded": bool(json.loads(r.choices[0].message.content).get("grounded"))}
    except Exception:  # noqa: BLE001
        return {"grounded": None}


def local_numbers(rows):
    per = []
    for r in rows:
        out = dashi_classifier(r["caption"], r["counts"], r["segment"], r["start_sec"], r["source"])
        per.append((r, out, grounded(r["caption"], out)["grounded"]))
    n = len(per)
    none_rows = [p for p in per if p[0]["expected_scenario"] == "none"]
    flagged = [p for p in per if p[1]["verdict"] != "none"]
    g = [p for p in flagged if p[2] is not None]
    return per, {
        "n": n,
        "scenario_acc": sum(p[1]["scenario_id"] == p[0]["expected_scenario"] for p in per) / max(1, n),
        "verdict_acc": sum(p[1]["verdict"] == p[0]["expected_verdict"] for p in per) / max(1, n),
        "false_alarm": (sum(p[1]["scenario_id"] != "none" for p in none_rows) / len(none_rows)) if none_rows else None,
        "n_none": len(none_rows),
        "grounded": (sum(bool(p[2]) for p in g) / len(g)) if g else None,
        "n_flagged": len(flagged),
    }


def pct(x):
    return "n/a" if x is None else f"{round(100 * x)}%"


def main():
    lp = ROOT / "eval" / "labels.json"
    res = ROOT / "eval" / "results.md"
    if not lp.exists():
        res.write_text("# Dashi eval results\n\nEval harness ready; labels not completed in time.\n")
        print("no labels.json; wrote placeholder results.md")
        return
    labels = json.loads(lp.read_text())
    rows = build_rows(labels)
    eval_note = "Weave unavailable."
    if weave is not None:
        try:
            ev = weave.Evaluation(name="dashi-classifier", dataset=rows,
                                  scorers=[scenario_match, verdict_match, false_alarm, grounded])
            print(asyncio.run(ev.evaluate(dashi_classifier)))
            eval_note = f"Weave project: https://wandb.ai/{clients.setting('WANDB_TEAM')}/{clients.setting('WANDB_PROJECT')}/weave (evaluation `dashi-classifier`)."
        except Exception as e:  # noqa: BLE001
            eval_note = f"Weave evaluation failed: {str(e)[:120]}"
    per, num = local_numbers(rows)
    md = ["# Dashi eval results", "",
          "Method: a teammate watched each 5 s segment and labelled the scenario and verdict from the video.",
          "The classifier (same prompt, validation and confidence floor as the app pipeline) saw only the caption and YOLO counts.",
          "Groundedness is an LLM judge checking that `what_happened` states only facts in the caption.", "",
          "| metric | value |", "|---|---|",
          f"| n (labelled segments) | {num['n']} |",
          f"| scenario accuracy | {pct(num['scenario_acc'])} |",
          f"| verdict accuracy | {pct(num['verdict_acc'])} |",
          f"| false-alarm rate (of {num['n_none']} labelled none) | {pct(num['false_alarm'])} |",
          f"| groundedness (of {num['n_flagged']} flagged) | {pct(num['grounded'])} |",
          f"| model | `{clients.MODEL}` |", "", eval_note, "",
          "| segment | expected | predicted | confidence |", "|---|---|---|---|"]
    for r, o, _ in per:
        md.append(f"| `{r['source'].split('/')[-1]}` | {r['expected_scenario']} / {r['expected_verdict']} | "
                  f"{o['scenario_id']} / {o['verdict']} | {o['confidence']:.2f} |")
    md += ["", f"Measured on {num['n']} hand-labelled clips; labels from watching video, predictions from captions only.", ""]
    after_rows = [r for r in build_rows(labels, "captions_after.json")
                  if chunk_of(r["source"]) in json.loads((ROOT / "captions_after.json").read_text())] \
        if (ROOT / "captions_after.json").exists() else []
    if after_rows:
        _, a = local_numbers(after_rows)
        md.append(f"Before/after re-ingest on {a['n']} rows: verdict accuracy after = {pct(a['verdict_acc'])}.")
    else:
        md.append("Before/after eval: not run (re-ingested chunk not in labels).")
    res.write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
