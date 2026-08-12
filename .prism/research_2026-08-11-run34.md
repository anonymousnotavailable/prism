# Phase 2 Research — Run 34 (2026-08-12)

## Web Speech API browser support (2025-2026)

WebSearch confirms and refines what was assumed going in:

- **Chrome, Edge, Opera (Chromium family)**: full support for
  `SpeechRecognition`. Cloud-based only — audio is sent to a cloud service
  for processing, so it requires the browser to be online even though the
  API surface itself is entirely client-side JS (no server code in the
  hosting app is involved, which is the property this run's feature
  relies on).
- **Safari**: supported since 14.1+ (macOS) / 14.5+ (iOS/iPadOS) via the
  `webkitSpeechRecognition` prefix — **this contradicts the common
  assumption that Safari never implemented it.** Notably, Safari can run
  recognition fully **on-device** once the user grants permission and
  installs the relevant language pack, unlike Chrome/Edge's always-cloud
  approach — a genuine privacy/offline advantage worth knowing about, even
  though this run's implementation doesn't special-case it (feature
  detection picks it up automatically either way).
- **Firefox**: implemented but shipped disabled by default behind the
  `dom.webspeech.recognition.enable` about:config flag — effectively
  unsupported for the overwhelming majority of real users who will never
  touch that flag.
- **Practical takeaway for this run's implementation**: feature-detecting
  `window.SpeechRecognition || window.webkitSpeechRecognition` client-side
  (not user-agent sniffing) is confirmed as the only reliable approach —
  it correctly picks up Safari's support (which a hardcoded "Chrome/Edge
  only" allowlist would have missed) and correctly excludes default-
  Firefox. `modules/web_speech.py`'s docstring was updated after this
  search to no longer claim Safari has zero support.

Sources:
- https://textintoaudio.com/browser-support
- https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition
- https://www.testmuai.com/learning-hub/speech-recognition-api-browser-support/

## JARVIS-style copilot UX patterns (2025-2026)

- Persistent mic button in the primary action bar + a listening indicator
  as a privacy trust signal are cited as the core voice-UI pattern —
  matches what Prism's Atlas side panel + global command bar already do
  structurally (this run kept that shape, didn't redesign it).
- The dominant 2026 framing is "AI as a thoughtful copilot — present,
  optional, and respectful of human context," explicitly contrasted
  against an "all-knowing autopilot" pattern. Directly supports this run's
  scope decision to ship a mic **input** button (user-initiated,
  optional) rather than attempt proactive/ambient voice or an animated
  HUD in the same slice — that's explicitly named as a *separate*,
  larger pattern ("proactive voice... surfaces the right action before
  the user has to think about it") that the routine's own brief already
  flagged as future scope.
- "Structured error recovery" and "proactive status communication"
  (e.g. visible state like "listening…", explicit failure messages
  instead of silent no-ops) are named as one of four principles
  separating working agent UIs from failed ones — directly informed this
  run's insistence on a distinct, specific message per failure mode
  (unsupported browser / permission denied / no speech / network error /
  no mic found) rather than one generic fallback caption, which is what
  the previous `voice_input.py` path had.

Sources:
- https://www.letsgroto.com/blog/mastering-ai-copilot-design
- https://fuselabcreative.com/ui-design-for-ai-agents/
- https://fuselabcreative.com/voice-user-interface-design-guide-2026/

## Second-feature gap sweep

Per Run 33's already-thorough sweep (PCA, RFM, PSM, DiD, ensemble anomaly
detection, SHAP, conformal prediction, survival analysis, Bayesian A/B,
power analysis, text analytics, changepoint detection, Granger causality
all confirmed shipped), this run's sweep targeted `modules/stats_lab.py`
specifically since it hadn't been touched since its original build and its
`normality_warnings()` function looked like a suspicious dead end on
inspection (warns about a violated assumption with no alternative
offered). Confirmed via direct code read (`run_ttest`/`run_anova`/
`run_pearson` — all parametric, no rank-based alternative existed
anywhere in the codebase; `grep -ril "mannwhitney\|kruskal\|spearman"
modules/` came back empty before this run). This is the second feature —
full reasoning and scope justification in `.prism/routine_log.md`'s
selection-log entry and `RUN_REPORT_2026-08-11-run34.md`.
