# Where V2 differs from V1

Every annotation in `data/samples.json` that differs from upstream MMLongBench-Doc, and why.
**106 of v1's 1,082 questions are changed**; the rest are byte-identical to upstream.

Most were found the same way: a document-QA system answered the question, scored zero, and the
answer turned out on inspection to be right or at least as defensible as the key. Each was then
checked against the source PDF, and the check is written into the entry's `note` — the page, the
figures, and the arithmetic — so a reader can disagree with the reasoning rather than just the
verdict.

One structural change: v1 contains the same question twice under
`PRE_2022.09.29_NSL-politics_REPORT.pdf`, once answered `46%` and once `Not answerable`. Page 97
answers it, so both were resolved to `46%`, which left a duplicate `(doc_id, question)` key —
enough to silently drop a row from any keyed join. The second copy is removed. Ten further rows
are dropped as `corpus_defect` (below), so **V2 has 1,071 questions over 134 documents, to v1's
1,082 over 135.**

## Files

| File | What it is |
|---|---|
| `corrections.json` | The 106 changes, each with the original annotation, the correction, and a `note` giving the evidence. |
| `diff.json` | The same changes as a plain field-level before/after, no commentary. |
| `samples_v1.json` | Upstream's original `samples.json`, unmodified, so the diff can be reproduced independently. |

Reproduce the diff yourself — join on `(doc_id, question)` rather than by position, since V2 drops
11 rows (one duplicate, ten `corpus_defect`) and rewords 38 questions:

```python
import json
norm = lambda s: " ".join(str(s).split())
v1 = {(x["doc_id"], norm(x["question"])): x for x in json.load(open("data/corrections/samples_v1.json"))}
v2 = {(x["doc_id"], norm(x["question"])): x for x in json.load(open("data/samples.json"))}
corr = json.load(open("data/corrections/corrections.json"))

for c in corr:                              # each correction names both sides of the rename
    before = v1[(c["doc_id"], norm(c["question"]))]
    after  = v2.get((c["doc_id"], norm(c.get("manual_question") or c["question"])))
    if after is None:                       # corpus_defect: dropped from V2 entirely
        print(c["doc_id"], c["dispute_type"], "removed")
        continue
    changed = {k for k in ("answer", "answer_format", "evidence_pages")
               if str(before[k]) != str(after[k])}
    print(c["doc_id"], c["dispute_type"], changed or "question only")
```

## By category

| `dispute_type` | n | Meaning |
|---|---|---|
| `wrong_answer` | 26 | The question is sound, but the recorded answer is not what the document says. |
| `defective_question` | 19 | The question itself is broken — wrong page, wrong year, a typo, a false premise, or singular phrasing over a multi-part answer. V2 rewords it and keeps the answer. |
| `ambiguous_question` | 19 | Two readings are both defensible and the recorded answer only fits one. V2 states the intended reading in the question. |
| `should_be_answerable` | 14 | Labelled `Not answerable`, but the document contains a determinate answer. |
| `incomplete_answer` | 16 | The recorded key omits members, or omits a form of the answer that is equally correct. |
| `corpus_defect` | 10 | No answer is recoverable from the distributed corpus at all. Removed from `samples.json` rather than counted wrong. |
| `should_be_unanswerable` | 2 | An answer is recorded, but the document does not support one. |

## By field

| Field | Rows changed |
|---|---|
| `answer` | 74 |
| `question` | 38 |
| `evidence_pages` | 35 |
| `answer_format` | 19 |

`corpus_defect` rows are **not present in `samples.json`** — they are listed below and in
`corrections.json` as the record of why they were dropped. Their `manual_answer` is `None` because
no answer is recoverable, not because the answer is empty. All ten belong to one document, whose
distributed PDF is a different deck from the one the questions were written against, so V2 covers
134 of upstream's 135 PDFs. `eval/metrics.py` still filters on the flag, which makes predictions
produced against the earlier 1,081-row file score correctly rather than counting those rows as
failures.

Fourteen `Not answerable` keys were widened to `Not answerable or 0 or none`. The document does let
you determine that the set is empty in each case, so reporting "there are none" — or, for a
`how many`, the count `0` — says exactly what the key means. `eval/metrics.py` matches the
`Not answerable` prefix, so these rows still count in the unanswerable slice.

