# MMLongBench-Doc-V2

A corrected-annotation, semantics-aware version of MMLongBench-Doc, you can find a technical report [here](https://arxiv.org/abs/2608.03397).

Two changes from v1, both aimed at the same thing — making the score reflect whether the system
actually answered the question:

1. **106 ground-truth annotations corrected.** Each was checked against the source PDF, and the
   check itself — page, figures, arithmetic — is written into the entry, so you can disagree with
   the reasoning rather than just the verdict. Every change is listed in
   [`data/corrections/`](data/corrections/), alongside upstream's original file so the diff can be
   reproduced. Ten further questions are **removed** rather than scored: their document ships under
   the wrong filename, so no system can answer them and no key is recoverable.
2. **An LLM judge replaces the string metric.** v1 extracted a short answer with GPT-4o and then
   compared strings, so `Operating Activities` lost to `Operations activities` and `1,358,000` lost
   to `1358000`. V2 asks a judge whether the response *means* the reference.

Because the metric changed, **V2 numbers are not comparable with published V1 numbers.** They are
higher for the same system, and the gap is not uniform — it is largest wherever answers are lists
or free text.

## Contents

```
data/
  samples.json          1,071 questions with corrected ground truth
  question_types.json   per-question task_type + requires_visual (model-labelled)
  corrections/          everything that differs from v1
    README.md             the 106 changes as a table, by category and by field
    corrections.json      each change with its evidence and reasoning
    diff.json             plain field-level before/after
    samples_v1.json       upstream's original file, for independent diffing
eval/                   judge.py, metrics.py, evaluate.py, classify_questions.py
```

`data/samples.json` is the ground truth: **1,071 questions over 134 documents.** It is upstream's
`samples.json` with 106 rows corrected, one duplicate row removed, and the ten unanswerable-by-
construction rows dropped, and it keeps the same filename and schema so v1 tooling reads it
unchanged. The duplicate is a v1 defect: the same question appears twice under
`PRE_2022.09.29_NSL-politics_REPORT.pdf` with contradictory answers, which makes
`(doc_id, question)` non-unique and silently drops a row from any keyed join. The ten dropped rows
all belong to one document, so V2 covers 134 of upstream's 135 PDFs.

## Install

```bash
pip install -r requirements.txt
```

### The documents

The 134 source PDFs are **not** redistributed here. Download them from upstream:

<https://github.com/mayubo2333/MMLongBench-Doc/tree/main/data/documents>

`data/samples.json` refers to them by `doc_id`, which is the PDF filename. Put them wherever your
system reads documents from — `data/documents/` is gitignored if you want them alongside the
questions. Nothing in `eval/` opens them: scoring only ever sees the question, the reference
answer and your system's response.

## Evaluate

Produce a predictions file — a JSON list where each row carries the system's **full response
text**, not a pre-extracted short answer:

```json
[
  {"doc_id": "COSTCO_2021_10K.pdf",
   "question": "what is total debt of COSTCO in FY 2021?Answer in millions.",
   "response": "Total debt is $11,407 million: long-term debt of 6,692 plus ..."}
]
```

Then:

```bash
export OPENAI_API_KEY=...            # or: export OPENROUTER_API_KEY=...

python -m eval.evaluate predictions.json --out scored.json
```

Output:

```
==============================================================
samples scored : 1071
accuracy       : 0.####
F1             : 0.####
```

Writes a per-row JSON with every verdict, and a `.txt` breakdown by single-page / cross-page /
unanswerable, by evidence source, and by document type. Resumable: rerunning with the same `--out`
reuses verdicts already recorded.

## Question types

`data/question_types.json` labels every question on two facets the upstream metadata does not
carry. Join on `(doc_id, question)`.

| `task_type` | n | What the question demands |
|---|---|---|
| `lookup` | 487 | Read back one stated fact or value. |
| `count` | 234 | Produce a number by counting occurrences. |
| `enumerate` | 122 | Produce the complete set of members. |
| `derive` | 122 | Compute a new value from two or more retrieved values. |
| `compare` | 89 | Pick the max/min/rank among alternatives. |
| `verify` | 17 | A yes/no judgement about whether a claim holds. |

`requires_visual` (314 of 1,071) marks questions that need a property plain text extraction cannot
carry — colour, shape, layout, an icon's presence, the content of a photo or diagram.

**It is not the same as `evidence_sources` containing Chart or Figure**, and the gap is large:
of the questions marked Chart/Figure, **231 are answerable straight from the text layer** (the
figure is an image, but the number you need is printed as a chart label that extraction picks up),
while **75 questions not marked Chart/Figure do need the rendered page** — typically meta-questions
like "how many bar charts are in the report". Selecting a "visual" subset on `evidence_sources`
alone therefore mixes in a large share of pure-text questions, and misses genuinely visual ones.

These labels are **model-produced and not human-verified** — `gpt-5.6-luna` at `low` effort, one
pass, prompt in [`eval/classify_questions.py`](eval/classify_questions.py). Treat them as a
convenience for slicing results, not as ground truth. Regenerate with:

```bash
python -m eval.classify_questions data/samples.json --out data/question_types.json
```

## The metric

Each row is judged once. The judge is given the question, the reference answer, the expected
format and the system's **full response**, and returns a binary verdict plus an `abstained` flag.

    accuracy  = fraction judged equivalent
    recall    = fraction judged equivalent, over answerable questions
    precision = correct answerable / questions the system actually answered
    F1        = harmonic mean

Same definitions v1 used. The one substitution: v1 decided whether a system had abstained by
testing `pred == "Not answerable"` on the extractor's output; V2 reads it off the response itself.
Precision counts a confident wrong answer to an unanswerable question against the system, which is
what stops "always guess" from scoring well.

Three properties make the judge usable as a benchmark metric:

- **It never reads the document.** It is given the reference answer, told to treat it as correct,
  and asked only whether the response says the same thing. A document-reading judge fails on
  image-only PDFs, truncated text layers and mojibake, and then reports fabrication that did not
  happen — this one has nothing it can fail to see. It also cannot invent a new correct answer:
  the reference is the only thing it can agree with.
- **The rubric is explicit.** Wording, case, units, thousands separators, list order and
  surrounding prose are free. A different value, a list with missing or extra members, a decline,
  or a shotgun enumeration that merely contains the reference are not. For `Not answerable`
  references, only a clean decline counts — a decline that then offers a nearest figure has
  supplied an answer.
- **It is pinned.** `gpt-5.6-luna` at high reasoning effort with a strict JSON schema. Report the
  judge model alongside any score; `--judge_model` overrides it.

### Providers

`OPENAI_API_KEY` is used when present, against the Responses API. If it is unset and
`OPENROUTER_API_KEY` is set, the judge routes through OpenRouter's chat-completions endpoint as
`openai/gpt-5.6-luna` — same model, same reasoning effort, same strict schema, no OpenAI account
needed. `--judge_model` accepts any slug the active provider serves, so OpenRouter also makes it
easy to swap the judge for a different model entirely.

The two paths are not bit-identical: OpenRouter has no Responses API, so that backend sends
`response_format: json_schema` on chat completions with `reasoning.effort` in the body. Quote the
provider along with the model when reporting a score.

## What changed in the data

By `dispute_type`:

| `dispute_type` | n | Meaning |
|---|---|---|
| `wrong_answer` | 26 | The question is sound, but the recorded answer is not what the document says. |
| `defective_question` | 19 | The question itself is broken — wrong page, wrong year, a typo, a false premise, or singular phrasing over a multi-part answer. V2 rewords it and keeps the answer. |
| `ambiguous_question` | 19 | Two readings are both defensible and the recorded answer only fits one. V2 states the intended reading in the question. |
| `should_be_answerable` | 14 | Labelled `Not answerable`, but the document contains a determinate answer. |
| `incomplete_answer` | 16 | The recorded key omits members, or omits a form of the answer that is equally correct. |
| `corpus_defect` | 10 | No answer is recoverable from the distributed corpus at all. Removed from `samples.json` rather than counted wrong. |
| `should_be_unanswerable` | 2 | An answer is recorded, but the document does not support one. |

38 of the 106 change the question text rather than the answer. That is deliberate: where the
document genuinely supports two readings, pinning the intended one in the question is more honest
than declaring one of them wrong.

Each entry in `data/corrections/corrections.json` carries the original annotation
(`benchmark_answer`, `benchmark_answer_format`, `benchmark_evidence_pages`), the correction
(`manual_answer`, `manual_answer_format`, `manual_evidence_pages`), and a `note` quoting the page
or showing the arithmetic. Examples:

- `BESTBUY_2023_10K.pdf` — "change of gross margins from FY2022 to FY2021" was recorded as
  `1.08%`, which is the FY2022→**FY2023** change. FY2022→FY2021 is 0.12 percentage points.
- `BESTBUY_2023_10K.pdf` — "interest coverage ratio for **AMCOR** FY2020" in a Best Buy 10-K.
  The recorded `51.286` is Best Buy's own FY2023 figure (operating income 1,795 ÷ interest 35).
- `AMAZON_2017_10K.pdf` — percentage change of the return allowance 2016→2017 recorded as `60.3%`;
  the allowance fell from 156 to 62, so the change is `-60.3%`.

Full detail, including the deliberate negative samples that were flagged and then left alone, and
a script to reproduce the diff against upstream, is in
[`data/corrections/README.md`](data/corrections/README.md).

Six questions are unscoreable under v1's string metric no matter what a system answers, because
their `answer_format` does not admit their own reference answer — `int("21%")` raises, `[]` under
`List` throws `IndexError`. `answer_format` is still carried for reference, but nothing scores on
it now, so these rows score normally in V2:

| doc | answer | format |
|---|---|---|
| `2401.18059v1.pdf` | `[]` | `List` |
| `05-03-18-political-release.pdf` | `21%` | `Int` |
| `germanwingsdigitalcrisisanalysis-…_95.pdf` | `13:51 CET` | `Int` |
| `STEPBACK.pdf` | `73.2%` | `Float` |
| `2309.17421v2.pdf` | `$49.99` | `Float` |
| `3M_2018_10K.pdf` | `$1577.00` | `Float` |

Corrections and disagreements are welcome; open an issue or a PR with the page that settles it.

## Internships

If you would like to work on this benchmark as an intern, please email your CV to
[mingtian@pageindex.ai](mailto:mingtian@pageindex.ai).

## Licence and attribution

Apache 2.0, inherited from upstream. The questions and the source PDFs come from
MMLongBench-Doc; `eval/` is new and contains no upstream code. See [`NOTICE`](NOTICE).

```bibtex
@article{ma2024mmlongbench,
  title={MMLongBench-Doc: Benchmarking Long-context Document Understanding with Visualizations},
  author={Ma, Yubo and Zang, Yuhang and Chen, Liangyu and others},
  journal={arXiv preprint arXiv:2407.01523},
  year={2024}
}
@article{zhang2026mmlongbenchdocv2,
   title={MMLongBench-Doc-V2: A Corrected-Annotation, Semantics-Aware Revision of MMLongBench-Doc}, 
   author={Mingtian Zhang},
   year={2026},
   eprint={2608.03397},
   url={https://arxiv.org/abs/2608.03397}, 
}
```
