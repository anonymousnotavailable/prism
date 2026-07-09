"""
Cleaning Recipes — "Save recipe" captures the current cleaning history
(already tracked as {"description", "code"} entries, the same ones behind
the sidebar's "Export as Python Script" button) as a named, portable JSON
recipe. "Apply recipe" re-runs that recipe's steps against any new
DataFrame, one at a time, in a restricted sandbox — skipping (never
crashing on) any step that doesn't apply to the new file, with a per-step
success/skip log.
"""

from __future__ import annotations

import builtins
import json
from datetime import datetime, timezone
from typing import Optional, Union

import numpy as np
import pandas as pd

from modules.type_coercion import parse_one as _prism_parse_numeric

RECIPE_FORMAT_VERSION = 1

# Same safety boundary as ai_analyst's sandbox: only df/pd/np (plus the
# type-coercion helper recipe steps may reference) are exposed, no
# import/eval/exec/dunder/subprocess/network access.
_FORBIDDEN_PATTERNS = [
    "import os", "import sys", "open(", "eval(", "exec(", "__",
    "subprocess", "requests", "socket", "shutil", "compile(",
]
_ALLOWED_BUILTIN_NAMES = [
    "len", "range", "min", "max", "sum", "sorted", "list", "dict", "set",
    "tuple", "str", "int", "float", "bool", "round", "zip", "enumerate",
    "abs", "all", "any", "reversed", "map", "filter",
]


def save_recipe(name: str, cleaning_log: list[dict]) -> str:
    """Serialize the current cleaning history as a named JSON recipe string."""
    recipe = {
        "format_version": RECIPE_FORMAT_VERSION,
        "name": name or "unnamed_recipe",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "steps": [{"description": step["description"], "code": step["code"]} for step in cleaning_log],
    }
    return json.dumps(recipe, indent=2)


def load_recipe(raw: Union[bytes, str]) -> tuple[dict, Optional[str]]:
    """Parse an uploaded recipe file. Returns (recipe, error)."""
    try:
        recipe = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {}, f"Not a valid recipe file: {e}"

    if not isinstance(recipe, dict) or "steps" not in recipe or not isinstance(recipe["steps"], list):
        return {}, "Not a valid Prism recipe — missing a 'steps' list."
    return recipe, None


def _run_step_code(code: str, current_df: pd.DataFrame) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    """Execute one recipe step's code against current_df in a restricted
    namespace. Returns (new_df, error) — new_df is None on failure.
    """
    lowered = code.lower()
    for pattern in _FORBIDDEN_PATTERNS:
        if pattern in lowered:
            return None, f"Step rejected — contains a disallowed operation ('{pattern.strip()}')."

    safe_builtins = {name: getattr(builtins, name) for name in _ALLOWED_BUILTIN_NAMES}
    exec_globals = {
        "__builtins__": safe_builtins,
        "pd": pd,
        "np": np,
        "df": current_df.copy(),
        "_prism_parse_numeric": _prism_parse_numeric,
    }
    exec_locals: dict = {}

    try:
        exec(code, exec_globals, exec_locals)
    except Exception as e:
        return None, str(e)

    result_df = exec_locals.get("df", exec_globals.get("df"))
    if not isinstance(result_df, pd.DataFrame):
        return None, "Step did not produce a valid DataFrame."
    return result_df, None


def apply_recipe(df: pd.DataFrame, recipe: dict) -> tuple[pd.DataFrame, list[dict]]:
    """Run each of the recipe's steps against df in order.

    Each step either succeeds (its output DataFrame feeds the next step) or
    is skipped with its error recorded — one bad step (a missing column, an
    unreproducible join to a file that isn't present) never aborts the rest
    of the recipe. Returns (final_df, step_log), where step_log is a list of
    {"description", "status": "applied"|"skipped", "detail"} dicts.
    """
    current_df = df.copy()
    step_log = []

    for step in recipe.get("steps", []):
        description = step.get("description", "(no description)")
        code = step.get("code", "")

        if not code.strip() or all(not line.strip() or line.strip().startswith("#") for line in code.splitlines()):
            step_log.append(
                {"description": description, "status": "skipped", "detail": "Informational step — no runnable code."}
            )
            continue

        new_df, error = _run_step_code(code, current_df)
        if error:
            step_log.append({"description": description, "status": "skipped", "detail": error})
        else:
            current_df = new_df
            step_log.append(
                {
                    "description": description,
                    "status": "applied",
                    "detail": f"{len(current_df):,} rows x {current_df.shape[1]} columns after this step.",
                }
            )

    return current_df, step_log
