# Prism — Hypothesis Engine Eval Results

**Accuracy: 100.0%** (7/7 test cases passed)

Runs `modules.hypothesis_engine`'s scan_hypotheses()/narrate_findings() directly against fixed synthetic datasets with planted relationships (and planted non-relationships). No Gemini API key required — the scan itself is fully deterministic scipy/statsmodels, and narrate_findings() is only exercised in its model=None templated-fallback path here.

| # | Case | Dataset | Result |
|---|------|---------|--------|
| 1 | finds a planted strong correlation | (synthetic) | **PASS** — revenue/marketing_spend flagged significant after correction (r=0.99, q=3.226e-264). |
| 2 | finds a planted group difference | (synthetic) | **PASS** — conversion_score/variant flagged significant after correction (Cohen's d=-1.99). |
| 3 | FDR correction suppresses noise false-positives | (synthetic) | **PASS** — 3 raw-significant -> 0 after FDR correction, out of 66 pure-noise pairs. |
| 4 | single testable column -> empty result, no crash | (synthetic) | **PASS** — Single-column dataset scanned to an empty (not crashed) result. |
| 5 | wide dataset truncates to max_columns | (synthetic) | **PASS** — 20-column dataset correctly capped to 12 scanned columns with truncated=True. |
| 6 | narrate_findings templated fallback (no model) | (synthetic) | **PASS** — Templated fallback produced 1 bullet(s) without calling Gemini. |
| 7 | narrate_findings on an empty scan | (synthetic) | **PASS** — Empty scan narrates to zero bullets, no error raised. |

## Failures in detail
None — every test case passed.