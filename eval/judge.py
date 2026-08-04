"""LLM-as-judge: does the response give the same answer as the reference?

Why this exists. v1 scored by comparing one extracted string against one reference
string: exact match for Int, isclose for Float, ANLS>=0.5 for Str, and for List a
sorted comparison that degrades to exact match whenever the first element is numeric.
That lost answers that were right but worded differently ("White Adults" vs "White",
"Operating Activities" vs "Operations activities", "1,358,000" vs 1358000,
"Industrial" vs "Industrial Business"), and it could not see an answer that the GPT-4o
extractor collapsed on the way out. V2 drops that pipeline; this judge is the metric.

What it does NOT do. It never reads the source document. The reference answer is given
and treated as correct, so this is a pure semantic-equivalence call between a reference
and a response. That is deliberate: a document-reading judge fails on image-only PDFs,
truncated text layers and mojibake, and then confidently reports fabrication that did
not happen. There is nothing here it can fail to see.

The judge only ever asks "does this response mean the reference". It cannot invent a
new correct answer, and it never sees another system's output, so verdicts do not drift
with the field. Run it over every row.

Provider. Uses OPENAI_API_KEY against the OpenAI Responses API when it is set. If it
is not, and OPENROUTER_API_KEY is, it falls back to OpenRouter's chat-completions
endpoint with the equivalent model slug, so any OpenRouter-hosted model can be used as
the judge without an OpenAI account. Both paths request the same reasoning effort and
the same strict JSON schema.

Usage:
    export OPENAI_API_KEY=...            # or: export OPENROUTER_API_KEY=...
    python -m eval.judge predictions_scored.json --out judged.json

Input rows need: question, answer, answer_format, response.
Adds `llm_judge: {equivalent: bool, abstained: bool, reason: str}` to each row.
"""

import argparse
import asyncio
import json
import os
import time

from openai import AsyncOpenAI

MODEL = "gpt-5.6-luna"                       # OpenAI
OPENROUTER_MODEL = "openai/gpt-5.6-luna"     # same model, OpenRouter slug
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
EFFORT = "high"
MAX_RESPONSE_CHARS = 12000


def make_client(api_key=None):
    """Pick a provider. Returns (client, backend, default_model).

    OpenAI wins when its key is present; OpenRouter is the fallback. OpenRouter does not
    serve the Responses API, so that backend goes through chat completions instead.
    """
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if key:
        return AsyncOpenAI(api_key=key), "openai", MODEL
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return (AsyncOpenAI(api_key=key, base_url=OPENROUTER_BASE),
                "openrouter", OPENROUTER_MODEL)
    raise RuntimeError("set OPENAI_API_KEY or OPENROUTER_API_KEY")

SCHEMA = {
    "type": "object",
    "properties": {
        "equivalent": {
            "type": "boolean",
            "description": "true if the response conveys the same answer as the reference",
        },
        "abstained": {
            "type": "boolean",
            "description": "true if the response committed to no answer at all",
        },
        "reason": {"type": "string", "description": "One short sentence."},
    },
    "required": ["equivalent", "abstained", "reason"],
    "additionalProperties": False,
}

PROMPT = """Decide whether a document-QA system's response gives the same answer as the reference.

<question>{question}</question>
<reference_answer>{answer}</reference_answer>
<expected_format>{answer_format}</expected_format>

<system_response>
{response}
</system_response>

Treat the reference answer as correct. Judge the answer the RESPONSE actually gives — its stated
conclusion — not how a string matcher would score it. Formatting, verbosity, markdown, tables and
surrounding explanation are irrelevant; extract the answer the response commits to and compare it
to the reference.

Answer "equivalent": true when the substance matches and only the surface differs:
- wording, case, pluralisation, word order, punctuation, dashes vs hyphens
- added or omitted qualifiers that do not change the referent
  ("White Adults" vs "White", "Rear Admiral Tim Ziemer" vs "Tim Ziemer")
- numeric formatting, thousands separators, units, %, currency symbols, rounding
  that leaves the value the same ("18.3" vs "18.29%", "1,175,000" vs "1175000")
- a list with the same members in a different order, or members phrased differently
- the correct answer stated plainly, even if buried in a long explanation
- the response gives the correct answer as an explicit, reasoned alternative alongside
  another figure — e.g. "5 under a strict reading; including the two year-specific
  charts it is 7" when the reference is 7. The system found the right answer and said
  so; which reading it headlines is a presentation choice.

Answer "equivalent": false when the substance differs:
- a different value, entity, date, or count
- a list missing members, containing extra members, or with different members
- an answer at the wrong granularity or about the wrong thing
- the response declines, says it cannot read the document, or gives no answer
- the response enumerates many values without analysis and the reference merely
  appears among them (a shotgun answer, e.g. dumping a whole table row)

Before deciding, strip anything the response itself sets outside its answer. An item is
segregated when the response marks it as conditional, borderline, footnote-only, excluded by the
question's stated criteria, or offered under a second reading — "plus X if you count the
footnote", "X only if year-specific charts are included", "under a strict reading it is 5". Such
items are NOT members of the answer. Judge what remains after removing them, and do this
regardless of where they sit: a caveat in the closing clause, a separate bullet, and a labelled
section are the same thing. Whether the response reads as equivalent must not depend on the
layout it chose.

Concretely: a response listing exactly the reference members and then separately flagging one
further item as outside the criteria IS equivalent — the flag is the response excluding it. The
same item presented as an ordinary member of the same list, with no signal that it is different
from the others, is NOT. Segregation must be explicit; a member is not excluded merely because
the response is unsure about it. When a response gives two readings and the reference matches
either one, that is equivalent — which reading it headlines is a presentation choice.

This never rescues a wrong core answer. Remove the segregated items first; if what remains still
differs from the reference in value, count, or membership, it is not equivalent.

When the reference answer is exactly "Not answerable", the question is unanswerable from the
document and a correct response says so. The test is whether the response commits to an answer to
the question AS ASKED. Explaining the refusal is part of a good refusal, not a substitute answer —
all of these stay equivalent: naming what the document says instead of what was asked ("the
decline was among Republicans, not Democrats"), identifying which premise fails, saying the term
or entity does not appear, or citing the pages it checked. Do not penalise a decline for being
well-reasoned or specific.

It is NOT equivalent when the response supplies a value and lets it stand as the answer: "the
document doesn't give X, but the closest figure is 42", a count such as zero offered as the count,
or a yes/no verdict on the asked question after a nominal decline. The question to ask yourself is
whether a reader would come away with an answer to what was asked, or with the understanding that
the document does not answer it.

Be strict about substance. Do not credit a response for being close, well-argued, or confident,
and do not credit a bare mention of the right value in passing. But do credit a response that
identifies the reference answer and explains it, even if it headlines a different reading.

Separately, set "abstained": true if the response commits to no answer at all — it says the
document does not contain the information, says it cannot read the document, or otherwise declines.
A decline that explains itself is still a decline; reasoning about why the premise fails does not
make it an answer. Set it false only if the response supplies a value and lets it stand as the
answer to the question asked. This is independent of "equivalent": a response can
abstain correctly (equivalent true, abstained true, when the reference is "Not answerable") or
abstain wrongly (equivalent false, abstained true)."""


