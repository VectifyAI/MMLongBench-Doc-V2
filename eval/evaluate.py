"""Score a predictions file against MMLongBench-Doc-V2.

Scoring is a single LLM judge. For each question it is given the reference answer and
the system's full response, and asked whether the response gives the same answer. The
verdict is binary; accuracy and F1 are computed from those verdicts.

v1's pipeline — GPT-4o extracting a short answer, then exact match / isclose / ANLS /
sorted-list comparison — is not used here. It cost correct answers for reasons that had
nothing to do with the document: `Operating Activities` lost to `Operations activities`,
`1,358,000` lost to `1358000`, `Industrial` lost to `Industrial Business`, and four
questions were unscoreable outright because their `answer_format` did not admit their
own reference answer.

Predictions file: a JSON list of objects with at least

    {"doc_id": "...", "question": "...", "response": "<the system's full answer text>"}

matched to data/samples.json on (doc_id, question). Pass the full response — the judge
reads what the system actually said, not a summary of it.

Usage:
    export OPENAI_API_KEY=...            # or: export OPENROUTER_API_KEY=...
    python -m eval.evaluate predictions.json --out scored.json

If OPENAI_API_KEY is unset and OPENROUTER_API_KEY is set, the judge runs through
OpenRouter instead, using the same model.

Resumable: rerunning with the same --out reuses verdicts already recorded.
"""

import argparse
import asyncio
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from eval.judge import judge_all  # noqa: E402
from eval.metrics import acc_and_f1, scoreable, show_results  # noqa: E402


def key(s):
    return (s["doc_id"], " ".join(str(s["question"]).split()))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("predictions")
    ap.add_argument("--samples", default=os.path.join(ROOT, "data/samples.json"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--judge_model", default=None,
                    help="default: the provider's own slug for the pinned judge model")
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()

    if not (os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")):
        sys.exit("set OPENAI_API_KEY (or OPENROUTER_API_KEY) — the judge needs one.")

    samples = {key(s): s for s in json.load(open(args.samples))}
    preds = json.load(open(args.predictions))
    out = args.out or args.predictions.replace(".json", "_scored.json")

    rows, unmatched = [], 0
    for p in preds:
        gold = samples.get(key(p))
        if gold is None:
            unmatched += 1
            continue
        rows.append({**gold, "response": p.get("response", "")})
    if unmatched:
        print(f"warning: {unmatched} predictions matched no sample and were dropped")
    missing = len(samples) - len(rows)
    if missing:
        print(f"warning: {missing} of {len(samples)} samples have no prediction "
              f"— reported numbers cover only the {len(rows)} answered")

    # resume: reuse verdicts from a previous partial run
    if os.path.exists(out):
        prior = {key(x): x.get("llm_judge") for x in json.load(open(out))}
        for r in rows:
            v = prior.get(key(r))
            if v:
                r["llm_judge"] = v

    save = lambda: json.dump(rows, open(out, "w"), indent=2)
    todo = sum(1 for r in rows if "llm_judge" not in r)
    print(f"judging {todo} of {len(rows)} rows...", flush=True)
    asyncio.run(judge_all(rows, args.judge_model, args.concurrency,
                          on_checkpoint=lambda _: save()))
    save()

    acc, f1 = acc_and_f1(rows)
    n_scored = len(scoreable(rows))
    print("\n" + "=" * 62)
    print(f"samples scored : {n_scored}")
    if len(rows) - n_scored:
        print(f"  excluded     : {len(rows) - n_scored} corpus_defect "
              f"(no answer recoverable from the distributed corpus)")
    print(f"accuracy       : {acc:.4f}")
    print(f"F1             : {f1:.4f}")
    print(f"\nwrote {out}")

    txt = out.replace(".json", ".txt")
    try:
        show_results(rows, show_path=txt)
        print(f"      {txt}")
    except Exception as e:
        print(f"      (show_results failed: {type(e).__name__}: {e})")


if __name__ == "__main__":
    main()
