# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Cross-agent handoff — read this first

This repo is also worked on by other AI agents (Codex) in separate
sessions. **Before finishing any task that changes files here, add a dated
entry to the Change Log in [`AGENTS.md`](./AGENTS.md)** summarizing what
changed, why, and which files — that file is the shared handoff point so
the next agent (Claude or Codex) doesn't have to re-derive context from a
diff. Read `AGENTS.md`'s Change Log at the start of a session too, to see
what's already been done.

## Project shape

- Streamlit single-page app (`app.py`) — no JS framework, styling is CSS
  injected via `modules/theme.py` (see that file's own docstring for the
  token-driven multi-theme system).
- `modules/theme.py` owns *styling*; `modules/ui.py` owns landing-page
  *content*. Keep that split.
- One module per feature area under `modules/` (`autocleaner.py`,
  `forecasting.py`, `mllab.py`, `atlas.py`, ...).
- See `DEPLOYMENT.md` for how this ships to Streamlit Community Cloud /
  Render, and `HARDENING.md` / `QA_CHECKLIST.md` for testing conventions.

## Before committing a UI/theme change

Boot the app (`streamlit run app.py --server.headless true`) and check it
with a real screenshot (Playwright is fine) before assuming a CSS change
works — this codebase has caught real layout bugs this way (see
`AGENTS.md`'s Change Log) that a syntax check alone would have missed.
