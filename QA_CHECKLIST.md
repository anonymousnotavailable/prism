# Prism — Final QA Checklist

Manual walkthrough before calling this launch-ready. Check items off as you
go; anything that fails, note it and fix before deploying. Do this both
**locally** and **once more against the deployed Streamlit Cloud URL** —
they can fail independently (e.g. secrets misconfigured on Cloud only).

---

## 1. Every tab loads with each of the 3 sample datasets

For **each** of Sales, HR, and Stocks (landing screen → "Load \<name\>"):

- [ ] Overview tab renders — metrics, missing/outlier tables, Column Health,
      Column Drill-Down (try 2-3 different columns), Anomaly Detection
- [ ] Clean tab renders — Before vs After, Cleaning Log, download button works
- [ ] Combine tab renders — upload a second sample as the "second file" and
      confirm the candidate-key table appears
- [ ] Visualize tab renders — auto-charts appear, correlation heatmap shows
      (Stocks/Sales have enough numeric columns), manual chart builder works
- [ ] SQL Lab tab renders — `SELECT * FROM data LIMIT 10;` runs cleanly
- [ ] AI Analyst tab renders (with a key configured — see §7 for without)

## 2. Every button clicked once, sane output

Sidebar:
- [ ] Theme toggle (dark ↔ light) — both the CSS and the chart colors switch
- [ ] Handle Missing Values → Apply
- [ ] Remove Duplicate Rows
- [ ] Drop Selected Columns
- [ ] Fix Column Types → Convert
- [ ] Datetime Features → Extract (use Sales' `order_date` or Stocks' `date`)
- [ ] Smart Type Coercion → Convert (use Sales' `revenue` or HR's `salary` —
      confirm the injected outlier becomes visible as a numeric value after conversion)
- [ ] Reset to Original Data
- [ ] Undo
- [ ] Export .py (open the downloaded file — does it look like valid Python?)
- [ ] Save Session

Overview tab:
- [ ] Find Anomalies → Exclude flagged rows from active dataset

Visualize tab:
- [ ] Build Chart (manual mode, a couple of different chart types)
- [ ] Download Full HTML Report (open it — do the charts render?)

SQL Lab:
- [ ] Each of the 4 example query buttons, then Run Query
- [ ] Explain This Query

AI Analyst:
- [ ] Generate Key Insights
- [ ] Mic button (or confirm the graceful fallback caption if no mic/package)

## 3. AI Analyst answers 3 test questions correctly

Using the **Sales** sample dataset:

- [ ] "What's the average revenue?" → a number (may need type coercion applied first for a clean numeric answer)
- [ ] "How many orders are there per region?" → a table, and a chart (question implies comparison)
- [ ] "What's the total quantity sold by product?" → a table, correct aggregation

For each: confirm the "View generated code" expander shows sensible pandas,
and that a genuinely malformed follow-up (e.g. a typo'd column name) triggers
the self-healing retry caption instead of just failing silently.

## 4. SQL Lab runs all 4 example queries

On at least 2 of the 3 sample datasets:

- [ ] `SELECT *` — returns rows, row count + ms shown
- [ ] `GROUP BY` aggregation — returns grouped rows
- [ ] `WHERE` filter — returns a filtered subset
- [ ] `ORDER BY` + `LIMIT` — returns a sorted, capped subset
- [ ] A deliberately broken query (e.g. `SELEKT * FROM data;`) shows a styled error, not a crash

## 5. Undo works after 3 consecutive cleaning steps

- [ ] Apply 3 different cleaning actions in a row (e.g. fill nulls → remove
      duplicates → convert a dtype)
- [ ] Click Undo 3 times
- [ ] Confirm the dataset is back to its state before step 1 (check row/column
      counts and the Cleaning Log match the original)
- [ ] Confirm Undo is disabled (grayed out) once the stack is empty

## 6. Session save → reload → state fully restored

- [ ] Load a sample, apply 2-3 cleaning steps, ask the AI Analyst one question
- [ ] Click Save Session, note the downloaded filename
- [ ] Refresh the browser tab (or open a new session) to get back to the landing screen
- [ ] Upload the saved `.json` via "Restore a saved session"
- [ ] Confirm: the dataset matches, the Cleaning Log matches, and the AI
      Analyst chat history shows the prior question (code/answer text, not
      necessarily the live chart)

## 7. App works with API key removed (graceful degradation)

- [ ] Rename/remove `.env` (or comment out `GEMINI_API_KEY`) and restart the app
- [ ] Confirm the app **still loads fully** — landing screen, all 6 tabs, sidebar
- [ ] AI Analyst tab shows the friendly "Add your free Gemini API key..."
      message with a working link to aistudio.google.com — no traceback
- [ ] SQL Lab's "Explain This Query" shows the same friendly message instead of erroring
- [ ] Sidebar's AI Analyst status caption reads "No GEMINI_API_KEY found..."
- [ ] Restore the key afterward and confirm it starts working again

## 8. Mobile / narrow window: nothing catastrophically broken

Resize the browser window to ~400px wide (or use browser dev tools' device
toolbar):

- [ ] Sidebar collapses to a hamburger menu and is still usable
- [ ] Tabs remain clickable (may wrap or scroll horizontally — that's fine,
      just shouldn't overlap or become unclickable)
- [ ] Landing screen's feature cards and sample buttons stack instead of
      overflowing off-screen
- [ ] Charts resize instead of getting clipped
- [ ] No error banners appear purely from the resize

---

## Additional launch-readiness spot-checks

- [ ] `git status` shows no `.env` staged, ever (re-check right before every push)
- [ ] Fresh clone + `pip install -r requirements.txt` + `streamlit run app.py`
      works on a clean machine/venv (catches anything only working because
      of leftover local state)
- [ ] Empty CSV, 1-row CSV, all-null-column CSV, and a >50,000-row CSV each
      load without a traceback (see the edge cases fixed in this phase)
- [ ] A multi-sheet `.xlsx` file prompts for a sheet before loading; a
      single-sheet workbook or plain CSV loads with zero extra clicks
- [ ] Deployed Streamlit Cloud URL loads, theme matches local, and the
      Gemini secret (if set) is picked up (sidebar caption confirms it)
