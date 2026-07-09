"""
AI Analyst — turns plain-English questions into pandas code via the Google
Gemini API, executes that code in a restricted sandbox, and returns the
result for display. Also generates 5 analyst-style key findings.

Architecture (safe execution):
    question --> Gemini (schema + sample + stats + chat history, NEVER the
    full dataset) --> ```python code block --> restricted exec() (only df,
    pd, np in scope; import/eval/exec/dunder/subprocess/requests rejected
    outright) --> on failure, the error is sent back to Gemini exactly once
    for a corrected version ("self-healing retry") --> final result.

Setup: put GEMINI_API_KEY=... in a .env file at the project root (see
.env.example). Get a free key at https://aistudio.google.com/apikey.
"""

from __future__ import annotations

import os
import re
from typing import Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv

try:
    import google.generativeai as genai
    from google.api_core import exceptions as google_exceptions
except ImportError:  # the app should still load even if the package isn't installed yet
    genai = None
    google_exceptions = None

# Populate os.environ from a .env file in the project root, if one exists.
# Safe to call even when no .env is present — it's then a no-op.
load_dotenv()

MODEL_NAME = "gemini-2.5-flash"

GEMINI_SETUP_HELP = (
    "**Add your free Gemini API key to unlock AI features.**\n\n"
    "Locally: create a `.env` file in the project root with `GEMINI_API_KEY=your_key_here` "
    "(see `.env.example`), then restart the app.\n\n"
    "On Streamlit Community Cloud: add `GEMINI_API_KEY` under your app's "
    "**Settings → Secrets** (see `DEPLOYMENT.md`).\n\n"
    "[Get a free key at aistudio.google.com](https://aistudio.google.com/apikey)"
)

# Belt-and-suspenders keyword blocklist, checked before anything is executed.
# The restricted exec() namespace below is the real safety boundary (no
# __import__, no file/network builtins) — this list just rejects obviously
# hostile code earlier, with a clearer error message than a raised NameError.
_FORBIDDEN_PATTERNS = [
    "import os", "import sys", "open(", "eval(", "exec(", "__",
    "subprocess", "requests", "socket", "shutil", "compile(",
]

# The only builtins the generated code is allowed to call. Everything that
# touches the filesystem, network, process, or Python internals is excluded.
_ALLOWED_BUILTIN_NAMES = [
    "len", "range", "min", "max", "sum", "sorted", "list", "dict", "set",
    "tuple", "str", "int", "float", "bool", "round", "zip", "enumerate",
    "abs", "all", "any", "reversed", "map", "filter",
]

CODE_SYSTEM_PROMPT = (
    "You are a data analyst assistant embedded in a Streamlit app. The user has a "
    "pandas DataFrame called `df` already loaded in memory. Given the dataframe's "
    "schema, a sample, and summary statistics, write Python code that answers the "
    "user's question.\n\n"
    "Rules:\n"
    "- Use only `df`, `pd` (pandas), and `np` (numpy) — nothing else is available.\n"
    "- Do not import anything, read/write files, or use network/system calls.\n"
    "- Assign the final answer to a variable named `result`. It should be a "
    "DataFrame, Series, or scalar — whichever best answers the question.\n"
    "- Return ONLY a single ```python code block, no prose before or after it."
)

# Keywords that suggest a chat answer would benefit from a chart alongside the
# raw table/number — used by question_implies_chart() below.
_TREND_KEYWORDS = [
    "trend", "over time", "compare", "comparison", "vs", "versus", " by ",
    "growth", "change", "correlation", "distribution", "group", "across", "per ",
]


def get_api_key() -> str:
    """Read GEMINI_API_KEY — st.secrets first (how Streamlit Community Cloud
    injects secrets), then the environment (populated from .env by
    load_dotenv() above, for local dev). A lazy streamlit import keeps this
    module usable outside a Streamlit run context (e.g. in plain scripts/tests).
    """
    try:
        import streamlit as st

        secret_key = st.secrets.get("GEMINI_API_KEY")
        if secret_key:
            return secret_key
    except Exception:
        pass  # no secrets.toml locally, or not running inside Streamlit — fall through
    return os.getenv("GEMINI_API_KEY", "")


