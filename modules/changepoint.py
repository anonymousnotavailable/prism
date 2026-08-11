"""
Changepoint Detection — where does a time series' *level* actually shift,
not just drift? modules.forecasting's STL decomposition explains smooth
trend/seasonal movement; this answers a different question: "at which
point(s) did the underlying process step to a genuinely different regime"
(a pricing change, an outage, a policy switch, a sensor recalibration).

Algorithm: binary segmentation with a CUSUM (cumulative sum) test statistic,
the textbook simpler sibling of PELT (Pruned Exact Linear Time) — same
"recursively split on the strongest candidate break" idea the `ruptures`
library calls `Binseg`, minus the pruning optimization PELT adds for
performance at scale, which this app's row counts don't need. No `ruptures`
dependency — pure numpy/pandas, same footprint philosophy as
modules.bayesian_ab and modules.did.

For a segment, the CUSUM statistic at split point k is:

    S_k = sum_{i=1}^{k} (x_i - xbar)          (running sum of demeaned values)
    stat = max_k |S_k| / (sigma * sqrt(n))     (normalized, sigma = sample std)

The location that maximizes |S_k| is the single most likely changepoint in
that segment (Page 1954's original CUSUM idea). Whether it's a *real* break
or just the strongest fluctuation noise happens to produce is decided by a
permutation test: shuffle the segment's values (destroying any true
changepoint while preserving its overall distribution) many times, recompute
the CUSUM statistic each time, and see how often a reshuffled segment
produces a statistic at least as extreme as the one observed. A low
resulting p-value means the observed break is unlikely to be a fluke.

`detect_changepoints` runs this recursively (binary segmentation): start
with the whole series as one candidate segment, and repeatedly pop the
strongest not-yet-tested candidate split (a max-heap keyed by CUSUM
statistic magnitude, so the most obvious breaks are found — and confirmed
significant, or discarded — before weaker ones are even considered), test
it for significance, and if it passes, split the segment there and push its
two halves back in as new candidates. Stops when the heap is empty, no
segment is large enough to test, or `max_changepoints` is reached.

One real limitation, stated plainly rather than glossed over (same
convention as modules.did's parallel-trends caveat and modules.power_
analysis's post-hoc-power caveat): CUSUM detects shifts in a series that is
otherwise *stationary* between breaks — a strongly trending series (with no
actual regime change) can itself trip a false positive, since a smooth
trend also produces a large cumulative sum. `changepoint_verdict` and the
UI caption both say so.

100% local compute (numpy/pandas). narrate_changepoints() is an optional
plain-English layer on an already-computed result, same call_gemini()
plumbing and graceful no-model fallback as every other narrate_* helper in
the app. Callers are responsible for caching its result, same convention as
those.
"""

from __future__ import annotations

import heapq
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go

# Below this many points, a segment can't be meaningfully split (each half
# would be too small to estimate a stable mean from) — same spirit as
# modules.did's _MIN_CELL_SIZE, just for a contiguous run instead of a
# group x period cell.
DEFAULT_MIN_SEGMENT_SIZE = 10
DEFAULT_MAX_CHANGEPOINTS = 10
DEFAULT_SIGNIFICANCE = 0.05
DEFAULT_N_PERMUTATIONS = 999


def cusum_stat(values: np.ndarray) -> tuple[float, int]:
    """Normalized CUSUM statistic and its argmax split location for `values`.

    Returns (stat, loc) where `loc` is the 0-based index such that the best
    candidate split is between values[loc] and values[loc + 1] (i.e. segment
    A = values[:loc + 1], segment B = values[loc + 1:]). `stat` is 0.0 for a
    constant series (nothing to detect — no zero-division).

    Raises ValueError if `values` has fewer than 2 points.
    """
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n < 2:
        raise ValueError("cusum_stat needs at least 2 points.")

    demeaned = values - values.mean()
    cumsum = np.cumsum(demeaned)
    sigma = values.std(ddof=0)
    if sigma == 0.0:
        return 0.0, n // 2

    loc = int(np.argmax(np.abs(cumsum)))
    stat = float(np.abs(cumsum[loc])) / (sigma * np.sqrt(n))
    return stat, loc


def _cusum_stat_restricted(values: np.ndarray, min_side: int) -> tuple[float, Optional[int]]:
    """Same statistic as cusum_stat, but the argmax search is restricted to
    split points that leave at least `min_side` points on each side. Used
    internally so a candidate segment can never be split into a big piece
    plus a sliver smaller than `min_segment_size` — cusum_stat's unrestricted
    argmax can otherwise land one or two points from either edge, which
    binary segmentation would then "confirm" as a spurious extra changepoint
    the next time that sliver is reconsidered.

    Returns (stat, loc); loc is None when the segment is too short for any
    valid interior split (stat is 0.0 in that case too).
    """
    n = len(values)
    lo, hi = min_side - 1, n - min_side - 1
    if lo > hi:
        return 0.0, None
    sigma = values.std(ddof=0)
    if sigma == 0.0:
        return 0.0, None
    cumsum = np.cumsum(values - values.mean())
    window = np.abs(cumsum[lo:hi + 1])
    rel_loc = int(np.argmax(window))
    loc = lo + rel_loc
    stat = float(np.abs(cumsum[loc])) / (sigma * np.sqrt(n))
    return stat, loc


