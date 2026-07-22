# Prism — Auto Cleaner Eval Results

**Accuracy: 100.0%** (8/8 test cases passed)

Runs `modules.autocleaner`'s scan -> plan -> execute pipeline directly against the bundled Hell Mode sample datasets and asserts specific fixes get planned and applied. No Gemini API key required — the plan and its execution are fully deterministic; only the optional one-line narration touches Gemini, and this eval never calls it in the scored path.

| # | Case | Dataset | Result |
|---|------|---------|--------|
| 1 | parse_indian_number (funding_amount) | indian_startup_funding_messy.csv | **PASS** — 'funding_amount' parsed to numeric (5 SAFE action(s) applied). |
| 2 | remove_exact_duplicates | product_events_messy.csv | **PASS** — 40 exact duplicate row(s) removed, 0 remain. |
| 3 | convert_disguised_nulls (device_type) | product_events_messy.csv | **PASS** — 'device_type' missing count rose from 36 to 60 (disguised nulls converted). |
| 4 | normalize_units (session_duration) | product_events_messy.csv | **PASS** — 'session_duration' normalized to a single unit (sec). |
| 5 | already-clean dataset -> empty plan | (synthetic) | **PASS** — Empty plan for already-clean data; narration matches expected template. |
| 6 | meaningful NA (PoolQC, House Prices-style) | (synthetic) | **PASS** — 99% missing 'PoolQC' correctly filled with an explicit 'Not Applicable' category, not the mode. |
| 7 | zero sentinel (Glucose, Pima Diabetes-style) | (synthetic) | **PASS** — 5 placeholder zeros in 'Glucose' converted to missing; legitimate 0/1 'Outcome' column left alone. |
| 8 | multi-value split (listed_in, Netflix-style) | (synthetic) | **PASS** — Multi-value 'listed_in' column correctly surfaced as count + primary-value columns. |

## Failures in detail
None — every test case passed.