def get_model(api_key: Optional[str] = None):
    """Build a configured Gemini model instance, or None if unavailable."""
    key = api_key or get_api_key()
    if not key or genai is None:
        return None
    genai.configure(api_key=key)
    return genai.GenerativeModel(MODEL_NAME, system_instruction=CODE_SYSTEM_PROMPT)


def build_data_context(df: pd.DataFrame, column_types: dict[str, str]) -> str:
    """Summarize the dataframe's schema, a 5-row sample, and summary stats.

    This — never the full dataset — is what goes to Gemini on every request.
    """
    schema_lines = [f"- {col}: {dtype} ({column_types.get(col, 'unknown')})" for col, dtype in df.dtypes.items()]
    sample = df.head(5).to_string()
    try:
        stats = df.describe(include="all").transpose().to_string()
    except Exception:
        stats = "(summary statistics unavailable)"

    return (
        f"DataFrame shape: {df.shape[0]} rows x {df.shape[1]} columns\n\n"
        "Columns and dtypes:\n" + "\n".join(schema_lines) + "\n\n"
        f"Sample rows (first 5):\n{sample}\n\n"
        f"Summary statistics:\n{stats}"
    )


def history_to_contents(chat_history: list[dict]) -> list[dict]:
    """Convert app-level chat history into Gemini's {role, parts} turn format.

    Assistant turns are represented by the code they produced (or the error,
    if the request itself failed) rather than the full result — enough for
    Gemini to keep continuity across follow-up questions without resending data.
    """
    contents = []
    for msg in chat_history:
        if msg["role"] == "user":
            contents.append({"role": "user", "parts": [msg["content"]]})
        else:
            if msg.get("ask_error"):
                text = "(The previous request failed and was not shown to the user.)"
            elif msg.get("code"):
                text = f"```python\n{msg['code']}\n```"
            else:
                text = "(no code generated)"
            contents.append({"role": "model", "parts": [text]})
    return contents


_CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL)


def extract_code(response_text: str) -> str:
    """Pull the first ```python ...``` block out of Gemini's reply, or fall back to the raw text."""
    match = _CODE_BLOCK_RE.search(response_text)
    return match.group(1).strip() if match else response_text.strip()


def call_gemini(model, contents) -> tuple[str, Optional[str]]:
    """Shared error handling around model.generate_content — used by both the
    chat and key-insights flows so quota/auth failures read the same way everywhere.
    """
    try:
        response = model.generate_content(contents)
    except google_exceptions.ResourceExhausted:
        return "", (
            "Daily free-tier quota exceeded for the Gemini API. Try again later, "
            "or check your usage at https://aistudio.google.com/."
        )
    except google_exceptions.PermissionDenied:
        return "", "Gemini rejected the request — check that GEMINI_API_KEY in your .env file is valid."
    except Exception as e:
        return "", f"Gemini request failed: {e}"
    return response.text, None


def explain_sql(model, sql: str) -> tuple[str, Optional[str]]:
    """Ask Gemini to explain a SQL query in plain English — the SQL Lab tab's
    "Explain this query" button. Kept independent of the pandas chat/insights
    flows since it doesn't touch the dataframe at all, only the query text.
    """
    prompt = (
        "Explain what the following SQL query does, in plain English, in 2-4 sentences, "
        "for a non-technical stakeholder. Do not restate the raw SQL back verbatim.\n\n"
        f"```sql\n{sql}\n```"
    )
    text, error = call_gemini(model, prompt)
    if error:
        return "", error
    return text.strip(), None