def _permutation_pvalue_restricted(values: np.ndarray, observed_stat: float, min_side: int, n_permutations: int, rng: np.random.Generator) -> float:
    """Same idea as a CUSUM permutation test, but using the min-side-
    restricted statistic so the null distribution matches how the observed
    statistic was actually computed.
    """
    count_at_least_as_extreme = 0
    shuffled = values.copy()
    for _ in range(n_permutations):
        rng.shuffle(shuffled)
        stat, _ = _cusum_stat_restricted(shuffled, min_side)
        if stat >= observed_stat:
            count_at_least_as_extreme += 1
    # +1/+1 Laplace correction (Davison & Hinkley) — a p-value of exactly 0
    # from a finite number of permutations overstates confidence.
    return (count_at_least_as_extreme + 1) / (n_permutations + 1)


def detect_changepoints(
    series: pd.Series,
    max_changepoints: int = DEFAULT_MAX_CHANGEPOINTS,
    significance: float = DEFAULT_SIGNIFICANCE,
    min_segment_size: int = DEFAULT_MIN_SEGMENT_SIZE,
    n_permutations: int = DEFAULT_N_PERMUTATIONS,
    seed: int = 42,
) -> dict:
    """Binary-segmentation changepoint detection over `series` (mean shifts).

    Returns a dict:
      ok: bool
      error: str (only when ok is False)
      n: number of clean (non-null) points used
      values / index: the cleaned numpy array / pandas Index actually used
      changepoints: list of {position, index_label, before_mean, after_mean,
          delta, direction, p_value}, sorted by position. `p_value` is the
          raw permutation p-value for that split; a split is only accepted
          in the first place once it clears `significance` divided by the
          tree-depth Bonferroni correction described above, so every
          accepted changepoint is meaningfully more significant than a bare
          "p < significance" reading of its own p_value would suggest.
      segments: list of {start_position, end_position, start_label,
          end_label, n, mean, std}, covering the full clean series with no
          gaps or overlaps
    """
    clean = series.dropna()
    if not pd.api.types.is_numeric_dtype(clean):
        return {"ok": False, "error": "Series must be numeric to detect changepoints."}
    values = np.asarray(clean.values, dtype=float)

    n = len(values)
    if n < 2 * min_segment_size:
        return {
            "ok": False,
            "error": f"Only {n} non-null points — need at least {2 * min_segment_size} "
                     f"({min_segment_size} per side of a candidate split) to test for a changepoint.",
        }

    rng = np.random.default_rng(seed)
    index = clean.index

    # Binary segmentation recursively re-tests each half of every accepted
    # split, which — left uncorrected — compounds the overall false-positive
    # rate across the whole procedure (the same "many implicit comparisons"
    # problem modules.hypothesis_sweep corrects for with Benjamini-Hochberg
    # across its flat set of tests; here the tests form a recursion tree
    # instead, so a Bonferroni-style correction over the tree's depth —
    # log2(n / min_segment_size), the worst-case number of recursive
    # halvings — is the calibrated fix rather than an arbitrarily stricter
    # fixed threshold). `p_value` reported per changepoint is still the raw,
    # uncorrected permutation p-value for transparency; `effective_alpha` is
    # what it's actually compared against.
    max_depth = max(1, int(np.ceil(np.log2(max(2.0, n / min_segment_size)))))
    effective_alpha = significance / max_depth

    # Max-heap over candidate segments, keyed by CUSUM statistic magnitude
    # (negated, since heapq is a min-heap) so the strongest, most obvious
    # break in the whole series is tested — and confirmed or discarded —
    # before weaker ones are even considered.
    heap: list[tuple[float, int, int]] = []  # (-stat, start, end)
    counter = 0  # tie-breaker so heap never compares (start, end) tuples

    def _push(start: int, end: int) -> None:
        nonlocal counter
        if end - start < 2 * min_segment_size:
            return
        stat, _ = _cusum_stat_restricted(values[start:end], min_segment_size)
        counter += 1
        heapq.heappush(heap, (-stat, counter, start, end))

    _push(0, n)

    changepoints: list[dict] = []
    while heap and len(changepoints) < max_changepoints:
        neg_stat, _, start, end = heapq.heappop(heap)
        segment = values[start:end]
        observed_stat, loc = _cusum_stat_restricted(segment, min_segment_size)
        if observed_stat == 0.0 or loc is None:
            continue
        p_value = _permutation_pvalue_restricted(segment, observed_stat, min_segment_size, n_permutations, rng)
        if p_value >= effective_alpha:
            continue

        split_pos = start + loc + 1  # absolute position: segment A ends here (exclusive)
        before_mean = float(values[start:split_pos].mean())
        after_mean = float(values[split_pos:end].mean())
        changepoints.append({
            "position": split_pos,
            "index_label": index[min(split_pos, n - 1)],
            "before_mean": before_mean,
            "after_mean": after_mean,
            "delta": after_mean - before_mean,
            "direction": "increase" if after_mean >= before_mean else "decrease",
            "p_value": p_value,
        })
        _push(start, split_pos)
        _push(split_pos, end)

    changepoints.sort(key=lambda cp: cp["position"])

    boundaries = [0] + [cp["position"] for cp in changepoints] + [n]
    segments = []
    for seg_start, seg_end in zip(boundaries[:-1], boundaries[1:]):
        seg_values = values[seg_start:seg_end]
        segments.append({
            "start_position": seg_start,
            "end_position": seg_end,
            "start_label": index[seg_start],
            "end_label": index[seg_end - 1],
            "n": int(seg_end - seg_start),
            "mean": float(seg_values.mean()),
            "std": float(seg_values.std(ddof=0)) if len(seg_values) > 1 else 0.0,
        })

    return {
        "ok": True,
        "n": n,
        "values": values,
        "index": index,
        "changepoints": changepoints,
        "segments": segments,
    }


