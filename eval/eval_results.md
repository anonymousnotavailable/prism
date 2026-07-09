# Prism — Code-Gen Eval Results

**Accuracy: 100.0%** (7/7 evaluated questions passed)

> **Partial run:** 18 question(s) were skipped after hitting the Gemini free-tier daily quota mid-run — they count toward neither passes nor failures. Re-run `python eval/run_eval.py` once the quota resets (or with a fresh API key) for a full score.

Runs each question in `questions.json` through the real AI Analyst pipeline (`modules.ai_analyst.ask_and_execute` — Gemini-generated pandas code, run in the safe-execution sandbox) against the bundled sample datasets, after the same Smart Type Coercion cleanup a user would apply in the app, and checks the result against a fixed ground truth.

| # | Dataset | Question | Result |
|---|---------|----------|--------|
| 1 | sales_data.csv | What is the total quantity sold across all orders? | **PASS** — Got 3567.00, expected 3567.0 (tolerance +/- 71.34). |
| 2 | sales_data.csv | What is the total revenue across all orders? | **PASS** — Got 1080822.00, expected 1080822.0 (tolerance +/- 21616.44). |
| 3 | sales_data.csv | What is the average revenue per order? | **PASS** — Got 2192.34, expected 2214.8 (tolerance +/- 66.44). |
| 4 | sales_data.csv | Which region generated the highest total revenue? | **PASS** — Expected to find 'West' in the result. |
| 5 | sales_data.csv | Which product had the highest total quantity sold? | **PASS** — Expected to find 'Desk Chair' in the result. |
| 6 | sales_data.csv | How many unique products are there? | **PASS** — Got 8.00, expected 8 (tolerance +/- 0.00). |
| 7 | sales_data.csv | How many unique regions are there? | **PASS** — Got 4.00, expected 4 (tolerance +/- 0.00). |
| 8 | hr_data.csv | What is the average salary across all employees? | **NOT RUN** — Gemini free-tier quota exceeded. |
| 9 | hr_data.csv | What is the maximum salary in the dataset? | **NOT RUN** — Skipped — Gemini free-tier quota already exhausted this run. |
| 10 | hr_data.csv | Which department has the highest average salary? | **NOT RUN** — Skipped — Gemini free-tier quota already exhausted this run. |
| 11 | hr_data.csv | How many unique departments are there? | **NOT RUN** — Skipped — Gemini free-tier quota already exhausted this run. |
| 12 | hr_data.csv | How many employees have attrition marked as Yes? | **NOT RUN** — Skipped — Gemini free-tier quota already exhausted this run. |
| 13 | hr_data.csv | How many employees have attrition marked as No? | **NOT RUN** — Skipped — Gemini free-tier quota already exhausted this run. |
| 14 | hr_data.csv | How many total employees are in the dataset? | **NOT RUN** — Skipped — Gemini free-tier quota already exhausted this run. |
| 15 | stock_data.csv | What is the average closing price across all rows? | **NOT RUN** — Skipped — Gemini free-tier quota already exhausted this run. |
| 16 | stock_data.csv | What is the highest high price recorded? | **NOT RUN** — Skipped — Gemini free-tier quota already exhausted this run. |
| 17 | stock_data.csv | What is the lowest low price recorded? | **NOT RUN** — Skipped — Gemini free-tier quota already exhausted this run. |
| 18 | stock_data.csv | What is the total trading volume across all rows? | **NOT RUN** — Skipped — Gemini free-tier quota already exhausted this run. |
| 19 | stock_data.csv | Which ticker has the highest average closing price? | **NOT RUN** — Skipped — Gemini free-tier quota already exhausted this run. |
| 20 | stock_data.csv | How many unique tickers are there in the dataset? | **NOT RUN** — Skipped — Gemini free-tier quota already exhausted this run. |
| 21 | bank_transactions_messy.csv | How many transactions are flagged as fraud (is_fraud equal to 1)? | **NOT RUN** — Skipped — Gemini free-tier quota already exhausted this run. |
| 22 | bank_transactions_messy.csv | How many unique customers are there? | **NOT RUN** — Skipped — Gemini free-tier quota already exhausted this run. |
| 23 | bank_transactions_messy.csv | What is the total transaction amount across all rows? | **NOT RUN** — Skipped — Gemini free-tier quota already exhausted this run. |
| 24 | indian_startup_funding_messy.csv | How many unique startups are there? | **NOT RUN** — Skipped — Gemini free-tier quota already exhausted this run. |
| 25 | product_events_messy.csv | How many unique users are there? | **NOT RUN** — Skipped — Gemini free-tier quota already exhausted this run. |

## Failures in detail
None — every evaluated question passed.