def ask_question(
    model, df: pd.DataFrame, column_types: dict[str, str], question: str, chat_history: list[dict]
) -> tuple[str, Optional[str]]:
    """Ask Gemini to translate a plain-English question into pandas code.

    Returns (code, error). On an API error, code is "" and error explains why.
    """
    context = build_data_context(df, column_types)
    user_turn = {"role": "user", "parts": [f"Data context:\n{context}\n\nQuestion: {question}"]}
    contents = history_to_contents(chat_history) + [user_turn]

    text, error = call_gemini(model, contents)
    if error:
        return "", error
    return extract_code(text), None


def execute_code_safely(code: str, df: pd.DataFrame):
    """Run Gemini-generated pandas code in a locked-down namespace.

    Returns (result, error). `result` is whatever the generated code assigned
    to `result` — typically a DataFrame, Series, or scalar. Only `df`, `pd`,
    and `np` are exposed; no import, file, network, or dunder access.
    """
    lowered = code.lower()
    for pattern in _FORBIDDEN_PATTERNS:
        if pattern in lowered:
            return None, f"Generated code was rejected — it contains a disallowed operation ('{pattern.strip()}')."

    import builtins

    safe_builtins = {name: getattr(builtins, name) for name in _ALLOWED_BUILTIN_NAMES}

    exec_globals = {
        "__builtins__": safe_builtins,
        "pd": pd,
        "np": np,
        "df": df.copy(),  # never let generated code mutate the app's real DataFrame
    }
    exec_locals: dict = {}

    try:
        exec(code, exec_globals, exec_locals)
    except Exception as e:
        return None, f"The generated code raised an error: {e}"

    if "result" not in exec_locals:
        return None, "The generated code did not assign a `result` variable."

    return exec_locals["result"], None


def ask_and_execute(
    model, df: pd.DataFrame, column_types: dict[str, str], question: str, chat_history: list[dict]
) -> dict:
    """Full round trip: ask Gemini for code, run it, and self-heal once on failure.

    Returns a dict with keys:
      code          — the (possibly corrected) generated code, or None if the Gemini request itself failed
      result        — the executed result, or None
      error         — the *execution* error after the retry, if it still failed
      ask_error     — set only if the Gemini request itself failed (bad key, quota, network, ...)
      retried       — True if the first attempt failed and a self-healing retry was made
      original_error — the first attempt's error, kept for display when retried is True
    """
    code, ask_error = ask_question(model, df, column_types, question, chat_history)
    if ask_error:
        return {"code": None, "result": None, "error": None, "ask_error": ask_error, "retried": False}

    result, exec_error = execute_code_safely(code, df)
    if not exec_error:
        return {"code": code, "result": result, "error": None, "ask_error": None, "retried": False}

    # Self-healing retry: send the failing code + its error back to Gemini once.
    retry_prompt = (
        f"The following code raised an error when executed:\n```python\n{code}\n```\n"
        f"Error: {exec_error}\n\n"
        "Return a corrected version that fixes this error, following the same rules "
        "(use only df/pd/np, assign the answer to `result`, and return only a single "
        "```python code block)."
    )
    contents = history_to_contents(chat_history + [{"role": "user", "content": question}])
    contents.append({"role": "user", "parts": [retry_prompt]})

    text, retry_ask_error = call_gemini(model, contents)
    if retry_ask_error:
        return {
            "code": code, "result": None, "error": exec_error,
            "ask_error": f"Retry request failed: {retry_ask_error}", "retried": True, "original_error": exec_error,
        }

    corrected_code = extract_code(text)
    corrected_result, corrected_error = execute_code_safely(corrected_code, df)
    return {
        "code": corrected_code,
        "result": corrected_result,
        "error": corrected_error,
        "ask_error": None,
        "retried": True,
        "original_error": exec_error,
    }


def question_implies_chart(question: str) -> bool:
    """Heuristic: does this question ask for a trend/comparison worth also charting?"""
    q = question.lower()
    return any(kw in q for kw in _TREND_KEYWORDS)


