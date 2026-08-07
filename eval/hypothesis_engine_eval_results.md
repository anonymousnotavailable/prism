# Prism — Hypothesis Engine + Anomaly Tuning Eval Results

**Accuracy: 100.0%** (9/9 test cases passed)

Runs `modules.hypothesis_engine`'s rule-based fallback + real statistical verification pipeline, and `modules.anomaly`'s new configurable-sensitivity and narration-fallback paths, against synthetic datasets with known ground truth (a strong correlation, a strong group effect, pure noise). No Gemini API key required — every scored path is the deterministic fallback.

| # | Case | Result |
|---|------|--------|
| 1 | default_hypotheses references real columns | **PASS** — 5 hypothesis(es) generated, all referencing real columns. |
| 2 | default_hypotheses surfaces strong correlation | **PASS** — The strongly correlated ('x', 'y') pair was proposed as a hypothesis. |
| 3 | test_hypotheses confirms a real group effect | **PASS** — Correctly confirmed with p=1.74e-175. |
| 4 | test_hypotheses rejects independent columns | **PASS** — Correctly did not confirm a hypothesis over independently generated columns. |
| 5 | test_hypotheses handles an untestable pairing | **PASS** — Correctly marked an invalid pairing as untestable rather than crashing. |
| 6 | generate_hypotheses falls back with model=None | **PASS** — model=None correctly fell back to 5 rule-based hypothesis(es). |
| 7 | anomaly contamination is clamped to a sane range | **PASS** — contamination=0.9 was clamped; 25% of rows flagged (max allowed ~25%). |
| 8 | anomaly narration fallback (no Gemini) | **PASS** — Fallback narration produced without Gemini: "10 row(s) (10.0% of the dataset) were flagged as unusual. 'a' was the most commo"... |
| 9 | anomaly narration handles zero flagged rows | **PASS** — Correctly handled the zero-flagged-rows case without calling Gemini. |

## Failures in detail
None — every test case passed.