This was needed because the corpus keys the same shape two ways. Of the 287 upstream questions
beginning "how many", **14 are keyed `0`** for a thing that is simply absent — cats, tigers,
airplanes, blue arrows, GPT-4o, words starting with 'X' — while **56 are keyed `Not answerable`**,
including questions of essentially identical shape. One brochure contradicts itself:
`GPL-Graduate-Studies` keys "how many dogs and
cats are there in page 17" as `['0','0']` and "how many people with scarf are there in Page 5" as
`2`, but the sunglasses twin on the same page as `Not answerable`. It cuts both ways — `RAR.pdf`
"how many GPT-4o examples" is keyed `0` (the string appears on none of its 28 pages; the paper uses
GPT-4V), so a system that declines there is marked wrong too. Widening the key settles it without
deleting a negative sample in either direction.

The widening is **not** applied to the other `how many` rows keyed `Not answerable`. Those fail for
different reasons: page ranges outside the document (Pages 200-205, Pages 400-640), entities the
document never covers (Boeing, Airbus, Shopee, HAQ Executive Leadership, PWC Technic), or
deliberate terminology twins (EFI for ECU, NTUSU for NUSSU, generation for correction).

### When a `Not answerable` key gets widened

All 208 `Not answerable` rows were reviewed against this test, which turns on **what is missing**:

**Widen** when the container the question names *exists* and the thing it asks about is
*verifiably absent from it*. Then "none" — or, for a `how many`, `0` — is a reading of the
document, not a guess, and it means exactly what the key means. Examples: page 2 of
`8e7c4cb…` has a street photograph with three cars and a box truck and no bicycle; PDF p10 and
p14 of `e79deb02…` contain zero images and zero large vector blocks, so there is no diagram on
"page 10" under either page numbering; the timer chart on p50 of `User_Manual_1500S` draws only
green and blue bars, so no red bar starts anywhere.

**Do not widen** in four cases, where "none" is an over-claim rather than a reading:

| Case | Example |
|---|---|
| The container itself is missing | `Pages 200-205`, `Pages 400-640`; `2311.16502v3.pdf` "Figure 10", which has no caption anywhere in the paper |
| The entity never appears in the document | Beijing in a Nepal media survey; a microwave in a dishwasher manual; TRUCS "level-6"; survey years 2018 and 2022 |
| The question asks for a complement against an unbounded universe | `mi_phone.pdf`, "signal icons that can **not** be found in Status Bar" |
| The set is short, not empty | the EarthLink deck asks for "another **two** companies" when exactly one further contact carries a phone number |

The last row is why this is a test and not a heuristic: it looked like an empty set until the
contact slide was actually read.


## Every change

`⟳` marks a question whose wording was changed; the answer column then shows the answer that
wording now has.

