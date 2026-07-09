# Screenshots

Save your screenshots into this folder using the **exact filenames** below —
the main `README.md` already links to these paths, so GitHub will render
them inline automatically once the files exist. No separate "upload" step,
no GitHub web editor needed — just save the file here and push.

| Filename | What to capture |
|---|---|
| `landing.png` | The landing screen — hero title, feature cards, sample-dataset buttons |
| `overview.png` | Overview tab — data quality metrics + Column Health expander |
| `clean.png` | Clean tab — before/after comparison (sidebar's Cleaning History showing too is a nice touch) |
| `visualize.png` | Visualize tab — auto-generated chart grid + correlation heatmap |
| `sql-lab.png` | SQL Lab — an example query loaded, results with row count + execution time |
| `ai-analyst.png` | AI Analyst — a question answered with a generated chart |
| `combine.png` | Combine tab — candidate join-key table + before/after row-count preview |
| `hell-mode.png` | Hell Mode tab — the Indian Number Parser's before/after preview table (load `samples/hell/indian_startup_funding_messy.csv` first) |

## How to add one (Windows)

1. Run the app locally (`streamlit run app.py`) or open your deployed Cloud URL.
2. Get it into the state you want to capture (load a sample dataset, ask a
   question, etc.).
3. Press **Win + Shift + S** to open the Snipping Tool, drag to select the
   region, then it copies to your clipboard automatically.
4. Open **Paint** (or any image editor), paste (**Ctrl+V**), and save as a
   PNG directly into this folder (`prism/docs/screenshots/`) with the exact
   filename from the table above.
5. Back in your terminal:
   ```bash
   git add docs/screenshots/landing.png   # repeat per file, or just: git add docs/screenshots/
   git commit -m "Add screenshots"
   git push
   ```
6. Refresh the README on GitHub — the images should now render inline.

You don't need all 8 at once — add whichever you have and repeat later for
the rest. Any filename left missing just won't render (GitHub shows a small
broken-image icon), it won't break the rest of the page.
