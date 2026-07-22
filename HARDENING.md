# HARDENING.md — Real-World Corpus Fix Log

Every fix below was earned: it exists because a real, publicly-downloadable
dataset (see [`tools/corpus_registry.json`](tools/corpus_registry.json))
tripped Prism's engine when run through the 8-stage gauntlet
(`tools/corpus_gauntlet.py`), not because it seemed like a good idea in the
abstract. Fixes went into the shared engine — never a per-dataset
special case — per the rule: unparseable input becomes a clear error (at
load) or NaN + a report entry (during cleaning), never something silently
dropped or guessed at.

## Round 1 — first full corpus run: 48/54 stage-runs passed, 6 load failures

### Fix 1 — Delimiter sniffing (comma → semicolon → tab → pipe)

**Tripped by:** France Elus Locaux (`data.gouv.fr`'s semicolon-delimited
public-official CSV).

**Root cause:** `data_engine._read_csv_with_encoding_fallback()` always
parsed with `sep=","`. Outside the US/UK, semicolon-delimited CSVs are
common (often because the same locale uses a comma as the decimal
separator). Comma-parsing a semicolon file doesn't always fail loudly —
early rows with no embedded comma "succeed" as single-column garbage, then
`pandas` throws `ParserError: Expected 1 fields ... saw 2` the moment a
later row happens to contain one.

**Fix:** `data_engine.py` now tries `[",", ";", "\t", "|"]` in order, across
all three encoding fallbacks, and keeps the first delimiter that produces
more than one column. A delimiter that parses cleanly but yields exactly
one column is kept only as a last-resort fallback (a real single-column
CSV should still load), so it doesn't win over a delimiter that actually
splits the file. When the winning delimiter isn't a comma, `load_data()`
surfaces a warning explaining what was detected and why.

### Fix 2 — Extension permissiveness (don't gate on file extension)

**Tripped by:** all four `data.gov.in` API responses (URLs with no file
extension at all — the API path is a bare resource ID) and UCI Adult
Income's `adult.data` (a genuine, unusual-but-real extension UCI's own
static site serves the file under).

**Root cause:** `data_engine.load_data()` hard-rejected anything that
didn't end in `.csv`, `.xlsx`, or `.xls` with "Unsupported file type,"
even when the content was perfectly good delimited text. A file's
extension is a hint, not proof of its contents — and it's the one thing a
government open-data API or a UCI static mirror doesn't reliably control.

**Fix:** `load_data()` now only special-cases `.xlsx`/`.xls` (Excel needs a
different parser, not just a different `sep`); everything else — `.csv`,
`.txt`, `.dat`, `.data`, or no extension — is treated as a delimited-text
candidate and run through the same encoding/delimiter sniffing above. If
the content genuinely isn't delimited text, the parser still raises a
specific, clear error (`EmptyDataError`, `ParserError`, etc.) — nothing is
silently accepted.

### Fix 3 — Downloader filename hygiene (not an engine bug, but worth fixing)

**Tripped by:** the same four `data.gov.in` entries — `tools/corpus.py`'s
`_safe_filename()` fell back to a generic `.dat` extension for any URL with
no path extension, even though the registry entry already declares
`"format": "csv"`. That's a downloader-naming defect, not evidence Prism's
engine can't handle these files (Fix 2 above makes the extension
irrelevant either way, but a cache file's name should still describe what's
actually inside it).

**Fix:** `_safe_filename()` now falls back to the registry's own declared
`format` field instead of a hardcoded `.dat` when neither a `zip_member`
nor the URL supplies a real extension.

## Round 2 — scorecard review surfaced a silent bug behind a passing stage

Round 1's fixes made every stage report PASS, but "load succeeded" isn't
the same as "load did the right thing." Building the badge table's
row-count column against `corpus_scorecard.json` surfaced a mismatch: UCI
Adult Income's cached file has 32,561 data rows, but Prism reported 32,560
after cleaning — one row silently missing, on a dataset with a green
`load: PASS`.

### Fix 4 — Detecting a missing header row (not just a missing header cell)

**Tripped by:** UCI Adult Income (`adult.data` — the file has no header
row at all, a deliberate quirk of this classic UCI dataset).

**Root cause:** `pd.read_csv(...)` defaults to `header=0`, so when a file
has no header row, the parser silently treats the first real data row as
column names. Nothing raises — it just drops a row and produces garbage
column labels (`'39'`, `' State-gov'`, `' 77516'`, ...), which then
propagate through Auto Cleaner, the dashboard, and the AI Analyst as if
they were real column names.

A first attempt at a heuristic ("if most 'header' cells parse as numbers,
it's not a real header") missed this case: only 6 of Adult Income's 15
columns are numeric, so "6/15 header cells look numeric" fell under a
50% threshold designed for an all-numeric file. Real datasets are
routinely a realistic mix of numeric and categorical columns, so a
whole-row numeric ratio is too blunt a signal.

**Fix:** `_header_row_is_probably_data()` now looks only at the columns
pandas already inferred as numeric dtype from the body, and checks whether
*every one* of those columns' header label also happens to look numeric —
a real header for a numeric column is a name like `"age"`, essentially
never a number itself. Requiring at least two such columns (not just one)
rules out the rare legitimate case of a single intentionally-numeric
column name (e.g. a `"2024"` year column). When triggered, Prism re-reads
the file with `header=None`, keeps every row (no more silent row loss),
and assigns generic `Column_1, Column_2, ...` names — with a warning
explaining what happened, since there's no real header text to recover.

## Result

Re-ran the full 12-dataset / 8-stage corpus three consecutive times right
after Round 1's fixes (delimiter/extension sniffing): **96/96 stage-runs
passed each time**, zero tracebacks. Round 2's header-detection fix was
then verified independently (a direct `load_data()` call confirmed UCI
Adult Income now reads all 32,561 rows with generic column names, instead
of silently losing one row to a garbage header) and by one further full
corpus run, whose scorecard (`corpus_scorecard.json`) confirms the fix is
live end-to-end. `eval/autocleaner_eval.py` remained 8/8 throughout,
confirming the header-detection heuristic doesn't misfire on any of
Prism's existing sample datasets (all of which have real headers).

That run had exactly one stage failure, and it's worth calling out
explicitly since it's *not* a Prism defect: `data.gov.in Census Sex Ratio
and Growth Rate`'s `ai_questions` stage failed with `Daily free-tier quota
exceeded for the Gemini API`. The stage's own error handling caught this
cleanly — no traceback, no crash, the run continued straight to `export`
and finished normally. Two more full runs immediately after came back
96/96 clean both times, confirming this was a transient rate-limit blip
(the free tier's per-minute limit, not the daily one, despite the error
text) rather than a real quota exhaustion — every other dataset's
`ai_questions` stage in that same run had already succeeded. This is the
harness working as designed: isolate the failure, keep going, report it
honestly, and don't chase an external flake with a code change.

## What was *not* touched

- **Kaggle entries (4)** are skipped, not failed, when no `KAGGLE_USERNAME`
  / `KAGGLE_KEY` is configured — this is correct, expected behavior for a
  benchmark that can't assume every environment has a personal Kaggle key,
  not a gap to route around.
- **UCI Bank Marketing's nested zip** (`bank.zip > bank-full.csv`) and
  **UCI Online Retail's `.xlsx` under a `.zip`** both worked on the first
  run — `tools/corpus.py`'s existing `>`-separated `zip_member` extraction
  already handled zip-of-zips correctly.
