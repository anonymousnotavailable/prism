# Prism — Code-Gen Eval Results

**Partial run: 7/7 passed (100%) before hitting the Gemini free-tier daily quota.**
The remaining 13 questions could not be evaluated today — see note below.

Runs each question in `questions.json` through the real AI Analyst pipeline
(`modules.ai_analyst.ask_and_execute` — Gemini-generated pandas code, run in the
safe-execution sandbox) against the bundled sample datasets, after the same Smart
Type Coercion cleanup a user would apply in the app, and checks the result against
a fixed ground truth.

> **Note on this run:** questions 1-7 (`sales_data.csv`) each got a real answer from
> Gemini and passed. Starting at question 8, the API key hit its free-tier **daily**
> quota, so questions 8-20 failed with a quota error rather than a wrong answer —
> this is an external rate limit, not a pipeline defect. Re-run
> `python eval/run_eval.py` once the quota resets (or with a fresh API key) to get
> the full 20-question score, then update the accuracy badge in `README.md`.

| # | Dataset | Question | Result |
|---|---------|----------|--------|
| 1 | sales_data.csv | What is the total quantity sold across all orders? | **PASS** — Got 3567.00, expected 3567.0 (tolerance +/- 71.34). |
| 2 | sales_data.csv | What is the total revenue across all orders? | **PASS** — Got 1080822.00, expected 1080822.0 (tolerance +/- 21616.44). |
| 3 | sales_data.csv | What is the average revenue per order? | **PASS** — Got 2192.34, expected 2214.8 (tolerance +/- 66.44). |
| 4 | sales_data.csv | Which region generated the highest total revenue? | **PASS** — Expected to find 'West' in the result. |
| 5 | sales_data.csv | Which product had the highest total quantity sold? | **PASS** — Expected to find 'Desk Chair' in the result. |
| 6 | sales_data.csv | How many unique products are there? | **PASS** — Got 8.00, expected 8 (tolerance +/- 0.00). |
| 7 | sales_data.csv | How many unique regions are there? | **PASS** — Got 4.00, expected 4 (tolerance +/- 0.00). |
| 8 | hr_data.csv | What is the average salary across all employees? | **NOT RUN** — Gemini free-tier daily quota exceeded. |
| 9 | hr_data.csv | What is the maximum salary in the dataset? | **NOT RUN** — Gemini free-tier daily quota exceeded. |
| 10 | hr_data.csv | Which department has the highest average salary? | **NOT RUN** — Gemini free-tier daily quota exceeded. |
| 11 | hr_data.csv | How many unique departments are there? | **NOT RUN** — Gemini free-tier daily quota exceeded. |
| 12 | hr_data.csv | How many employees have attrition marked as Yes? | **NOT RUN** — Gemini free-tier daily quota exceeded. |
| 13 | hr_data.csv | How many employees have attrition marked as No? | **NOT RUN** — Gemini free-tier daily quota exceeded. |
| 14 | hr_data.csv | How many total employees are in the dataset? | **NOT RUN** — Gemini free-tier daily quota exceeded. |
| 15 | stock_data.csv | What is the average closing price across all rows? | **NOT RUN** — Gemini free-tier daily quota exceeded. |
| 16 | stock_data.csv | What is the highest high price recorded? | **NOT RUN** — Gemini free-tier daily quota exceeded. |
| 17 | stock_data.csv | What is the lowest low price recorded? | **NOT RUN** — Gemini free-tier daily quota exceeded. |
| 18 | stock_data.csv | What is the total trading volume across all rows? | **NOT RUN** — Gemini free-tier daily quota exceeded. |
| 19 | stock_data.csv | Which ticker has the highest average closing price? | **NOT RUN** — Gemini free-tier daily quota exceeded. |
| 20 | stock_data.csv | How many unique tickers are there in the dataset? | **NOT RUN** — Gemini free-tier daily quota exceeded. |

## Failures in detail

None of the 7 evaluated questions failed. Questions 8-20 are pending a re-run
(quota-blocked, not failed) — see the note above.
