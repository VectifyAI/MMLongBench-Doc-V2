"""Label every question with a task type and whether it needs non-textual perception.

Produces data/question_types.json — two facets the upstream metadata does not carry:

  task_type        what operation the question demands (lookup / count / enumerate /
                   compare / derive / verify). Cuts across answer_format: "how many"
                   and "list them" are both List-or-Int in the schema but fail for
                   different reasons.

  requires_visual  whether answering needs a property plain text extraction cannot
                   carry. This is NOT the same as evidence_sources containing Chart or
                   Figure: on this corpus 237 of the 478 Chart/Figure questions are
                   answerable straight from the text layer (the number is printed as a
                   chart label), while 75 questions not marked Chart/Figure do need the
                   rendered page. Filtering a "visual" subset on evidence_sources alone
                   therefore mixes in a large share of pure-text questions.

Labels are model-produced and not human-verified. They are kept out of samples.json so
that our inferences stay separable from upstream's hand annotation, and so the ground
truth can be read by v1 tooling unchanged.

Usage:
    export OPENAI_API_KEY=...
    python -m eval.classify_questions data/samples.json --out data/question_types.json
"""
import asyncio, json, os, sys, time
from openai import AsyncOpenAI

MODEL, EFFORT = "gpt-5.6-luna", "low"
SCHEMA = {
  "type":"object",
  "properties":{
    "task_type":{"type":"string","enum":["lookup","count","enumerate","compare","derive","verify"]},
    "requires_visual":{"type":"boolean"},
    "reason":{"type":"string"}},
  "required":["task_type","requires_visual","reason"],
  "additionalProperties":False}

PROMPT = """Classify one question from a document-QA benchmark. Judge the question as written; the
reference answer and evidence metadata are context, not the thing being classified.

<question>{q}</question>
<reference_answer>{a}</reference_answer>
<evidence_sources>{src}</evidence_sources>

task_type -- the operation the question demands. Pick exactly one:
- lookup     : read back one stated fact or value.
- count      : produce a number by counting occurrences of something.
- enumerate  : produce the complete set of members ("list all", "what are the ...").
- compare    : pick the max/min/rank among alternatives, or state which of several is greater.
- derive     : compute a new value from two or more retrieved values (ratio, difference, sum,
               percentage change, average).
- verify     : a yes/no judgement about whether a stated claim holds.

Counting how many members a set has is `count`; naming them is `enumerate`. A superlative over
values already printed is `compare`; one that needs arithmetic first is `derive`.

requires_visual -- true only if answering needs a property a plain text extraction cannot carry:
colour, shape, position/layout, an icon's presence, or the content of a photograph or diagram.
False when the answer is a number, name, or phrase that appears in the document's text, even if
that text sits inside a chart or table. "How many charts are in the report" is true (you must see
the pages); "what percentage did group X report" is false (the label is text)."""

async def one(cli, sem, s, st):
    async with sem:
        for k in range(3):
            try:
                r = await cli.responses.create(model=MODEL, reasoning={"effort":EFFORT},
                    text={"format":{"type":"json_schema","name":"c","schema":SCHEMA,"strict":True}},
                    input=PROMPT.format(q=" ".join(s["question"].split()),
                                        a=str(s["answer"])[:300], src=s.get("evidence_sources","")))
                v=json.loads(r.output_text); break
            except Exception as e:
                if k==2: v={"task_type":"lookup","requires_visual":False,"reason":f"failed: {e}"}
                else: await asyncio.sleep(2*(k+1))
        s["task_type"]=v["task_type"]; s["requires_visual"]=v["requires_visual"]
        st["n"]+=1
        if st["n"]%100==0: print(f"  {st['n']}/{st['tot']}", flush=True)
        return s

async def main():
    import argparse
    ap=argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("samples", nargs="?", default="data/samples.json")
    ap.add_argument("--out", default="data/question_types.json")
    ap.add_argument("--concurrency", type=int, default=24)
    a=ap.parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set.")
    d=json.load(open(a.samples))
    if os.path.exists(a.out):                       # resume
        prior={(x["doc_id"], " ".join(x["question"].split())): x for x in json.load(open(a.out))}
        for s in d:
            k=(s["doc_id"], " ".join(s["question"].split()))
            if k in prior:
                s["task_type"]=prior[k]["task_type"]; s["requires_visual"]=prior[k]["requires_visual"]
    todo=[s for s in d if "task_type" not in s]
    cli=AsyncOpenAI(); sem=asyncio.Semaphore(a.concurrency); st={"n":0,"tot":len(todo)}
    print(f"classifying {len(todo)} of {len(d)} with {MODEL} (effort={EFFORT})")
    if todo: await asyncio.gather(*[one(cli,sem,s,st) for s in todo])
    json.dump([{"doc_id":s["doc_id"],"question":s["question"],
                "task_type":s["task_type"],"requires_visual":s["requires_visual"]} for s in d],
              open(a.out,"w"), indent=2)
    print(f"wrote {len(d)} labels -> {a.out}")


if __name__ == "__main__":
    asyncio.run(main())