def changepoint_verdict(result: dict) -> str:
    """Plain-text one-line summary of a detect_changepoints() result."""
    if not result.get("ok"):
        return f"Couldn't detect changepoints: {result.get('error', 'unknown error')}"

    n_cp = len(result["changepoints"])
    if n_cp == 0:
        return "No statistically significant changepoints found — the series looks stable in level throughout."

    biggest = max(result["changepoints"], key=lambda cp: abs(cp["delta"]))
    direction_word = "jumped up" if biggest["direction"] == "increase" else "dropped"
    plural = "changepoint" if n_cp == 1 else "changepoints"
    return (
        f"Found {n_cp} {plural}. The largest shift {direction_word} by {abs(biggest['delta']):.3g} "
        f"around {biggest['index_label']} (p={biggest['p_value']:.3g})."
    )


def build_changepoint_chart(result: dict, title: str = "Changepoint detection") -> Optional[go.Figure]:
    """Original series with a vertical dashed line at each detected
    changepoint and a horizontal segment-mean overlay, so the "before" and
    "after" levels the test compared are visible at a glance."""
    if not result.get("ok"):
        return None

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=result["index"], y=result["values"], mode="lines",
        name="series", line=dict(color="#6b7280", width=1.5),
    ))

    for seg in result["segments"]:
        fig.add_trace(go.Scatter(
            x=[seg["start_label"], seg["end_label"]], y=[seg["mean"], seg["mean"]],
            mode="lines", line=dict(color="#2563eb", width=3),
            name="segment mean", showlegend=False,
        ))

    for cp in result["changepoints"]:
        fig.add_vline(x=cp["index_label"], line_dash="dash", line_color="#dc2626", line_width=1.5)

    fig.update_layout(title=title, xaxis_title="", yaxis_title="value", showlegend=False)
    return fig


def narrate_changepoints(model, result: dict) -> tuple[str, Optional[str]]:
    """Ask Gemini to explain one detect_changepoints() result in plain
    English. Returns (narration, error) — never raises. Callers should
    cache the result rather than re-calling this on every rerun, same
    convention as modules.bayesian_ab.narrate_bayesian_ab.
    """
    if model is None:
        return "", "No Gemini model available for narration."
    if not result.get("ok"):
        return "", "No result to narrate."

    from modules.ai_analyst import call_gemini

    n_cp = len(result["changepoints"])
    if n_cp == 0:
        summary = "No statistically significant changepoints were found — the series' level looks stable throughout."
    else:
        lines = []
        for cp in result["changepoints"]:
            lines.append(
                f"- around {cp['index_label']}: {cp['before_mean']:.3g} -> {cp['after_mean']:.3g} "
                f"({cp['direction']}, delta={cp['delta']:+.3g}, p={cp['p_value']:.3g})"
            )
        summary = f"{n_cp} changepoint(s) detected via CUSUM binary segmentation:\n" + "\n".join(lines)

    prompt = (
        f"{summary}\n\n"
        "In 2-4 plain-English sentences for a non-technical stakeholder, explain what changed and when, "
        "and why it matters. Do not repeat the raw numbers verbatim — focus on the practical story "
        "(e.g. did something get better or worse, and around when did it happen)."
    )
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None