| Document | Question (v1) | V1 answer | V2 answer | Type |
|---|---|---|---|---|
| `2005.12872v3.pdf` | How many multi-head self-attention layers does DETR's d… | 36 | 12 | `wrong_answer` |
| `2005.12872v3.pdf` | According to Fig 10 architecture of DETR’s transformer,… | Red | Pink | `wrong_answer` |
| `2023.findings-emnlp.248.pdf` | Which dataset used in this paper was proposed in 2022 a… | ProofWriter | AR-LSAT | `wrong_answer` |
| `698bba535087fa9a7f9009e172a7f763.…` | What are the counties mentioned in the document? | ['Hamilton', 'Lucas', '… | ['Hamilton', 'Lucas', '… | `wrong_answer` |
| `91521110100M_4K_UHD_Display_User_…` | A transmitter operating at a frequency of 500 MHz has a… | 2.92 | 3.80 | `wrong_answer` |
| `ADOBE_2015_10K.pdf` | what is roa for ADBE in FY2015? | 0.053 | 0.054 | `wrong_answer` |
| `AMAZON_2017_10K.pdf` | what is the percentage change of return for allowance f… | 60.3% | -60.3% | `wrong_answer` |
| `AMAZON_2017_10K.pdf` | What is Amazon's FY2017 days payable outstanding (DPO)?… | 97.75 | 97.70 | `wrong_answer` |
| `BESTBUY_2023_10K.pdf` | what is the change of Best Buy's gross margins change f… | 1.08% | 0.12% | `wrong_answer` |
| `GPL-Graduate-Studies-Professional…` | Which programme by coursework with disciplinary content… | ['MA (Humanities Educat… | ['MA (Humanities Educat… | `wrong_answer` |
| `NUS-FASS-Graduate-Guidebook-2021-…` | Which of the following department does not provide a Ph… | Department of History | None | `wrong_answer` |
| `PIP_Seniors-and-Tech-Use_040314.p…` | What is the gap between male 65+ age group who use inte… | 73.0 | 12.0 | `wrong_answer` |
| `PIP_Seniors-and-Tech-Use_040314.p…` | How many people who do not go online or only use SNS in… | 4087 | 1038 | `wrong_answer` |
| `PIP_Seniors-and-Tech-Use_040314.p…` | How many 65+ age group people go online 3-5 times per w… | 1251 | 738 | `wrong_answer` |
| `PI_2017.10.04_Automation_FINAL.pdf` | How many US workers say email or social media have had … | 2481 | 1506 | `wrong_answer` |
| `PI_2018.11.19_algorithms_FINAL.pdf` | Among all interviewees in the survey, what percentage o… | 20% | 5.1% | `wrong_answer` |
| `PRE_2022.09.29_NSL-politics_REPOR…` | Which Hispanic origin group in the United States is mos… | Puerto Rican | Cuban | `wrong_answer` |
| `afe620b9beac86c1027b96d31d396407.…` | What are the bankers' names associated with GODFREY PHI… | ['State Bank of India',… | ['State Bank of India',… | `wrong_answer` |
| `afe620b9beac86c1027b96d31d396407.…` | For the year ended March 31,2003, how much less were th… | 83672770 | 8367277000 | `wrong_answer` |
| `amb-siteaudits-ds15-150204174043-…` | What is the Top-Level Page name of the page with the sl… | /video/videocat/video92… | /category3/subcat2/ | `wrong_answer` |
| `bdf54dxa.pdf` | How many possible problems does the diswasher may encou… | 17 | 15 | `wrong_answer` |
| `e79deb02a0c0e87511080836c5d4347b.…` | How many strengths and weaknesses are metioned in Appen… | ['23', '21'] | ['22', '21'] | `wrong_answer` |
| `f8d3a162ab9507e021d83dd109118b60.…` | How many quizzes are there in the entire course? | 6 | 7 | `wrong_answer` |
| `germanwingsdigitalcrisisanalysis-…` | Is the Germanwings Facebook account logo consistent bef… | yes | no | `wrong_answer` |
| `germanwingsdigitalcrisisanalysis-…` | When did the number of tweets referencing Germanwings e… | 14:04 CET | 13:51 CET | `wrong_answer` |
| `obs-productdesc-en.pdf` | What is the benefit of level-2 in the system has passed… | Multi-AZ storage | Erasure Code | `wrong_answer` |
| `05-03-18-political-release.pdf` | What is the percentage of registered voters who support… ⟳ | 92% | 92% | `defective_question` |
| `05-03-18-political-release.pdf` | How many Demoncratic people in the survey of U.S. adult… ⟳ | 128 | 128 | `defective_question` |
| `05-03-18-political-release.pdf` | How many non-partisan people in the survey of U.S. adul… ⟳ | Not answerable | Not answerable | `defective_question` |
| `11-21-16-Updated-Post-Election-Re…` | How many % of voters reactions are "uneasy" and "excite… ⟳ | [53, 1.4] | [53, 51] | `defective_question` |
| `2021-Apple-Catalog.pdf` | One40 can only be used for Apple Watch, is that true? P… ⟳ | Yes | No | `defective_question` |
| `2311.16502v3.pdf` | According to this paper, among nice different datasets … ⟳ | "MMMU" | "MMMU" | `defective_question` |
| `2401.18059v1.pdf` | Write down the pseudo code from appendix that correspon… ⟳ | Slayer ← sorted(top k)[… | Slayer ← sorted(top k)[… | `defective_question` |
| `AMAZON_2017_10K.pdf` | How do Amazon recognize least cost? ⟳ | straight-line basis wit… | straight-line basis wit… | `defective_question` |
| `PG_2020.05.21_International-Coope…` | How many EU people believe that they will have more inf… ⟳ | 19% | 19% | `defective_question` |
| `PI_2017.10.04_Automation_FINAL.pdf` | How many US workers are interested in a robot caregiver… ⟳ | 1695 | 1695 | `defective_question` |
| `SnapNTell.pdf` | In the 3rd Wiki filtering, how many more entities were … ⟳ | 2885 | 1923 | `defective_question` |
| `User_Manual_1500S_Classic_EN.pdf` | How many steps are there for data exchange via USB? ⟳ | 9 | 9 | `defective_question` |
| `afe620b9beac86c1027b96d31d396407.…` | How much higher was the proposed dividend paid (Rupees … ⟳ | 155.98 | 155.98 | `defective_question` |
| `b3m5kaeqm2w8n4bwcesw-140602121350…` | Does CFCs causes skin burn? Directly answer 'yes' or 'n… ⟳ | Yes | No | `defective_question` |
| `e79deb02a0c0e87511080836c5d4347b.…` | What are the words written in the first rectangle on th… ⟳ | ['strategic priority ar… | ['strategic priority ar… | `defective_question` |
| `earthlinkweb-150213112111-convers…` | What is the job of the contact person in the picture at… ⟳ | Vice President of Produ… | Vice President of Produ… | `defective_question` |
| `f1f5242528411b262be447e61e2eb10f.…` | Which step in Figure 1 maps to the content of Figure 10? ⟳ | Deletion/duplication/re… | Deletion/duplication/re… | `defective_question` |
| `indonesiamobilemarketresearch-ag-…` | Which group accounts for the second largest share in te… ⟳ | Christians | Christians | `defective_question` |
| `reportq32015-151009093138-lva1-ap…` | As of Q3 2015, is vietnam's adoption rate of iOS 7 high… ⟳ | Not answerable | Not answerable | `defective_question` |
| `2303.08559v2.pdf` | What is the performance of filter-then-rerank methods (… ⟳ | 72.3% | 72.3% | `ambiguous_question` |
| `2307.09288v2.pdf` | list the top-3 models in Figure 3 ⟳ | ['Vicuna13b-v1.3', 'PaL… | ['Vicuna 33b-v1.3', 'Pa… | `ambiguous_question` |
| `2312.04350v3.pdf` | Which model performs the best on Cladder? ⟳ | GPT-4 | GPT-4 | `ambiguous_question` |
| `8e7c4cb542ad160f80fb3d795ada35d8.…` | What is the residential capacity of Staten Island from … ⟳ | 435000000 | 435000000 | `ambiguous_question` |
| `AMAZON_2017_10K.pdf` | what is Amazon's FY2017 Operating Profit Margin Before … ⟳ | 0.073 | 0.073 | `ambiguous_question` |
| `AMAZON_2017_10K.pdf` | what is Amazon's FY2017 debt to ebitda ratio? round you… ⟳ | 1.93 | 1.93 | `ambiguous_question` |
| `BESTBUY_2023_10K.pdf` | what is invested capital of Best Buy for for the fiscal… ⟳ | 13929 | 13929 | `ambiguous_question` |
| `COSTCO_2021_10K.pdf` | What does Costco rely heavily on for its financial perf… ⟳ | the financial performan… | the financial performan… | `ambiguous_question` |
| `COSTCO_2021_10K.pdf` | what is long-term debt of Costco in FY 2021? Anwser in … ⟳ | 10314 | 10314 | `ambiguous_question` |
| `COSTCO_2021_10K.pdf` | what is total debt of COSTCO in FY 2021?Answer in milli… ⟳ | 11407 | 11407 | `ambiguous_question` |
| `COSTCO_2021_10K.pdf` | what is total debt to EBITDA ratio of COSTCO in FY2021?… ⟳ | 1.344 | 1.344 | `ambiguous_question` |
| `COSTCO_2021_10K.pdf` | what is Long-term Debt to Total Liabilities for COSTCO … ⟳ | 0.25 | 0.25 | `ambiguous_question` |
| `COSTCO_2021_10K.pdf` | what is total debt to total assets for costco in FY 202… ⟳ | 0.192 | 0.192 | `ambiguous_question` |
| `COSTCO_2021_10K.pdf` | What is common equity for COSTCO in FY2021? ⟳ | 18078 | 18078 | `ambiguous_question` |
| `ISEP_student_handbook_2020.pdf` | Which compulsory ISEP courses does the students must ha… ⟳ | ['GS5002', 'GS6001', 'G… | ['GS5002', 'GS6001', 'G… | `ambiguous_question` |
| `Pew-Research-Center_Hispanic-Iden…` | What's the average value of all orange bars in the char… ⟳ | 21 | 21 | `ambiguous_question` |
| `chapter8-geneticscompatibilitymod…` | In the case presented in Chapter 9, what color are the … ⟳ | Not answerable | Not answerable | `ambiguous_question` |
| `mmdetection-readthedocs-io-en-v2.…` | If I want to use the detector in the paper `SOLO: Segme… ⟳ | DecoupledSOLOHead | DecoupledSOLOHead | `ambiguous_question` |
| `welcome-to-nus.pdf` | How many people with white shirt are there in the Page … ⟳ | Not answerable | 1 | `ambiguous_question` |
| `2311.16502v3.pdf` | How many tables are included in Pages 105-110? | Not answerable | 1 | `should_be_answerable` |
| `Independents-Report.pdf` | From this report, among Clinton, G.W.Bush, and Obama, w… | Not answerable | None | `should_be_answerable` |
| `NUS-Business-School-BBA-Brochure-…` | From 2022 graduate employment survey, do graduates with… | Not answerable | No | `should_be_answerable` |
| `NUS-FASS-Graduate-Guidebook-2021-…` | Which of the following department does not provide a MB… | Not answerable | None | `should_be_answerable` |
| `PP_2021.04.22_voting-access_REPOR…` | Compared to October 2018, the proportion of Democrats w… | Not answerable | No | `should_be_answerable` |
| `PRE_2022.09.29_NSL-politics_REPOR…` | What proportion of the Spanish dominant Latinos express… | Not answerable | 46% | `should_be_answerable` |
| `afe620b9beac86c1027b96d31d396407.…` | How much higher was the dividend paid in 2003 compared … | Not answerable | 0.70 | `should_be_answerable` |
| `camry_ebrochure.pdf` | What models of wheel are introduced on pages 10 and 11? | Not answerable | ['18-in. black machined… | `should_be_answerable` |
| `csewt7zsecmmbzjufbyx-signature-24…` | From 2009 to 2013, as for the adviser's organic growth … | Not answerable | 0 | `should_be_answerable` |
| `csewt7zsecmmbzjufbyx-signature-24…` | How many years have there been more than 4,500 births (… | Not answerable | 0 | `should_be_answerable` |
| `e79deb02a0c0e87511080836c5d4347b.…` | What are the top2 texts of the yellow words in the docu… | Not answerable | ['Strategic Planning', … | `should_be_answerable` |
| `earthlinkweb-150213112111-convers…` | What is the sum of percentage of customers and employer… | Not answerable | 122 | `should_be_answerable` |
| `nielsen2015musicbizpresentation-f…` | What is the difference in total volume between the rank… | Not answerable | 1175000 | `should_be_answerable` |
| `owners-manual-2170416.pdf` | In the two styles shown in the "Parts and Features" sec… | Not answerable | No | `should_be_answerable` |
| `379f44022bb27aa53efd5d322c7b57bf.…` | what is the number of red logos in page 10? | Not answerable | Not answerable or 0 or … | `incomplete_answer` |
| `7c3f6204b3241f142f0f8eb8e1fefe7a.…` | What types of charts are in the document? | Not answerable | Not answerable or 0 or … | `incomplete_answer` |
| `8e7c4cb542ad160f80fb3d795ada35d8.…` | Which area of New York has more than 23% land area rezo… | Not answerable | Not answerable or 0 or … | `incomplete_answer` |
| `8e7c4cb542ad160f80fb3d795ada35d8.…` | What is the color of the bike in the picture on page 2? | Not answerable | Not answerable or 0 or … | `incomplete_answer` |
| `936c0e2c2e6c8e0c07c51bfaf7fd0a83.…` | What service specifications are associated with the SRM… | ['Microsoft Oracle Open… | ['Microsoft Oracle Open… | `incomplete_answer` |
| `GPL-Graduate-Studies-Professional…` | How many people with sun glassess are there in Page 5? | Not answerable | Not answerable or 0 or … | `incomplete_answer` |
| `Macbook_air.pdf` | List all the countries/regions mentioned in the "Regula… | ['Canada', 'Europe', 'K… | ['Canada', 'Europe', 'K… | `incomplete_answer` |
| `User_Manual_1500S_Classic_EN.pdf` | In the picture on page 50, what time does the red bar s… | Not answerable | Not answerable or 0 or … | `incomplete_answer` |
| `a5879805d70c854ea4361e43a84e3bb2.…` | what is the texts of the underlined italic words in pag… | Not answerable | Not answerable or 0 or … | `incomplete_answer` |
| `chapter8-geneticscompatibilitymod…` | What plants is on the cover of each chapter? | Not answerable | Not answerable or 0 or … | `incomplete_answer` |
| `ddoseattle-150627210357-lva1-app6…` | Which Youtube does the slides use to show the consequce… | Not answerable | Not answerable or 0 or … | `incomplete_answer` |
| `e639029d16094ea71d964e2fb953952b.…` | What is the yellow color italic texts in page 9? | Not answerable | Not answerable or 0 or … | `incomplete_answer` |
| `e79deb02a0c0e87511080836c5d4347b.…` | What is the title of the diagram on page 10? | Not answerable | Not answerable or 0 or … | `incomplete_answer` |
| `earthlinkweb-150213112111-convers…` | What is the job of the contact person in the picture at… | Not answerable | Not answerable or 0 or … | `incomplete_answer` |
| `formwork-150318073913-conversion-…` | Which stages of casting a tunnel framework require a co… | Not answerable | Not answerable or 0 or … | `incomplete_answer` |
| `san-francisco-11-contents.pdf` | Name a restaurant between 45th Ave. and 44th Ave.. | Not answerable | Not answerable or 0 or … | `incomplete_answer` |
| `dr-vorapptchapter1emissionsources…` | What are the four concrect facts of global challenges? | ['Increasing world popu… | None | `corpus_defect` |
| `dr-vorapptchapter1emissionsources…` | What are the ten concrect consequences of global challe… | Not answerable | None | `corpus_defect` |
| `dr-vorapptchapter1emissionsources…` | Among the global challenges and requirements, which of … | ['World Mobility', 'Wor… | None | `corpus_defect` |
| `dr-vorapptchapter1emissionsources…` | Among the global challenges, which of them would not be… | Not answerable | None | `corpus_defect` |
| `dr-vorapptchapter1emissionsources…` | What four elements are exhausted in the combustion proc… | ['Nitrogen', 'Water', '… | None | `corpus_defect` |
| `dr-vorapptchapter1emissionsources…` | What are the top 3 sources according to the total emiss… | ['Power Generation', 'V… | None | `corpus_defect` |
| `dr-vorapptchapter1emissionsources…` | List all the PM health effects that increse by more tha… | ['Cough', 'Phlegm', 'Ad… | None | `corpus_defect` |
| `dr-vorapptchapter1emissionsources…` | For first two gases that causes greenhouse effect, list… | ['13.7%', '0.1%'] | None | `corpus_defect` |
| `dr-vorapptchapter1emissionsources…` | One kind of gas is the siginificant contributor to clim… | ['USA', 'Russia', 'Sout… | None | `corpus_defect` |
| `dr-vorapptchapter1emissionsources…` | How many slides includes at least one chart? | 24 | None | `corpus_defect` |
| `BESTBUY_2023_10K.pdf` | what is interest coverage ratio for AMCOR'FY 2020? roun… | 51.286 | Not answerable | `should_be_unanswerable` |
| `Macbook_air.pdf` | I'm a Macbook Air user in Mexico. According to this gui… | 1-800-275-2273 | Not answerable | `should_be_unanswerable` |

## Considered and rejected

Questions that looked defective and turned out to be **deliberate negative samples**. Upstream
pairs many items with a near-identical twin: one side uses the document's real terminology, page,
year or entity and is answerable; the other changes one word and is labelled `Not answerable`.
That is the point — it tests whether a system invents an answer for a premise the document does
not contain. These are left exactly as upstream wrote them.

| Document | Answerable twin | Twin labelled `Not answerable` |
|---|---|---|
| `2310.05634v2.pdf` | "…map to **both** [NA] **and** a list of sub-graph knowledge?" | "…map to **either** [NA] **or** a list…" |
| `tacl_a_00660.pdf` | "Among the three **correction** strategies…" | "Among the three **generation** strategies…" |
| `t480_ug_en.pdf` | "Which **country or region** codes … Mainland China?" → `SC` | "Which **license** codes … Mainland China?" |
| `formwork-…_95.pdf` | "Which stages … require a **heater**?" → `Stage 5` | "Which stages … require a **cooler**?" |
| `e79deb02…pdf` | "…governor as mentioned on the **first** page" → `Rick Scott` | "…on the **last** page" |
| `e79deb02…pdf` | "title of the diagram on page **9**" | "title of the diagram on page **10**" |
| `chapter8-genetics…pdf` | "What **animal** is on the cover of each chapter?" → `leopard` | "What **plants** is on the cover…" |
| `san-francisco-11-contents.pdf` | "Name a restaurant between **36th** and **37th** Ave." → `Cassava` | "…between **45th** and **44th** Ave." |
| `san-francisco-11-contents.pdf` | "…most central part of **San Francisco**" → `178` | "…most central part of **Oakland**" |
| `PIP_Seniors…pdf` | "…tracking survey" dated **2013** | the same question dated **2020** / **2022** |
| `ddoseattle…pdf` | "Which Youtube … **blindly following data**" | "Which Youtube … **weak data leadership**" |

The same shape guards the corpus elsewhere: several items name a company the document never
discusses — Apple in a Godfrey Phillips annual report, Amazon in a Facebook/Twitter deck, Boeing in
the Germanwings analysis, Amcor in a Best Buy 10-K — and are all labelled `Not answerable`.

**Before rewording any question, check for an answerable twin.** A `Not answerable` key with empty
`evidence_pages` is very likely intentional; one with a concrete value and a cited page is where an
annotator did the work and mislabelled the prompt. Twin structure shows what the annotator was
*trying* to test — it does **not** guarantee that both sides are labelled correctly. Two of the
corrections above sit on one side of a pair whose other side is untouched.

## Two traps worth naming

**Stating a convention can introduce a new one.** Several finance ratios were unanswerable as
written because the filing supports more than one reading of "long-term debt" or "before
depreciation". Adding "taking total debt as **all debt** plus all lease liabilities" fixed the
lease ambiguity and immediately created another: `$41` of short-term borrowings disclosed only in
Costco's Note 5 is literally "all debt", so a careful system included it and diverged again. The
wording now names the balance-sheet lines. Prefer the most specific phrasing available; universal
quantifiers move the boundary rather than removing it.

**Percentages need their own base.** Three answers were a survey percentage multiplied by the
wrong denominator — the full sample instead of the subgroup the chart describes. A chart headed
"% of *internet users*" applied to every respondent produces a number larger than the population
that could possibly qualify. Where a count is derived from a percentage, the note records which
base was used.

## Caveat

These come from auditing questions that one system answered confidently and therefore scored zero
— a biased slice, and one where annotation errors naturally concentrate. The corpus-wide error rate
is unmeasured, and a broader sample would establish it. Coverage is also uneven by task type: the
`lookup`, `derive` and `compare` slices have been audited end to end, `count` and `enumerate` have
not.

Thirteen entries from the first review pass record the change but not the reasoning; their `note`
says so explicitly. They were checked against the cited pages at the time, but the derivation was
not written down and has not been reconstructed.

Disagreements are useful. Open an issue naming the entry and the page you read; some questions turn
out to be defective rather than mislabelled, which is why `defective_question` exists as a category.
