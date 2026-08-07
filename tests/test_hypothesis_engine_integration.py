"""
Minimal integration test: the actual user-facing flow — load a bundled
sample dataset the way app.py does (modules.data_engine), detect column
types, then run the Hypothesis Engine end to end — with no mocking of the
pipeline it sits on top of (data_engine -> stats_lab).
"""

from __future__ import annotations

import pandas as pd

from modules import data_engine, hypothesis_engine as he

SAMPLE_PATH = "samples/sales_data.csv"


def test_end_to_end_on_bundled_sales_sample():
    df = pd.read_csv(SAMPLE_PATH)
    column_types = data_engine.detect_column_types(df)

    hypotheses = he.generate_hypotheses(df, column_types)

    # sales_data.csv has region (categorical) x revenue/quantity (numeric),
    # so at least one testable pair should exist and survive the pipeline.
    assert isinstance(hypotheses, list)
    for h in hypotheses:
        assert set(h.keys()) >= {
            "statement", "kind", "col_a", "col_b", "screen_score",
            "suggestion", "result", "verdict", "interpretation", "warnings",
        }
        assert h["verdict"] in {"supported", "not supported"}
        assert 0.0 <= h["result"]["p_value"] <= 1.0

    headline = he.narrate_headline(hypotheses)
    assert isinstance(headline, str) and headline
