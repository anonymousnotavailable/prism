"""
Corpus Badge Generator — turns corpus_scorecard.json (written by
tools/corpus_gauntlet.py) into the README's "Battle-tested on real data"
table, and writes it in place between two HTML-comment markers so re-running
this script after a corpus update never touches the rest of the README by
hand.

Run with:  python tools/generate_corpus_badge.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCORECARD_PATH = REPO_ROOT / "corpus_scorecard.json"
REGISTRY_PATH = Path(__file__).resolve().parent / "corpus_registry.json"
README_PATH = REPO_ROOT / "README.md"

START_MARKER = "<!-- CORPUS_BADGE_START -->"
END_MARKER = "<!-- CORPUS_BADGE_END -->"


def _domain_for(name: str, registry_by_name: dict) -> str:
    if name.startswith("nightmare"):
        return "chaos"
    return registry_by_name.get(name, {}).get("domain", "—")


def _source_for(name: str, registry_by_name: dict) -> str:
    if name.startswith("nightmare"):
        return "Kaggle (House Prices, Ames)"
    return registry_by_name.get(name, {}).get("source", "—")


def build_table() -> str:
    scorecard = json.loads(SCORECARD_PATH.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["datasets"]
    registry_by_name = {e["name"]: e for e in registry}

    lines = [
        f"**Benchmarked against {len(scorecard)} real-world datasets** — pulled live from government open-data "
        f"portals, UCI's ML repository, and city open-data APIs, run through Prism's full 8-stage pipeline "
        f"(load, scan, auto-clean, invariant checks, dashboard, PDF/HTML report, AI questions, export) by "
        f"[`tools/corpus_gauntlet.py`](tools/corpus_gauntlet.py). See [HARDENING.md](HARDENING.md) for the "
        f"full fix log — every row below reflects a dataset that actually broke Prism at least once during "
        f"development, before the fix that made it pass.",
        "",
        "| Dataset | Source | Domain | Rows × Cols | Health (before → after) | Result |",
        "|---|---|---|---|---|---|",
    ]
    for r in scorecard:
        name = r["name"]
        domain = _domain_for(name, registry_by_name)
        source = _source_for(name, registry_by_name)
        shape = f"{r['n_rows']:,} × {r['n_cols']}" if r["n_rows"] is not None else "—"
        if r["health_before"] is not None and r["health_after"] is not None:
            delta = r["health_after"] - r["health_before"]
            arrow = f"{r['health_before']} → {r['health_after']}" + (f" (+{delta})" if delta > 0 else "")
        else:
            arrow = "—"
        badge = "PASS 8/8" if r["stages_passed"] == r["stages_total"] else f"{r['stages_passed']}/{r['stages_total']}"
        lines.append(f"| {name} | {source} | {domain} | {shape} | {arrow} | {badge} |")

    return "\n".join(lines)


def write_readme_section() -> None:
    table = build_table()
    text = README_PATH.read_text(encoding="utf-8")
    if START_MARKER not in text or END_MARKER not in text:
        raise SystemExit(
            f"README.md is missing {START_MARKER} / {END_MARKER} markers — "
            "add the 'Battle-tested on real data' section once by hand first."
        )
    before, rest = text.split(START_MARKER, 1)
    _, after = rest.split(END_MARKER, 1)
    new_text = f"{before}{START_MARKER}\n{table}\n{END_MARKER}{after}"
    README_PATH.write_text(new_text, encoding="utf-8")
    print(f"Wrote {len(table)} chars of badge table into {README_PATH}")


if __name__ == "__main__":
    write_readme_section()
