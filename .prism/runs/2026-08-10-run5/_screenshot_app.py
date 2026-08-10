"""LOCAL-ONLY screenshot harness — not part of the app, never committed to a
feature branch's shipped code. Stubs Gemini so the Auto Analyst flow (which
requires a live API key to even show its "Run Full Analysis" button) can be
exercised headlessly to screenshot the new Auto-Verified Hypothesis Testing
UI. The deterministic parts (auto_verify_hypothesis, suggest_followup_hypothesis)
still run for real — only the LLM call itself is canned.
"""
import sys

sys.path.insert(0, ".")
import modules.ai_analyst as ai_analyst


def _fake_call_gemini(model, contents):
    text = str(contents).lower()
    if "ordered analysis plan" in text:
        return (
            '[{"title": "Data quality check", "question": "Summarize missing values and duplicate rows in df."}, '
            '{"title": "Correlations", "question": "Compute the correlation matrix between numeric columns in df '
            'and report the strongest pairwise correlation."}]',
            None,
        )
    if "5 concise" in text or "headline findings" in text:
        return ("1. Finding one.\n2. Finding two.\n3. Finding three.\n4. Finding four.\n5. Finding five.", None)
    if "hypothesis tested" in text:
        return (
            "This difference is statistically significant, so the pattern is unlikely to be due to "
            "chance and is worth acting on.",
            None,
        )
    return ("```python\nresult = df.describe()\n```", None)


ai_analyst.call_gemini = _fake_call_gemini
ai_analyst.get_model = lambda: object()

with open("app.py") as f:
    _code = f.read()
exec(compile(_code, "app.py", "exec"), {"__name__": "__main__", "__file__": "app.py"})
