"""Accuracy, F1 and the per-slice breakdown, computed from judge verdicts.

Same definitions v1 used, with one substitution. v1 derived both numbers from a
per-sample `score` produced by string matching, and decided whether the system had
abstained by testing `pred == "Not answerable"` on the extractor's output. Here the
score is the judge's binary verdict, and abstention is the judge's `abstained` flag —
read off the response itself rather than off a collapsed extraction.

    accuracy  = mean(score)
    recall    = mean(score) over answerable questions
    precision = (correct answerable) / (questions the system actually answered)
    F1        = harmonic mean

Precision counts a wrong answer to an unanswerable question against the system, which
is the point of the metric: it is what stops "always guess" from scoring well.
"""

from collections import defaultdict

UNANSWERABLE = "Not answerable"


def is_answerable(s):
    """Unanswerable keys all start with "Not answerable"; some also spell out the
    equally-correct empty-set wording ("Not answerable or none"), so match the prefix."""
    return not str(s["answer"]).startswith(UNANSWERABLE)


def score_of(s):
    v = s.get("llm_judge")
    return 1.0 if v and v.get("equivalent") else 0.0


def answered(s):
    """Did the system commit to an answer? Falls back to answered if unjudged."""
    v = s.get("llm_judge")
    return not (v and v.get("abstained"))


def scoreable(samples):
    """Every row in data/samples.json is scoreable; this is a compatibility shim.

    V2 used to ship ten unanswerable rows flagged `corpus_defect` -- one document ships under the
    wrong filename, so its questions describe content absent from the distribution -- and excluded
    them at scoring time. They are now removed from data/samples.json outright, so the filter is a
    no-op against the current file. It is kept so that predictions produced against the earlier
    1,081-row file still score correctly instead of counting those rows as failures. See
    data/corrections/ for the identification.
    """
    return [s for s in samples if not s.get("corpus_defect")]


def acc_and_f1(samples):
    rows = [s for s in scoreable(samples) if "llm_judge" in s]
    if not rows:
        return 0.0, 0.0
    acc = sum(score_of(s) for s in rows) / len(rows)

    pos = [s for s in rows if is_answerable(s)]
    hits = sum(score_of(s) for s in pos)
    n_answered = sum(1 for s in rows if answered(s))
    recall = hits / len(pos) if pos else 0.0
    precision = hits / n_answered if n_answered else 0.0
    f1 = 2 * recall * precision / (recall + precision) if (recall + precision) else 0.0
    return acc, f1


def as_list(v):
    if isinstance(v, list):
        return v
    try:
        return list(eval(v))
    except Exception:
        return []


def show_results(samples, show_path=None):
    """Overall / single-page / cross-page / unanswerable, then by source and doc type."""
    dropped = len(samples) - len(scoreable(samples))
    samples = scoreable(samples)
    acc, f1 = acc_and_f1(samples)
    lines = [
        f"Overall Acc: {acc} | Question Number: {len(samples)}",
        f"Overall F1-score: {f1} | Question Number: {len(samples)}",
        "-----------------------",
    ]
    if dropped:
        lines.insert(0, f"Excluded as corpus_defect: {dropped}")

    single = [s for s in samples if len(as_list(s["evidence_pages"])) == 1]
    multi = [s for s in samples
             if len(as_list(s["evidence_pages"])) != 1 and is_answerable(s)]
    neg = [s for s in samples if not is_answerable(s)]
    for name, sub in (("Single-page", single), ("Cross-page", multi),
                      ("Unanswerable", neg)):
        lines.append(f"{name} | Accuracy: {acc_and_f1(sub)[0]} | Question Number: {len(sub)}")
    lines.append("-----------------------")

    by_source, by_doctype = defaultdict(list), defaultdict(list)
    for s in samples:
        for src in as_list(s["evidence_sources"]):
            by_source[src].append(s)
        by_doctype[s["doc_type"]].append(s)
    for k, sub in by_source.items():
        lines.append(f"Evidence Sources: {k} | Accuracy: {acc_and_f1(sub)[0]} | "
                     f"Question Number: {len(sub)}")
    lines.append("-----------------------")
    for k, sub in by_doctype.items():
        lines.append(f"Document Type: {k} | Accuracy: {acc_and_f1(sub)[0]} | "
                     f"Question Number: {len(sub)}")

    text = "\n".join(lines) + "\n"
    if show_path:
        with open(show_path, "w") as f:
            f.write(text)
    return text