async def judge_one(client, sem, s, model, state, backend="openai", effort=EFFORT):
    """Never raises. On repeated failure, records equivalent=false with the error."""
    async with sem:
        prompt = PROMPT.format(
            question=" ".join(s["question"].split()),
            answer=s["answer"],
            answer_format=s["answer_format"],
            response=str(s.get("response", ""))[:MAX_RESPONSE_CHARS],
        )
        for attempt in range(3):
            try:
                if backend == "openrouter":
                    r = await client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_schema",
                                         "json_schema": {"name": "verdict",
                                                         "schema": SCHEMA,
                                                         "strict": True}},
                        extra_body={"reasoning": {"effort": effort}},
                    )
                    txt = r.choices[0].message.content
                    if not txt:
                        raise ValueError(f"empty output ({r.choices[0].finish_reason})")
                else:
                    r = await client.responses.create(
                        model=model,
                        reasoning={"effort": effort},
                        text={"format": {"type": "json_schema", "name": "verdict",
                                         "schema": SCHEMA, "strict": True}},
                        input=prompt,
                    )
                    txt = r.output_text
                    if not txt:
                        raise ValueError(f"empty output (status={r.status})")
                v = json.loads(txt)
                break
            except Exception as e:
                if attempt == 2:
                    v = {"equivalent": False, "abstained": False,
                         "reason": f"judge failed: {type(e).__name__}: {e}"}
                else:
                    await asyncio.sleep(2 * (attempt + 1))
        s["llm_judge"] = v
        state["done"] += 1
        el = time.time() - state["t0"]
        eta = (state["total"] - state["done"]) / (state["done"] / el) / 60 if el else 0
        print(f"[{state['done']}/{state['total']}] {'EQUIV' if v['equivalent'] else '  no ':<6} "
              f"gt={str(s['answer'])[:30]!r:<32} eta={eta:.0f}m", flush=True)
        return s


async def judge_all(samples, model=None, concurrency=8, api_key=None, on_checkpoint=None):
    """Judge every row lacking `llm_judge`. Mutates and returns `samples`.

    `model=None` takes the provider's default; pass a string to override.
    """
    todo = [s for s in samples if "llm_judge" not in s]
    if not todo:
        return samples
    client, backend, default_model = make_client(api_key)
    model = model or default_model
    print(f"judge: {model} via {backend}", flush=True)
    state = {"done": 0, "total": len(todo), "t0": time.time()}
    sem = asyncio.Semaphore(concurrency)
    tasks = [asyncio.create_task(judge_one(client, sem, s, model, state, backend))
             for s in todo]
    n = 0
    for f in asyncio.as_completed(tasks):
        await f
        n += 1
        if on_checkpoint and n % 10 == 0:
            on_checkpoint(samples)
    return samples


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("results", help="JSON list with question/answer/answer_format/response")
    ap.add_argument("--out", default=None)
    ap.add_argument("--model", default=None, help="default: provider's own slug")
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()

    samples = json.load(open(args.results))
    out = args.out or args.results.replace(".json", "_judged.json")

    # resume from a previous partial run
    if os.path.exists(out):
        prior = {(x["doc_id"], x["question"]): x.get("llm_judge")
                 for x in json.load(open(out))}
        for x in samples:
            v = prior.get((x["doc_id"], x["question"]))
            if v:
                x["llm_judge"] = v

    save = lambda rows: json.dump(rows, open(out, "w"), indent=2)
    asyncio.run(judge_all(samples, args.model, args.concurrency, on_checkpoint=save))
    save(samples)

    eq = sum(1 for x in samples if x["llm_judge"]["equivalent"])
    print(f"\njudged {len(samples)} | equivalent {eq} ({eq / len(samples):.1%})\nwrote {out}")


if __name__ == "__main__":
    main()
