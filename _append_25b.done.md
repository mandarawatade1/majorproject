
### 25.9 The verifier discriminates — probe results (29 Aug 2026)

The first live C5 question returned `verdict: supported, support_rate: 1.0` on
a one-sentence answer that was in fact correct. That is the right verdict and
almost no evidence: a verifier that only ever agrees produces exactly the same
row — 100% support, zero refusals — while doing nothing at all.

So `scripts/check_verifier.py` holds the context fixed and varies the answer,
which is the opposite of what the pipeline does, and checks four cases whose
correct verdict is known in advance.

| Case | Expected | Result | Raw reply |
| --- | --- | --- | --- |
| Answer the context states outright | `supported` | **PASS** (11 s) | `SUPPORTED` |
| Answer the context contradicts (900 vs 180) | `unsupported`, refused | **PASS** (4 s) | `UNSUPPORTED: 1` |
| One true sentence, one fabricated | `partially_supported`, only #2 | **PASS** (7 s) | `UNSUPPORTED: 2` |
| A fact plus "contact the admissions office" | `supported` | **PASS** (5 s) | `SUPPORTED` |

**4 / 4.**

Case 3 carries most of the weight. Cases 1 and 2 could both be passed by a
model reacting to some surface property of the answer as a whole; only case 3
requires judging two sentences in one answer differently, which is precisely
what C5 claims to do. Case 4 guards the opposite failure — a verifier that
flagged every signpost would depress the support rate on nearly every answer
and make the metric meaningless.

The refusal fired exactly once, on the wholly-unsupported answer, and never
otherwise.

**This is the §25.3 prediction holding.** C4 asked the same model to plan and
it rephrased the question 12 times out of 12 (§24.3). C5 asks it to check, and
it checks correctly on all four probes. The difference between the two
configurations is not effort or prompt quality — both use the same one-line
contract against the same quantized 7B — it is the *kind* of task. Planning
requires generating something new; checking requires comparing two things
already present. That distinction is the most useful thing the C4/C5 pair
contributes to the report, and it is now evidenced rather than asserted.

**What the probe does not establish.** Four synthetic cases against one short,
clean passage is a far easier setting than a real answer judged against five
retrieved chunks of ~6000 characters, several of them near-duplicates. The
probe demonstrates capability; only the 20-question evaluation demonstrates
reliability at scale. It is a gate, not a result.

**On cost.** The probe's verification calls took 4–11 seconds; the same step
inside the pipeline took 92 seconds. The difference is prompt length — CPU
inference is dominated by evaluating the context, and the pipeline passes the
full assembled context where the probe passes one short passage. So C5's
overhead scales with context size, and the 20-question run should be expected
around 100 minutes against C4's 69.
