# Deploying Prism to Streamlit Community Cloud

Step-by-step instructions to get Prism live on a public URL, free, in about
five minutes. No server management, no Docker — Streamlit Community Cloud
builds and hosts the app directly from your GitHub repo.

---

## Prerequisites

- A [GitHub](https://github.com) account
- A [Streamlit Community Cloud](https://share.streamlit.io) account (sign in
  with GitHub — no separate signup needed)
- A free Gemini API key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
  (only needed if you want the AI Analyst tab to work — the rest of the app
  runs fine without one)

---

## 1. Push the project to GitHub

If this project isn't already a git repository:

```bash
cd prism
git init
git add .
git status   # sanity check — .env should NOT appear in this list
git commit -m "Initial commit"
```

**Before pushing, double-check `.env` is not staged.** Run `git status` and
confirm you don't see `.env` in the output (only `.env.example` should be
tracked). It's already listed in `.gitignore`, so a plain `git add .` won't
pick it up — but always verify before the first push, since this is the one
step that can leak a secret if something's misconfigured.

Then create a new repository on GitHub and push:

```bash
git remote add origin https://github.com/anonymousnotavailable/prism.git
git branch -M main
git push -u origin main
```

---

## 2. Create the app on Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. Click **"New app"**.
3. Fill in the deploy form:
   - **Repository:** `anonymousnotavailable/prism`
   - **Branch:** `main`
   - **Main file path:** `app.py`
4. (Optional) Click **"Advanced settings"** to pin a Python version — Prism
   is tested on **Python 3.9+**; 3.11 or 3.12 is a good choice if you don't
   have a preference. This isn't required — Cloud's default works fine.
5. Click **"Deploy"**.

Streamlit Cloud will clone the repo, install `requirements.txt`, and start
the app. The first deploy takes a couple of minutes (installing scikit-learn
and DuckDB takes the longest).

---

## 3. Add your Gemini API key as a Secret

The AI Analyst tab (and SQL Lab's "Explain This Query") needs `GEMINI_API_KEY`.
Locally this comes from `.env`; on Cloud it comes from Streamlit's **Secrets**
manager instead — `.env` files aren't deployed (they're gitignored on purpose).

1. From your app's page on Streamlit Cloud, click the **⋮** menu → **Settings**.
2. Open the **Secrets** tab.
3. Paste in TOML format:

   ```toml
   GEMINI_API_KEY = "your_key_here"
   ```

4. Click **Save**. The app restarts automatically with the secret available.

`modules/ai_analyst.py`'s `get_api_key()` checks `st.secrets` first and falls
back to the local `.env`-populated environment variable — so the exact same
code path works in both places without an `if running_on_cloud` branch
anywhere in the app.

**Without this step**, the app still deploys and runs completely — every tab
except the AI-dependent parts of AI Analyst and SQL Lab works normally. The
AI Analyst tab shows a friendly "Add your free Gemini API key..." message
with a link to get one, instead of crashing.

---

## 4. Verify the deployment

Open the app's public URL and check:

- [ ] The landing screen loads with the hero, feature cards, and sample-dataset buttons
- [ ] Loading the **Sales** sample dataset works and all 6 tabs render
- [ ] The dark cyan theme matches your local screenshots (confirms `.streamlit/config.toml` deployed correctly)
- [ ] The sidebar's "AI Analyst" status caption reads "API key detected" (confirms the secret is wired up)
- [ ] Ask the AI Analyst a simple question and confirm it responds

---

## 5. Redeploying after changes

Streamlit Community Cloud auto-redeploys on every push to the connected
branch. Just:

```bash
git add .
git commit -m "..."
git push
```

...and the live app updates within a minute or two. If you change
`requirements.txt`, the rebuild takes a bit longer (new packages need
installing).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| App shows "Add your free Gemini API key..." even though you set a secret | Secret key name doesn't match exactly | Confirm the secret is named `GEMINI_API_KEY` (case-sensitive), not `GOOGLE_API_KEY` or similar |
| Build fails installing `duckdb` or `scikit-learn` | Rare platform/wheel mismatch | Check the build log; usually resolves by re-running "Reboot app" from the ⋮ menu |
| Voice input's mic button does nothing | Browser blocked mic permission, or the site isn't served over HTTPS | Streamlit Cloud always serves over HTTPS, so this is almost always a browser permission prompt — check your browser's site settings |
| App is slow / runs out of memory on large files | Streamlit Community Cloud's free tier caps at ~1 GB RAM | Prism already samples files over 50,000 rows; if you still hit limits, test with a smaller file or upgrade to a paid Streamlit Cloud tier |
| "This app has gone to sleep" | Free-tier apps sleep after a period of inactivity | Just reload the page — it wakes up in a few seconds |

---

## What actually changes between local and Cloud

Nothing in the app code. The only difference is *where* `GEMINI_API_KEY`
comes from:

| Environment | Source |
|---|---|
| Local (`streamlit run app.py`) | `.env` file → `python-dotenv` → `os.environ` |
| Streamlit Community Cloud | Secrets manager → `st.secrets` |

`ai_analyst.get_api_key()` tries `st.secrets` first, then falls back to the
environment — so the same `app.py`, unmodified, runs correctly in both places.