def build_chart_from_result(result, title: str) -> Optional[go.Figure]:
    """Best-effort auto-chart for a pandas result. Returns None if the result
    doesn't lend itself to a chart (e.g. a scalar, or a single-row frame).

    This runs on the *already-computed* result — never on AI-generated code —
    so it's outside the sandbox and free to use Plotly directly.
    """
    try:
        if isinstance(result, pd.Series):
            series = result.dropna()
            if len(series) < 2:
                return None
            if pd.api.types.is_datetime64_any_dtype(series.index):
                fig = px.line(x=series.index, y=series.values, title=title)
            else:
                fig = px.bar(x=series.index.astype(str), y=series.values, title=title)
            fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
            return fig

        if isinstance(result, pd.DataFrame):
            if result.shape[0] < 2:
                return None
            numeric_cols = result.select_dtypes(include=np.number).columns.tolist()
            if not numeric_cols:
                return None
            y_col = numeric_cols[0]
            if pd.api.types.is_datetime64_any_dtype(result.index):
                fig = px.line(result, x=result.index, y=y_col, title=title)
            else:
                fig = px.bar(result, x=result.index.astype(str), y=y_col, title=title)
            fig.update_layout(margin=dict(t=50, b=10, l=10, r=10))
            return fig
    except Exception:
        return None
    return None


_INSIGHTS_PROMPT_TEMPLATE = (
    "{context}\n\n"
    "Missing values by column: {missing_summary}\n"
    "Outliers by column (IQR method): {outlier_summary}\n"
    "Duplicate rows: {duplicate_rows}\n"
    "Top correlations: {correlation_summary}\n\n"
    "You are a senior data analyst. Based only on the information above, write "
    "exactly 5 concise, analyst-style findings a business stakeholder would care "
    "about. Each finding MUST reference at least one concrete number from the "
    "statistics above (a mean, a percentage, a correlation coefficient, a count, "
    "etc.) — do not write vague statements. Format your response as exactly 5 "
    "lines, each starting with '1. ' through '5. ', with no other text before or after."
)

_BULLET_RE = re.compile(r"^\s*\d+[.)]\s*(.+)$")


def parse_numbered_bullets(text: str) -> list[str]:
    bullets = [m.group(1).strip() for line in text.splitlines() if (m := _BULLET_RE.match(line))]
    if not bullets:
        # Gemini didn't follow the numbering format — fall back to non-empty lines.
        bullets = [line.strip("-*\t ") for line in text.splitlines() if line.strip()]
    return bullets[:5]


def generate_key_insights(
    model,
    df: pd.DataFrame,
    quality_report: dict,
    column_types: dict[str, str],
    top_correlations: Optional[list[tuple[str, str, float]]] = None,
) -> tuple[list[str], Optional[str]]:
    """Ask Gemini for 5 analyst-style, number-referencing findings.

    Returns (bullets, error) — bullets is a list of up to 5 plain-text
    findings with their leading numbering already stripped, ready to render
    as cards.
    """
    context = build_data_context(df, column_types)
    missing_summary = (
        ", ".join(f"{col}: {pct}%" for col, pct in quality_report["missing_by_column"].items() if pct > 0) or "none"
    )
    outlier_summary = (
        ", ".join(
            f"{col}: {info['count']} ({info['pct']}%)"
            for col, info in quality_report["outliers"].items()
            if info["count"] > 0
        )
        or "none"
    )
    correlation_summary = (
        ", ".join(f"{a} vs {b}: {v:.2f}" for a, b, v in top_correlations) if top_correlations else "none"
    )

    prompt = _INSIGHTS_PROMPT_TEMPLATE.format(
        context=context,
        missing_summary=missing_summary,
        outlier_summary=outlier_summary,
        duplicate_rows=quality_report["duplicate_rows"],
        correlation_summary=correlation_summary,
    )

    text, error = call_gemini(model, prompt)
    if error:
        return [], error
    return parse_numbered_bullets(text), None
