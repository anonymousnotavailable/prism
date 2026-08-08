# Working with other AI agents on this repo

Prism is developed with the help of multiple AI coding agents — **Claude
Code** and **Codex** — working on behalf of the same maintainer, often in
separate sessions that don't share context with each other. This file is
the handoff point between them.

## The one rule

**Whenever you (any agent, in any session) make a change to this repo,
add a dated entry to the Change Log below before you're done** — a few
lines is enough: what changed, why, and which files. The next agent to
touch this repo (Claude or Codex, today or in six months) should be able
to read this file top-to-bottom and know what's already been done and
why, without re-deriving it from a diff.

This applies to design/UI passes, refactors, dependency changes, bug
fixes — anything a collaborator would want to know about before building
on top of it. Trivial fixes (typos, formatting) don't need an entry.

## Conventions already established

- **Theming**: `modules/theme.py` is a token-driven multi-theme system —
  see its module docstring. Add a new look by adding a new `THEMES[...]`
  dict entry (and, if it needs structural rules a token can't express —
  no-blur, different radii, a second font — a small override block like
  `_SLASH_OVERRIDES`), not by hand-editing the shared CSS template.
- **Styling lives in `modules/theme.py`; content lives in `modules/ui.py`**
  — see `modules/ui.py`'s module docstring for the split.
- Component modules under `modules/` are one file per feature area
  (`autocleaner.py`, `forecasting.py`, `mllab.py`, ...) — new features
  should follow that pattern rather than growing `app.py` further.

## Change Log

Newest first.

### 2026-08-08 — Slash brand theme (design system swap)
**Agent:** Claude Code · **Files:** `modules/theme.py`, `.streamlit/config.toml`

Implemented a client-supplied brand style reference ("Slash — Style
Reference": midnight-vault fintech aesthetic — obsidian canvas, Ivy Presto
serif headings substituted with Playfair Display, Inter body, Copper as
the single chromatic accent, pill controls, hairline borders instead of
shadows/blur) as a new theme, `THEMES["slash"]`, and made it
`DEFAULT_THEME`. Added `_SLASH_OVERRIDES` — a second `<style>` block
injected only when this theme is active — to express the things color
tokens alone can't (no blur/glow anywhere, pill vs. 2px vs. 10px radius by
role, serif-only-above-28px, monochrome icons, gilded-gradient chart/health
-ring accent instead of the HUD cyan/violet sweep). The prior 6 themes
(`prism_hud`, `graphite`, `midnight`, `arctic`, `obsidian`, `emerald`) are
untouched and still selectable from the sidebar theme picker — this was
additive, not destructive. `.streamlit/config.toml`'s first-paint colors
were updated to match so there's no color flash before the injected CSS
loads.

Verified: all 7 themes substitute through `_CSS_TEMPLATE` with no missing
placeholders (each theme dict carries the same keys); smoke-tested the
running app (landing hero, feature cards, loaded-dataset dashboard, Atlas
panel) via Playwright screenshots before committing.

### 2026-08-08 — Prism HUD soft-glass refinement
**Agent:** Claude Code · **Files:** `modules/theme.py`

Refined the (then-default) `prism_hud` theme into an Apple-style soft
glassmorphism system: new azure/violet/rose accent trio, heavier/consistent
`backdrop-filter` blur+saturate across sidebar/cards/Atlas panel/dataset
chip/column-profiler cards (previously inconsistent — 3 of 6 themes had
opaque surfaces where blur was a no-op), an ambient aurora background wash,
light-sweep hover micro-interactions on cards, a glossy highlight on
gradient buttons, and a glass-framed treatment for Plotly charts. Added
`--prism-dur-fast/med/slow` motion tokens. Recomputed `on_accent` contrast
for the new accent pair (~7.0–7.9:1, clears WCAG AA/AAA). Scoped to
`prism_hud`'s own tokens plus shared theme-agnostic CSS — the other 5
themes' color tokens were untouched.

Caught and fixed a real bug along the way: an early version of the aurora
background gave `.stApp` `position: relative`, which silently overrode
Streamlit's own layout rule for that element and collapsed the whole app to
zero height. Fixed before commit; verified via a live Playwright run.

*(Superseded as the default theme by the Slash entry above, but still
selectable — see that entry.)*
