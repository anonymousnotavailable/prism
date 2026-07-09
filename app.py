"""
Prism — an Auto-EDA tool with an AI analyst layer.

Entry point: a landing screen (hero, feature cards, sample datasets, session
restore) that collapses into the sidebar (upload + cleaning controls) and six
main tabs (Overview / Clean / Combine / Visualize / SQL Lab / AI Analyst)
once a dataset is active. All the actual logic lives in modules/ — this file
is mostly Streamlit plumbing and state management.

Run with:  streamlit run app.py

Developed by Prathmesh Katkade.
"""

import numpy as np
import pandas as pd
import streamlit as st

from modules import (
    ai_analyst,
    anomaly,
    auto_analyst,
    cleaning,
    clustering,
    dashboard_builder,
    data_engine,
    datetime_intel,
    drift,
    forecasting,
    join_engine,
    pii_detector,
    profiling,
    recipes,
    report,
    report_writer,
    session_io,
    sql_lab,
    stats_lab,
    theme,
    type_coercion,
    ui,
    visualization,
    voice_input,
)

# --------------------------------------------------------------------------
# Page setup
# --------------------------------------------------------------------------
st.set_page_config(page_title="Prism | Auto-EDA & AI Analyst", page_icon="P", layout="wide")

# --------------------------------------------------------------------------
# Session state — this is Prism's "memory" between reruns. Streamlit reruns
# the whole script on every interaction, so anything that must survive a
# rerun (the loaded data, cleaning history, chat log) lives here.
# --------------------------------------------------------------------------
_DEFAULTS = {
    "raw_df": None,  # the dataset exactly as first loaded (for before/after + reset)
    "working_df": None,  # the dataset after any cleaning steps applied so far
    "column_types": {},  # column -> 'numeric' | 'categorical' | 'datetime' | 'text' | 'all_null'
    "cleaning_log": [],  # list of {"description": str, "code": str} — one per applied step
    "chat_history": [],  # AI Analyst chat transcript
    "key_insights": [],  # last "Generate Key Insights" output — list of up to 5 bullet strings
    "key_insights_error": None,  # error from the last "Generate Key Insights" attempt, if any
    "manual_chart_fig": None,  # last chart built via the Visualize tab's manual mode
    "manual_chart_error": None,  # error message from the last manual-chart build attempt, if any
    "last_file_name": None,  # detects a new upload vs. a plain rerun; also used in exports
    "sql_editor": "",  # SQL Lab's query text (bound to the text_area's key)
    "sql_result_df": None,  # last successful query result
    "sql_error": None,  # last query's error message, if any
    "sql_exec_time": None,  # last query's execution time in seconds
    "sql_explanation": "",  # last "Explain this query" output
    "sql_explanation_error": None,  # error from the last "Explain this query" attempt, if any
    "second_df": None,  # second file uploaded in the Combine tab (raw, uncleaned)
    "second_file_name": None,  # detects a new second-file upload vs. a plain rerun
    "combine_preview_df": None,  # last previewed join result
    "combine_stats": None,  # stats dict for the last previewed join
    "last_voice_text": None,  # dedupes repeated speech_to_text() return values across reruns
    "pending_voice_question": None,  # a transcribed question waiting to be fed into the chat pipeline
    "theme_mode": "dark",  # "dark" | "light" — sidebar toggle, default dark cyan
    "onboarding_dismissed": False,  # first-visit step-by-step intro, dismissible once per session
    "undo_stack": [],  # snapshots of {working_df, column_types, cleaning_log} before each mutation, capped at 10
    "anomaly_result_df": None,  # last "Find Anomalies" result
    "anomaly_error": None,  # error from the last anomaly-detection attempt, if any
    "auto_analyst_plan": None,  # last "Run Full Analysis" plan — list of {"title", "question"}
    "auto_analyst_step_outcomes": [],  # per-step results from the last Auto Analyst run
    "auto_analyst_findings": [],  # last Auto Analyst "top 5 findings" synthesis
    "auto_analyst_findings_error": None,  # error from the last findings synthesis, if any
    "stats_lab_result": None,  # last "Run Test" result dict from Stats Lab
    "forecast_result": None,  # last "Generate Forecast" result dict from Forecasting
    "forecast_error": None,  # error from the last forecast attempt, if any
    "cluster_result": None,  # last "Run Clustering" result dict
    "cluster_segment_names": [],  # last "Name Segments with AI" descriptions
    "cluster_segment_error": None,  # error from the last segment-naming attempt, if any
    "drift_result": None,  # last "Run Drift Comparison" report from the Combine tab's Compare mode
    "dashboard_spec": None,  # last "Build My Dashboard" spec (kpis + charts), editable via Remove/Swap
    "auto_report_content": None,  # last "Generate Report" content dict (for PDF/HTML export)
    "recipe_apply_log": [],  # last "Apply Recipe" per-step applied/skipped log
    "pii_findings": {},  # PII Detector's scan of the active dataset — {"email"/"phone"/"name": [...]}
}
for key, default_value in _DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default_value

theme.apply_custom_theme(st.session_state.theme_mode)
theme.apply_plotly_theme(st.session_state.theme_mode)

UNDO_STACK_CAP = 10


def push_undo_snapshot() -> None:
    """Capture the current working_df/column_types/cleaning_log so a later
    mutation can be undone. Call this BEFORE applying any cleaning action.
    """
    st.session_state.undo_stack.append(
        {
            "working_df": st.session_state.working_df.copy(),
            "column_types": dict(st.session_state.column_types),
            "cleaning_log": list(st.session_state.cleaning_log),
        }
    )
    if len(st.session_state.undo_stack) > UNDO_STACK_CAP:
        st.session_state.undo_stack.pop(0)


def log_step(description: str, code: str) -> None:
    """Append one entry to the cleaning history (used for display and for
    the "Export as Python Script" button).
    """
    st.session_state.cleaning_log.append({"description": description, "code": code})


def resolve_sheet_choice(uploaded_file, key_prefix: str):
    """For a multi-sheet Excel upload, render a picker and only report "ready"
    once the user confirms a sheet. CSVs and single-sheet workbooks are
    always immediately ready, so the common case has zero extra clicks.

    Returns (sheet_name_or_0, ready).
    """
    sheet_names = data_engine.get_excel_sheet_names(uploaded_file)
    if not sheet_names or len(sheet_names) <= 1:
        return 0, True
    st.info(f"This Excel file has {len(sheet_names)} sheets — pick one to load.")
    chosen = st.selectbox("Sheet", sheet_names, key=f"{key_prefix}_sheet_picker")
    confirmed = st.button("Load Selected Sheet", key=f"{key_prefix}_sheet_confirm", use_container_width=True)
    return chosen, confirmed


def set_active_dataset(raw_df, working_df, source_name, cleaning_log=None, chat_history=None) -> None:
    """Replace the entire active dataset and reset every piece of state tied
    to the previous one. Used by: a fresh sidebar upload, a sample dataset,
    a restored session, and the Combine tab's "Use as Active Dataset".
    """
    st.session_state.raw_df = raw_df
    st.session_state.working_df = working_df
    st.session_state.column_types = data_engine.detect_column_types(working_df)
    st.session_state.pii_findings = pii_detector.scan_dataframe(working_df, st.session_state.column_types)
    st.session_state.cleaning_log = cleaning_log if cleaning_log is not None else []
    st.session_state.chat_history = chat_history if chat_history is not None else []
    st.session_state.key_insights = []
    st.session_state.key_insights_error = None
    st.session_state.sql_result_df = None
    st.session_state.sql_error = None
    st.session_state.sql_explanation = ""
    st.session_state.sql_explanation_error = None
    st.session_state.second_df = None
    st.session_state.second_file_name = None
    st.session_state.combine_preview_df = None
    st.session_state.combine_stats = None
    st.session_state.manual_chart_fig = None
    st.session_state.manual_chart_error = None
    st.session_state.undo_stack = []
    st.session_state.anomaly_result_df = None
    st.session_state.anomaly_error = None
    st.session_state.auto_analyst_plan = None
    st.session_state.auto_analyst_step_outcomes = []
    st.session_state.auto_analyst_findings = []
    st.session_state.auto_analyst_findings_error = None
    st.session_state.stats_lab_result = None
    st.session_state.forecast_result = None
    st.session_state.forecast_error = None
    st.session_state.cluster_result = None
    st.session_state.cluster_segment_names = []
    st.session_state.cluster_segment_error = None
    st.session_state.drift_result = None
    st.session_state.dashboard_spec = None
    st.session_state.auto_report_content = None
    st.session_state.recipe_apply_log = []
    st.session_state.last_file_name = source_name


# --------------------------------------------------------------------------
# Sidebar — upload, theme toggle, cleaning controls + history, per the
# spec's UI layout. Rendered on every page, including the landing screen.
# --------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## PRISM")
    st.caption("Auto-EDA · AI Analyst")
    st.radio("Theme", ["dark", "light"], key="theme_mode", format_func=str.capitalize, horizontal=True)

    uploaded_file = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx", "xls"])

    if uploaded_file is not None and uploaded_file.name != st.session_state.last_file_name:
        sheet_choice, sheet_ready = resolve_sheet_choice(uploaded_file, "primary")
        if sheet_ready:
            with st.spinner("Reading and analyzing your data..."):
                new_df, load_error, load_warnings = data_engine.load_data(uploaded_file, sheet_name=sheet_choice)

            if load_error:
                st.error(load_error)
            else:
                set_active_dataset(new_df, new_df.copy(), uploaded_file.name)
                for w in load_warnings:
                    st.warning(w)
                st.success(f"Loaded {new_df.shape[0]:,} rows x {new_df.shape[1]} columns")

    working_df = st.session_state.working_df

    if working_df is not None:
        st.divider()
        st.markdown("### Cleaning Controls")

        # --- Missing values -------------------------------------------------
        with st.expander("Handle Missing Values", expanded=False):
            null_cols = [c for c in working_df.columns if working_df[c].isna().sum() > 0]
            if null_cols:
                with st.form("null_form"):
                    selected_cols = st.multiselect("Columns", null_cols, default=null_cols)
                    strategy_label = st.selectbox(
                        "Strategy",
                        ["Drop rows", "Fill with mean", "Fill with median", "Fill with mode", "Fill with custom value"],
                    )
                    custom_value = None
                    if strategy_label == "Fill with custom value":
                        custom_value = st.text_input("Custom value")
                    null_submitted = st.form_submit_button("Apply")

                if null_submitted:
                    strategy_map = {
                        "Drop rows": "drop_rows",
                        "Fill with mean": "fill_mean",
                        "Fill with median": "fill_median",
                        "Fill with mode": "fill_mode",
                        "Fill with custom value": "fill_custom",
                    }
                    strategy = strategy_map[strategy_label]
                    push_undo_snapshot()
                    new_df = working_df
                    apply_errors = []
                    for col in selected_cols:
                        try:
                            new_df = cleaning.handle_nulls(new_df, col, strategy, custom_value)
                            log_step(
                                f"Applied '{strategy_label}' to column '{col}'",
                                cleaning.nulls_code(col, strategy, custom_value),
                            )
                        except Exception as e:
                            apply_errors.append(str(e))
                    st.session_state.working_df = new_df
                    st.session_state.column_types = data_engine.detect_column_types(new_df)
                    for e in apply_errors:
                        st.error(e)
                    if not apply_errors:
                        st.toast("Missing-value strategy applied.")
            else:
                st.info("No missing values detected.")

        # --- Duplicates & columns --------------------------------------------
        with st.expander("Duplicates & Columns", expanded=False):
            n_dupes = int(working_df.duplicated().sum())
            st.write(f"Duplicate rows: **{n_dupes}**")
            if st.button("Remove Duplicate Rows", disabled=n_dupes == 0, use_container_width=True):
                push_undo_snapshot()
                new_df, removed = cleaning.remove_duplicates(working_df)
                st.session_state.working_df = new_df
                log_step(f"Removed {removed} duplicate row(s)", cleaning.duplicates_code())
                st.toast(f"Removed {removed} duplicate row(s).")

            all_null_cols = [c for c, t in st.session_state.column_types.items() if t == "all_null"]
            drop_choices = st.multiselect("Drop columns", working_df.columns.tolist(), default=all_null_cols)
            if st.button("Drop Selected Columns", disabled=not drop_choices, use_container_width=True):
                push_undo_snapshot()
                new_df = cleaning.drop_columns(working_df, drop_choices)
                st.session_state.working_df = new_df
                st.session_state.column_types = data_engine.detect_column_types(new_df)
                log_step(f"Dropped column(s): {', '.join(drop_choices)}", cleaning.drop_columns_code(drop_choices))
                st.toast("Column(s) dropped.")

        # --- Dtype fixes -------------------------------------------------------
        with st.expander("Fix Column Types", expanded=False):
            with st.form("dtype_form"):
                dtype_col = st.selectbox("Column", working_df.columns.tolist())
                target_type = st.selectbox("Convert to", ["numeric", "datetime", "text", "category"])
                dtype_submitted = st.form_submit_button("Convert")

            if dtype_submitted:
                new_df, dtype_error = cleaning.convert_dtype(working_df, dtype_col, target_type)
                if dtype_error:
                    st.error(dtype_error)
                else:
                    push_undo_snapshot()
                    st.session_state.working_df = new_df
                    st.session_state.column_types = data_engine.detect_column_types(new_df)
                    log_step(f"Converted '{dtype_col}' to {target_type}", cleaning.dtype_code(dtype_col, target_type))
                    st.toast(f"Converted '{dtype_col}' to {target_type}.")

        # --- Datetime feature extraction + gap detection -----------------------
        datetime_cols = [c for c, t in st.session_state.column_types.items() if t == "datetime"]
        if datetime_cols:
            with st.expander("Datetime Features", expanded=False):
                dt_col = st.selectbox("Column", datetime_cols, key="dt_feature_col")
                if st.button("Extract Year / Month / Day / Weekday / Quarter", use_container_width=True):
                    push_undo_snapshot()
                    new_df, added_cols = datetime_intel.extract_datetime_features(working_df, dt_col)
                    st.session_state.working_df = new_df
                    st.session_state.column_types = data_engine.detect_column_types(new_df)
                    log_step(
                        f"Extracted datetime features from '{dt_col}'", cleaning.datetime_features_code(dt_col)
                    )
                    st.toast(f"Added {len(added_cols)} new column(s) from '{dt_col}'.")

                gaps = datetime_intel.detect_gaps(working_df, dt_col)
                if gaps:
                    st.markdown("**Detected gaps** (assuming daily frequency)")
                    for gap in gaps[:5]:
                        st.caption(f"{gap['days_missing']} days missing between {gap['start']} and {gap['end']}")
                    if len(gaps) > 5:
                        st.caption(f"...and {len(gaps) - 5} more gap(s).")
                else:
                    st.caption("No gaps detected.")

        # --- Smart type coercion ------------------------------------------------
        coercion_candidates = type_coercion.detect_numeric_candidates(working_df, st.session_state.column_types)
        if coercion_candidates:
            with st.expander("Smart Type Coercion", expanded=False):
                for cand in coercion_candidates:
                    st.markdown(f"**{cand['column']}** — {cand['match_pct']}% look numeric")
                    _, preview_series = type_coercion.convert_column(working_df, cand["column"])
                    st.caption(f"Before: {', '.join(cand['sample_before'])}")
                    st.caption(f"After:  {', '.join(str(round(v, 2)) for v in preview_series.head(5))}")
                    if st.button(
                        f"Convert '{cand['column']}' to numeric",
                        key=f"coerce_{cand['column']}",
                        use_container_width=True,
                    ):
                        push_undo_snapshot()
                        converted_df, _ = type_coercion.convert_column(working_df, cand["column"])
                        st.session_state.working_df = converted_df
                        st.session_state.column_types = data_engine.detect_column_types(converted_df)
                        log_step(
                            f"Converted '{cand['column']}' from formatted text to numeric",
                            cleaning.type_coercion_code(cand["column"]),
                        )
                        st.toast(f"Converted '{cand['column']}' to numeric.")

        if st.button("Reset to Original Data", use_container_width=True):
            push_undo_snapshot()
            st.session_state.working_df = st.session_state.raw_df.copy()
            st.session_state.column_types = data_engine.detect_column_types(st.session_state.raw_df)
            st.toast("Reset to original uploaded data.")

        # --- Cleaning history, undo, export --------------------------------------
        st.divider()
        st.markdown("### Cleaning History")
        if st.session_state.cleaning_log:
            for i, step in enumerate(st.session_state.cleaning_log, 1):
                st.caption(f"{i}. {step['description']}")
        else:
            st.caption("No cleaning steps yet.")

        hc1, hc2 = st.columns(2)
        with hc1:
            if st.button("Undo", disabled=not st.session_state.undo_stack, use_container_width=True):
                snapshot = st.session_state.undo_stack.pop()
                st.session_state.working_df = snapshot["working_df"]
                st.session_state.column_types = snapshot["column_types"]
                st.session_state.cleaning_log = snapshot["cleaning_log"]
                st.toast("Reverted the last step.")
        with hc2:
            script_text = cleaning.export_script(st.session_state.cleaning_log, st.session_state.last_file_name)
            st.download_button(
                "Export .py",
                data=script_text.encode("utf-8"),
                file_name="prism_cleaning_script.py",
                mime="text/x-python",
                use_container_width=True,
                disabled=not st.session_state.cleaning_log,
            )

        # --- Cleaning recipes: save the history above as a named, reusable JSON
        # recipe, or apply a previously saved one to this dataset. ------------------
        st.divider()
        st.markdown("### Cleaning Recipes")
        recipe_name_input = st.text_input("Recipe name", value="my_cleaning_recipe", key="recipe_name_input")
        recipe_json_text = recipes.save_recipe(recipe_name_input, st.session_state.cleaning_log)
        st.download_button(
            "Save Recipe",
            data=recipe_json_text.encode("utf-8"),
            file_name=f"{recipe_name_input or 'prism_recipe'}.json",
            mime="application/json",
            use_container_width=True,
            disabled=not st.session_state.cleaning_log,
        )

        recipe_file = st.file_uploader("Apply a recipe to this dataset", type=["json"], key="recipe_uploader")
        if recipe_file is not None:
            loaded_recipe, recipe_load_error = recipes.load_recipe(recipe_file.getvalue())
            if recipe_load_error:
                st.error(recipe_load_error)
            elif st.button("Apply Recipe", use_container_width=True, key="apply_recipe_btn"):
                push_undo_snapshot()
                recipe_result_df, recipe_step_log = recipes.apply_recipe(working_df, loaded_recipe)
                st.session_state.working_df = recipe_result_df
                st.session_state.column_types = data_engine.detect_column_types(recipe_result_df)
                st.session_state.recipe_apply_log = recipe_step_log
                log_step(
                    f"Applied recipe '{loaded_recipe.get('name', 'unnamed')}'",
                    f"# Applied recipe: {loaded_recipe.get('name', 'unnamed')}",
                )
                st.toast(f"Applied recipe '{loaded_recipe.get('name', 'unnamed')}'.")

        if st.session_state.recipe_apply_log:
            with st.expander("Recipe apply log", expanded=True):
                for log_entry in st.session_state.recipe_apply_log:
                    status_label = "Applied" if log_entry["status"] == "applied" else "Skipped"
                    st.caption(f"**{status_label}** — {log_entry['description']}: {log_entry['detail']}")

        # --- Session save ---------------------------------------------------------
        st.divider()
        session_json = session_io.save_session(
            st.session_state.raw_df, st.session_state.working_df,
            st.session_state.cleaning_log, st.session_state.chat_history,
        )
        st.download_button(
            "Save Session",
            data=session_json.encode("utf-8"),
            file_name="prism_session.json",
            mime="application/json",
            use_container_width=True,
        )

        st.divider()
        st.markdown("### AI Analyst")
        if ai_analyst.get_api_key():
            st.caption(f"Gemini ({ai_analyst.MODEL_NAME}) — API key detected.")
        else:
            st.caption("No GEMINI_API_KEY found. See the AI Analyst tab for setup steps.")


# --------------------------------------------------------------------------
# Main area
# --------------------------------------------------------------------------
st.title("Prism")
st.caption("Auto-EDA · AI Analyst")

if st.session_state.working_df is None:
    # ---------------------------------------------------------------------
    # Landing screen — shown before any dataset is active.
    # ---------------------------------------------------------------------
    ui.render_hero()
    ui.render_feature_cards()
    st.divider()

    chosen_sample = ui.render_sample_buttons()
    if chosen_sample:
        sample_df = ui.load_sample_dataframe(chosen_sample)
        set_active_dataset(sample_df, sample_df.copy(), f"sample:{chosen_sample.lower()}.csv")
        st.toast(f"Loaded the {chosen_sample} sample dataset.")
        st.rerun()

    st.divider()
    session_file = ui.render_load_session_widget()
    if session_file is not None:
        bundle, session_load_error = session_io.load_session(session_file.getvalue())
        if session_load_error:
            st.error(session_load_error)
        else:
            set_active_dataset(
                bundle["raw_df"], bundle["working_df"], "restored_session.csv",
                cleaning_log=bundle["cleaning_log"], chat_history=bundle["chat_history"],
            )
            st.toast("Session restored.")
            st.rerun()

    ui.render_footer()
    st.stop()

# ---------------------------------------------------------------------------
# Tabbed app — reached once a dataset is active.
# ---------------------------------------------------------------------------
ui.render_onboarding()

df = st.session_state.working_df
column_types = st.session_state.column_types

has_datetime_col = "datetime" in column_types.values()

_tab_names = ["Overview", "Clean", "Combine", "Visualize", "SQL Lab", "AI Analyst", "Auto Analyst", "Stats Lab"]
if has_datetime_col:
    _tab_names.append("Forecasting")
_tab_names.append("Clustering")

_tabs = dict(zip(_tab_names, st.tabs(_tab_names)))
tab_overview = _tabs["Overview"]
tab_clean = _tabs["Clean"]
tab_combine = _tabs["Combine"]
tab_visualize = _tabs["Visualize"]
tab_sql = _tabs["SQL Lab"]
tab_ai = _tabs["AI Analyst"]
tab_auto = _tabs["Auto Analyst"]
tab_stats = _tabs["Stats Lab"]
tab_forecast = _tabs.get("Forecasting")  # None when the dataset has no datetime column
tab_cluster = _tabs["Clustering"]

# --------------------------------------------------------------------------
# Overview tab — data quality report, column health, drill-down, anomalies
# --------------------------------------------------------------------------
with tab_overview:
    ui.render_help_expander(
        "A full data-quality audit: missing values, outliers, column types, and summary "
        "stats — plus per-column health, a drill-down, and anomaly detection below."
    )

    quality = data_engine.get_data_quality_report(df, column_types)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Rows", f"{quality['n_rows']:,}")
    m2.metric("Columns", quality["n_cols"])
    m3.metric("Missing", f"{quality['total_missing_pct']}%")
    m4.metric("Duplicates", quality["duplicate_rows"])
    m5.metric("Memory", quality["memory_usage"])

    if quality["all_null_columns"]:
        st.warning(
            f"Fully empty columns detected: {', '.join(quality['all_null_columns'])}. "
            "Consider dropping them in the sidebar's Cleaning Controls."
        )

    if pii_detector.has_findings(st.session_state.pii_findings):
        st.warning(f"**Privacy notice:** {pii_detector.describe_findings(st.session_state.pii_findings)}")
        with st.expander("PII Detector — details & masking", expanded=False):
            for pii_type, label in [("email", "Emails"), ("phone", "Phone numbers"), ("name", "Likely names")]:
                entries = st.session_state.pii_findings.get(pii_type, [])
                if not entries:
                    continue
                st.markdown(f"**{label}**")
                for entry in entries:
                    pii_col = entry["column"]
                    pcol1, pcol2, pcol3 = st.columns([2, 2, 1])
                    pcol1.write(f"`{pii_col}`")
                    pcol2.caption(f"{entry['match_pct']}% match — e.g. {entry['sample']}")
                    with pcol3:
                        if st.button("Mask", key=f"mask_{pii_type}_{pii_col}", use_container_width=True):
                            push_undo_snapshot()
                            masked_df = pii_detector.mask_column(df, pii_col, pii_type)
                            st.session_state.working_df = masked_df
                            log_step(
                                f"Masked {label.lower()} in '{pii_col}'",
                                f"# Masked {pii_type} values in '{pii_col}' for privacy.",
                            )
                            st.session_state.pii_findings = pii_detector.scan_dataframe(
                                masked_df, st.session_state.column_types
                            )
                            st.toast(f"Masked '{pii_col}'.")
                            st.rerun()

    col_left, col_right = st.columns(2)
    with col_left:
        st.markdown("**Missing Values by Column**")
        missing_df = pd.DataFrame(
            {"Column": quality["missing_by_column"].keys(), "Missing %": quality["missing_by_column"].values()}
        ).sort_values("Missing %", ascending=False)
        st.dataframe(missing_df, use_container_width=True, hide_index=True)

    with col_right:
        st.markdown("**Outliers (IQR method)**")
        if quality["outliers"]:
            outlier_df = pd.DataFrame(
                [{"Column": c, "Outliers": v["count"], "Outlier %": v["pct"]} for c, v in quality["outliers"].items()]
            ).sort_values("Outliers", ascending=False)
            st.dataframe(outlier_df, use_container_width=True, hide_index=True)
        else:
            st.info("No numeric columns to check for outliers.")

    st.markdown("**Detected Column Types**")
    types_df = pd.DataFrame({"Column": column_types.keys(), "Detected Type": column_types.values()})
    st.dataframe(types_df, use_container_width=True, hide_index=True)

    st.markdown("**Summary Statistics**")
    st.dataframe(visualization.style_describe_table(visualization.get_overview_stats(df)), use_container_width=True)

    st.markdown("**Data Preview**")
    st.dataframe(df.head(20), use_container_width=True)

    st.divider()
    with st.expander("Column Health", expanded=False):
        profiles = profiling.profile_all_columns(df, column_types, quality)
        health_df = pd.DataFrame(
            [
                {
                    "Column": p["column"],
                    "Type": p["type"],
                    "Health": p["health"].upper(),
                    "Notes": "; ".join(p["issues"] + p["warnings"]) or "—",
                }
                for p in profiles
            ]
        )
        st.dataframe(health_df, use_container_width=True, hide_index=True)

    with st.expander("Column Drill-Down", expanded=False):
        drill_col = st.selectbox("Choose a column", df.columns.tolist(), key="drilldown_col")
        prof = profiling.profile_column(df, drill_col, column_types, quality)

        st.markdown(f"**Health: {prof['health'].upper()}**")
        for msg in prof["issues"]:
            st.error(msg)
        for msg in prof["warnings"]:
            st.warning(msg)

        dd1, dd2 = st.columns(2)
        with dd1:
            st.metric("Missing %", f"{prof['missing_pct']}%")
            if prof["skew_label"]:
                st.write(f"**Skewness:** {prof['skew_label']}")
            if prof["kurt_label"]:
                st.write(f"**Kurtosis:** {prof['kurt_label']}")
        with dd2:
            st.write("**Top 10 values**")
            st.dataframe(df[drill_col].value_counts().head(10).rename("count"), use_container_width=True)

        drill_type = column_types.get(drill_col)
        if drill_type == "numeric":
            hist, box = visualization.plot_numeric(df, drill_col)
            st.plotly_chart(hist, use_container_width=True)
            st.plotly_chart(box, use_container_width=True)
        elif drill_type == "categorical":
            cat_fig = visualization.plot_categorical(df, drill_col)
            if cat_fig is not None:
                st.plotly_chart(cat_fig, use_container_width=True)
        else:
            st.info("No dedicated chart for this column type — see the Top 10 values above.")

        st.write("**Descriptive stats**")
        st.dataframe(df[[drill_col]].describe(include="all").transpose(), use_container_width=True)

    with st.expander("Anomaly Detection", expanded=False):
        if not anomaly.is_available():
            st.warning("scikit-learn isn't installed. Run `pip install -r requirements.txt` and restart the app.")
        else:
            if st.button("Find Anomalies", key="find_anomalies_btn"):
                with st.spinner("Scanning for anomalies..."):
                    flagged, anomaly_err = anomaly.find_anomalies(df, column_types)
                st.session_state.anomaly_result_df = flagged
                st.session_state.anomaly_error = anomaly_err

            if st.session_state.anomaly_error:
                st.error(st.session_state.anomaly_error)
            elif st.session_state.anomaly_result_df is not None:
                flagged = st.session_state.anomaly_result_df
                if flagged.empty:
                    st.info("No anomalies detected.")
                else:
                    st.write(f"**{len(flagged)} anomalous row(s) flagged:**")
                    st.dataframe(flagged, use_container_width=True)
                    if st.button("Exclude flagged rows from active dataset", key="exclude_anomalies_btn"):
                        push_undo_snapshot()
                        new_df = df.drop(index=flagged.index)
                        st.session_state.working_df = new_df
                        st.session_state.column_types = data_engine.detect_column_types(new_df)
                        log_step(
                            f"Excluded {len(flagged)} anomalous row(s) (IsolationForest)",
                            cleaning.anomaly_exclude_code(len(flagged)),
                        )
                        st.session_state.anomaly_result_df = None
                        st.toast(f"Excluded {len(flagged)} anomalous row(s).")
                        st.rerun()

# --------------------------------------------------------------------------
# Clean tab — before/after comparison + cleaned dataset download
# (the actual cleaning controls live in the sidebar, per the spec's layout)
# --------------------------------------------------------------------------
with tab_clean:
    ui.render_help_expander(
        "Review exactly what changed since upload. Cleaning actions themselves live in the "
        "sidebar's Cleaning Controls, Datetime Features, and Type Coercion tools."
    )

    st.subheader("Before vs After")
    diff = cleaning.compare_before_after(st.session_state.raw_df, df)

    d1, d2, d3 = st.columns(3)
    d1.metric("Rows", diff["rows_after"], delta=diff["rows_after"] - diff["rows_before"])
    d2.metric("Columns", diff["cols_after"], delta=diff["cols_after"] - diff["cols_before"])
    d3.metric("Missing Cells", diff["nulls_after"], delta=diff["nulls_after"] - diff["nulls_before"])

    if diff["dtype_changes"]:
        st.markdown("**Dtype changes**")
        for col, (old, new) in diff["dtype_changes"].items():
            st.write(f"- `{col}`: {old} → {new}")

    st.divider()
    st.subheader("Cleaning Log")
    if st.session_state.cleaning_log:
        for step in st.session_state.cleaning_log:
            st.write(f"- {step['description']}")
    else:
        st.info("No cleaning steps applied yet — use the sidebar's Cleaning Controls.")

    st.divider()
    st.subheader("Original vs Cleaned Preview")
    prev_left, prev_right = st.columns(2)
    with prev_left:
        st.caption("Original")
        st.dataframe(st.session_state.raw_df.head(10), use_container_width=True)
    with prev_right:
        st.caption("Cleaned")
        st.dataframe(df.head(10), use_container_width=True)

    st.divider()
    st.download_button(
        "Download Cleaned Dataset (CSV)",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="prism_cleaned_data.csv",
        mime="text/csv",
        use_container_width=True,
    )

# --------------------------------------------------------------------------
# Combine tab — join a second uploaded file onto the active dataset. Setting
# the result as active rewires every other tab (Clean, Visualize, SQL Lab,
# AI Analyst) to operate on the joined data, since they all just read
# st.session_state.working_df.
# --------------------------------------------------------------------------
with tab_combine:
    ui.render_help_expander(
        "Upload a second file and join it onto your active dataset by a detected or "
        "manually chosen key."
    )

    st.subheader("Combine with Another File")
    combine_mode = st.radio(
        "Mode", ["Join datasets", "Compare for drift"], key="combine_mode", horizontal=True,
    )
    st.caption(
        "Upload a second dataset to join it onto your active data, or compare it against your "
        "active data for dataset drift (e.g. this month vs last month)."
    )

    second_file = st.file_uploader(
        "Upload second CSV or Excel", type=["csv", "xlsx", "xls"], key="second_file_uploader"
    )

    if second_file is not None and second_file.name != st.session_state.second_file_name:
        second_sheet_choice, second_sheet_ready = resolve_sheet_choice(second_file, "second")
        if second_sheet_ready:
            with st.spinner("Reading second file..."):
                new_second_df, second_error, second_warnings = data_engine.load_data(
                    second_file, sheet_name=second_sheet_choice
                )
            if second_error:
                st.error(second_error)
            else:
                st.session_state.second_df = new_second_df
                st.session_state.second_file_name = second_file.name
                st.session_state.combine_preview_df = None
                st.session_state.combine_stats = None
                st.session_state.drift_result = None
                for w in second_warnings:
                    st.warning(w)
                st.success(f"Loaded second file: {new_second_df.shape[0]:,} rows x {new_second_df.shape[1]} columns")

    if st.session_state.second_df is None:
        st.info("Upload a second file above to combine or compare it with your active dataset.")
    else:
        second_df = st.session_state.second_df

        prev_left, prev_right = st.columns(2)
        with prev_left:
            st.caption(f"Active dataset — {df.shape[0]:,} rows × {df.shape[1]} columns")
            st.dataframe(df.head(5), use_container_width=True)
        with prev_right:
            st.caption(f"{st.session_state.second_file_name} — {second_df.shape[0]:,} rows × {second_df.shape[1]} columns")
            st.dataframe(second_df.head(5), use_container_width=True)

        if combine_mode == "Join datasets":
            candidates = join_engine.detect_candidate_join_keys(df, second_df)
            if candidates:
                st.markdown("**Candidate Join Keys** (matching column names, ranked by value overlap)")
                candidates_df = pd.DataFrame(candidates).rename(
                    columns={
                        "column": "Column",
                        "overlap_pct": "Overlap %",
                        "left_unique": "Unique (active)",
                        "right_unique": "Unique (second)",
                    }
                )
                st.dataframe(candidates_df, use_container_width=True, hide_index=True)
                default_left_key = default_right_key = candidates[0]["column"]
            else:
                st.warning(
                    "No columns with matching names were found between the two files. "
                    "Pick a join key manually below."
                )
                default_left_key, default_right_key = df.columns[0], second_df.columns[0]

            jc1, jc2, jc3 = st.columns(3)
            with jc1:
                left_key = st.selectbox(
                    "Active dataset key", df.columns.tolist(),
                    index=df.columns.get_loc(default_left_key) if default_left_key in df.columns else 0,
                )
            with jc2:
                right_key = st.selectbox(
                    "Second file key", second_df.columns.tolist(),
                    index=second_df.columns.get_loc(default_right_key) if default_right_key in second_df.columns else 0,
                )
            with jc3:
                join_type = st.selectbox("Join type", ["inner", "left", "right", "outer"])
            st.caption(join_engine.JOIN_TYPE_DESCRIPTIONS[join_type])

            if st.button("Preview Join", use_container_width=True):
                try:
                    joined_df, join_stats = join_engine.join_dataframes(df, second_df, left_key, right_key, join_type)
                    st.session_state.combine_preview_df = joined_df
                    st.session_state.combine_stats = join_stats
                except Exception as e:
                    st.session_state.combine_preview_df = None
                    st.session_state.combine_stats = None
                    st.error(f"Join failed: {e}")

            if st.session_state.combine_preview_df is not None:
                stats = st.session_state.combine_stats
                s1, s2, s3, s4 = st.columns(4)
                s1.metric("Rows Before", f"{stats['rows_before']:,}")
                s2.metric("Rows After", f"{stats['rows_after']:,}", delta=stats["rows_after"] - stats["rows_before"])
                s3.metric("Columns Gained", stats["columns_gained"])
                s4.metric("Key Match Rate", f"{stats['match_pct']}%")

                st.markdown("**Joined Preview**")
                st.dataframe(st.session_state.combine_preview_df.head(20), use_container_width=True)

                if st.button("Use as Active Dataset", type="primary", use_container_width=True):
                    new_active_df = st.session_state.combine_preview_df
                    join_description = (
                        f"Combined with '{st.session_state.second_file_name}' via a {join_type} join on "
                        f"'{left_key}' = '{right_key}'"
                    )
                    set_active_dataset(
                        new_active_df.copy(),
                        new_active_df.copy(),
                        f"combined:{st.session_state.second_file_name}",
                        cleaning_log=[
                            {
                                "description": join_description,
                                "code": cleaning.join_code(
                                    st.session_state.second_file_name, left_key, right_key, join_type
                                ),
                            }
                        ],
                    )
                    st.toast("Joined dataset is now active — every tab will use it.")
                    st.rerun()

        else:
            st.caption(
                f"Comparing active dataset ({df.shape[0]:,} rows) as the baseline against "
                f"'{st.session_state.second_file_name}' ({second_df.shape[0]:,} rows) as the comparison."
            )

            if st.button("Run Drift Comparison", type="primary", use_container_width=True):
                st.session_state.drift_result = drift.compare_datasets(df, second_df, column_types)

            drift_result = st.session_state.drift_result
            if drift_result is not None:
                st.metric("Overall Drift Score", f"{drift_result['overall_drift_score']}/100")

                if drift_result["columns_only_in_a"]:
                    st.warning(f"Columns only in the active dataset: {', '.join(drift_result['columns_only_in_a'])}")
                if drift_result["columns_only_in_b"]:
                    st.warning(
                        f"Columns only in '{st.session_state.second_file_name}': "
                        f"{', '.join(drift_result['columns_only_in_b'])}"
                    )

                if not drift_result["column_reports"]:
                    st.info("No shared numeric or categorical columns to compare.")
                else:
                    st.markdown("**What changed the most**")
                    summary_df = pd.DataFrame(
                        [
                            {
                                "Column": r["column"],
                                "Type": r["type"],
                                "Drift Score": r["drift_score"],
                                "Summary": drift.describe_drift(r),
                            }
                            for r in drift_result["column_reports"]
                        ]
                    )
                    st.dataframe(summary_df, use_container_width=True, hide_index=True)

                    st.markdown("**Column-by-column detail**")
                    for r in drift_result["column_reports"]:
                        with st.expander(f"{r['column']} — drift score {r['drift_score']}", expanded=False):
                            st.plotly_chart(
                                drift.build_overlap_chart(r), use_container_width=True, key=f"drift_chart_{r['column']}"
                            )
                            if r["type"] == "categorical":
                                if r["new_categories"]:
                                    st.write(f"**New categories in B:** {', '.join(map(str, r['new_categories']))}")
                                if r["missing_categories"]:
                                    st.write(
                                        f"**Missing categories in B:** {', '.join(map(str, r['missing_categories']))}"
                                    )

# --------------------------------------------------------------------------
# Visualize tab — smart auto-charts, correlation heatmap, HTML export
# --------------------------------------------------------------------------
with tab_visualize:
    ui.render_help_expander(
        "Auto-picked charts per column type, a correlation heatmap, and a manual chart "
        "builder for full control."
    )

    st.subheader("Auto-Generated Charts")

    id_like_cols = profiling.get_id_like_columns(df)
    chart_column_types = {c: t for c, t in column_types.items() if c not in id_like_cols}
    if id_like_cols:
        st.caption(f"Excluded probable ID column(s) from auto-charts: {', '.join(id_like_cols)}")

    with st.spinner("Building charts..."):
        charts, top_corr = visualization.auto_generate_charts(df, chart_column_types)

    if top_corr:
        st.markdown("**Top Correlations**")
        for c1, c2, val in top_corr:
            st.info(f"**{c1}** ↔ **{c2}** — {visualization.describe_correlation(val)}")

    if not charts:
        st.info("Not enough data variety to auto-generate charts yet.")
    else:
        chart_items = list(charts.items())
        for i in range(0, len(chart_items), 2):
            cols = st.columns(2)
            for offset, col in enumerate(cols):
                idx = i + offset
                if idx < len(chart_items):
                    title, fig = chart_items[idx]
                    with col:
                        st.plotly_chart(fig, use_container_width=True, key=f"auto_chart_{idx}_{title}")

    st.divider()
    st.subheader("Manual Chart Builder")
    st.caption("Auto mode above not showing what you need? Pick the axes and chart type yourself.")

    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        manual_x = st.selectbox("X-axis", df.columns.tolist(), key="manual_x")
    with mc2:
        manual_chart_type = st.selectbox("Chart type", visualization.MANUAL_CHART_TYPES, key="manual_chart_type")
    with mc3:
        y_required = manual_chart_type in visualization.MANUAL_CHART_TYPES_REQUIRING_Y
        y_options = ["(none)"] + [c for c in df.columns if c != manual_x]
        y_label = st.selectbox(f"Y-axis{'' if y_required else ' (optional)'}", y_options, key="manual_y")
        manual_y = None if y_label == "(none)" else y_label

    if st.button("Build Chart", use_container_width=True):
        try:
            st.session_state.manual_chart_fig = visualization.build_manual_chart(
                df, manual_chart_type, manual_x, manual_y
            )
            st.session_state.manual_chart_error = None
        except Exception as e:
            st.session_state.manual_chart_fig = None
            st.session_state.manual_chart_error = str(e)

    if st.session_state.manual_chart_error:
        st.error(st.session_state.manual_chart_error)
    elif st.session_state.manual_chart_fig is not None:
        st.plotly_chart(st.session_state.manual_chart_fig, use_container_width=True)

    st.divider()
    st.subheader("Auto-Dashboard")
    st.caption("One click: Gemini designs a set of KPI cards and 4-6 charts for this dataset.")

    if st.button("Build My Dashboard", use_container_width=True):
        dashboard_model = ai_analyst.get_model()
        with st.spinner("Designing your dashboard..."):
            st.session_state.dashboard_spec = dashboard_builder.generate_dashboard_spec(
                dashboard_model, df, column_types
            )

    dashboard_spec = st.session_state.dashboard_spec
    if dashboard_spec is not None:
        if dashboard_spec["kpis"]:
            kpi_cols = st.columns(len(dashboard_spec["kpis"]))
            for kpi_col, kpi in zip(kpi_cols, dashboard_spec["kpis"]):
                kpi_value = dashboard_builder.compute_kpi(df, kpi)
                display_value = f"{kpi_value:,.2f}" if isinstance(kpi_value, float) else kpi_value
                kpi_col.metric(kpi.get("label", kpi["column"]), display_value if display_value is not None else "—")

        if not dashboard_spec["charts"]:
            st.info("No charts could be built for this dataset.")
        else:
            chart_entries = list(enumerate(dashboard_spec["charts"]))
            for row_start in range(0, len(chart_entries), 2):
                row_entries = chart_entries[row_start : row_start + 2]
                row_cols = st.columns(len(row_entries))
                for row_col, (chart_idx, chart_spec) in zip(row_cols, row_entries):
                    with row_col:
                        dash_fig = dashboard_builder.build_dashboard_chart(df, chart_spec)
                        if dash_fig is None:
                            st.warning(f"Couldn't build a chart for '{chart_spec.get('x')}'.")
                        else:
                            st.plotly_chart(dash_fig, use_container_width=True, key=f"dash_chart_{chart_idx}")
                            if chart_spec.get("reason"):
                                st.caption(chart_spec["reason"])

                        remove_col, swap_col = st.columns(2)
                        with remove_col:
                            if st.button("Remove", key=f"dash_remove_{chart_idx}", use_container_width=True):
                                dashboard_spec["charts"].pop(chart_idx)
                                st.session_state.dashboard_spec = dashboard_spec
                                st.rerun()
                        with swap_col:
                            if st.button("Swap", key=f"dash_swap_{chart_idx}", use_container_width=True):
                                dashboard_spec["charts"][chart_idx] = dashboard_builder.swap_chart_type(chart_spec)
                                st.session_state.dashboard_spec = dashboard_spec
                                st.rerun()

    st.divider()
    st.subheader("Export Report")
    st.caption("Generates a standalone HTML file with the data quality summary, all charts, and key stats.")

    quality_for_export = data_engine.get_data_quality_report(df, column_types)
    stats_df = visualization.get_overview_stats(df)
    html_report = report.generate_html_report(
        df, quality_for_export, stats_df, charts, [step["description"] for step in st.session_state.cleaning_log]
    )
    st.download_button(
        "Download Full HTML Report",
        data=html_report.encode("utf-8"),
        file_name="prism_eda_report.html",
        mime="text/html",
        use_container_width=True,
    )

    st.divider()
    st.subheader("Auto-Report Writer")
    st.caption(
        "One click: an executive-style write-up — summary, data quality, key findings with "
        "embedded charts, and recommendations — exportable as PDF or HTML."
    )

    if st.button("Generate Report", use_container_width=True):
        report_model = ai_analyst.get_model()
        with st.spinner("Writing your report..."):
            st.session_state.auto_report_content = report_writer.build_report_content(
                report_model, df, quality_for_export, column_types, charts, top_corr
            )

    report_content = st.session_state.auto_report_content
    if report_content is not None:
        st.markdown(f"**Executive Summary**  \n{report_content['executive_summary']}")
        if report_content["findings_error"]:
            st.warning(report_content["findings_error"])

        report_pdf_bytes = report_writer.generate_pdf_report(report_content, st.session_state.last_file_name or "dataset")
        report_html_text = report_writer.generate_html_report(report_content, st.session_state.last_file_name or "dataset")

        rc1, rc2 = st.columns(2)
        with rc1:
            st.download_button(
                "Download Report (PDF)",
                data=report_pdf_bytes,
                file_name="prism_analysis_report.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        with rc2:
            st.download_button(
                "Download Report (HTML)",
                data=report_html_text.encode("utf-8"),
                file_name="prism_analysis_report.html",
                mime="text/html",
                use_container_width=True,
            )

# --------------------------------------------------------------------------
# SQL Lab tab — run raw SQL against the active dataset via DuckDB (registered
# as table "data"), with clickable example queries and an optional
# AI-generated plain-English explanation of whatever query is in the editor.
# --------------------------------------------------------------------------
with tab_sql:
    ui.render_help_expander(
        "Run raw SQL against your active dataset via DuckDB — registered as a table named `data`."
    )

    st.subheader("SQL Lab")

    if sql_lab.duckdb is None:
        st.warning("The `duckdb` package isn't installed. Run `pip install -r requirements.txt` and restart the app.")
    else:
        st.caption('Your active dataset is registered as a table named `data`. Any DuckDB SQL works.')

        examples = sql_lab.build_example_queries(df, column_types)
        st.markdown("**Example Queries**")
        example_cols = st.columns(len(examples))
        for ex_col, (label, example_sql) in zip(example_cols, examples.items()):
            with ex_col:
                if st.button(label, key=f"sql_example_{label}", use_container_width=True):
                    st.session_state.sql_editor = example_sql

        st.text_area(
            "SQL query", key="sql_editor", height=140,
            placeholder="SELECT * FROM data LIMIT 10;",
        )

        run_col, explain_col = st.columns(2)
        with run_col:
            run_clicked = st.button("Run Query", type="primary", use_container_width=True)
        with explain_col:
            explain_clicked = st.button("Explain This Query", use_container_width=True)

        if run_clicked:
            query_text = st.session_state.sql_editor.strip()
            if not query_text:
                st.warning("Write a query first — the editor is empty.")
            else:
                sql_result, sql_error, sql_elapsed = sql_lab.run_query(df, query_text)
                st.session_state.sql_result_df = sql_result
                st.session_state.sql_error = sql_error
                st.session_state.sql_exec_time = sql_elapsed

        if st.session_state.sql_error:
            st.error(st.session_state.sql_error)
        elif st.session_state.sql_result_df is not None:
            st.caption(
                f"{len(st.session_state.sql_result_df):,} rows · "
                f"{st.session_state.sql_exec_time * 1000:.1f} ms"
            )
            st.dataframe(st.session_state.sql_result_df, use_container_width=True)

        if explain_clicked:
            query_text = st.session_state.sql_editor.strip()
            if not query_text:
                st.warning("Write a query first — the editor is empty.")
            else:
                sql_gemini_model = ai_analyst.get_model()
                if sql_gemini_model is None:
                    st.warning(ai_analyst.GEMINI_SETUP_HELP)
                else:
                    with st.spinner("Explaining query..."):
                        explanation, explain_error = ai_analyst.explain_sql(sql_gemini_model, query_text)
                    st.session_state.sql_explanation = explanation
                    st.session_state.sql_explanation_error = explain_error

        if st.session_state.sql_explanation_error:
            st.error(st.session_state.sql_explanation_error)
        elif st.session_state.sql_explanation:
            st.info(st.session_state.sql_explanation)

# --------------------------------------------------------------------------
# AI Analyst tab — key insights + natural-language chat over the dataframe
# Backed by Google Gemini (gemini-2.5-flash). Key comes from a .env file
# (GEMINI_API_KEY) via python-dotenv — see README for setup.
# --------------------------------------------------------------------------
with tab_ai:
    ui.render_help_expander(
        "Ask questions about your data in plain English — by typing or by voice — and get "
        "pandas-powered answers."
    )

    st.subheader("AI Analyst")

    gemini_model = ai_analyst.get_model()

    if gemini_model is None:
        st.warning(ai_analyst.GEMINI_SETUP_HELP)
    else:
        if st.button("Generate Key Insights"):
            with st.spinner("Analyzing your data..."):
                quality_for_ai = data_engine.get_data_quality_report(df, column_types)
                _, top_corr_for_ai = visualization.plot_correlation_heatmap(df)
                insights, insight_error = ai_analyst.generate_key_insights(
                    gemini_model, df, quality_for_ai, column_types, top_corr_for_ai
                )
            st.session_state.key_insights = insights
            st.session_state.key_insights_error = insight_error

        if st.session_state.key_insights_error:
            st.error(st.session_state.key_insights_error)
        elif st.session_state.key_insights:
            cards_html = "".join(
                f'<div class="insight-card"><div class="insight-number">FINDING {i + 1:02d}</div>'
                f'<div class="insight-text">{finding}</div></div>'
                for i, finding in enumerate(st.session_state.key_insights)
            )
            st.markdown(cards_html, unsafe_allow_html=True)

        st.divider()
        st.markdown("**Ask a question about your data**")
        st.caption(
            "Every question sends Gemini the column schema, a 5-row sample, and summary "
            "statistics — never the full dataset."
        )

        voice_col, _ = st.columns([1, 3])
        with voice_col:
            if voice_input.is_available():
                voice_text = voice_input.record_question()
                if voice_text and voice_text != st.session_state.last_voice_text:
                    st.session_state.last_voice_text = voice_text
                    st.session_state.pending_voice_question = voice_text
            else:
                st.caption(
                    "Voice input unavailable — install `streamlit-mic-recorder` to enable it, "
                    "or type your question below."
                )

        typed_question = st.chat_input("e.g. What's the average value of column X by category Y?")

        final_question = None
        if st.session_state.pending_voice_question:
            final_question = st.session_state.pending_voice_question
            st.session_state.pending_voice_question = None
        if typed_question:
            final_question = typed_question

        if final_question:
            st.session_state.chat_history.append({"role": "user", "content": final_question})
            with st.spinner("Thinking..."):
                outcome = ai_analyst.ask_and_execute(
                    gemini_model, df, column_types, final_question, st.session_state.chat_history[:-1]
                )
                chart_fig = None
                if (
                    not outcome["ask_error"]
                    and not outcome["error"]
                    and ai_analyst.question_implies_chart(final_question)
                ):
                    chart_fig = ai_analyst.build_chart_from_result(outcome["result"], final_question)
                st.session_state.chat_history.append(
                    {
                        "role": "assistant",
                        "question": final_question,
                        "code": outcome["code"],
                        "result": outcome["result"],
                        "error": outcome["error"],
                        "ask_error": outcome["ask_error"],
                        "retried": outcome.get("retried", False),
                        "original_error": outcome.get("original_error"),
                        "chart_fig": chart_fig,
                    }
                )

        for msg_idx, msg in enumerate(st.session_state.chat_history):
            if msg["role"] == "user":
                with st.chat_message("user"):
                    st.write(msg["content"])
            else:
                with st.chat_message("assistant"):
                    if msg.get("ask_error"):
                        st.error(msg["ask_error"])
                        continue

                    if msg.get("retried"):
                        st.caption(
                            f"First attempt failed ({msg.get('original_error')}) — "
                            "Gemini corrected it automatically."
                        )

                    if msg.get("code"):
                        with st.expander("View generated code"):
                            st.code(msg["code"], language="python")

                    if msg.get("error"):
                        st.error(msg["error"])
                        continue

                    result = msg.get("result")
                    if isinstance(result, (pd.DataFrame,)):
                        st.dataframe(result, use_container_width=True)
                    elif isinstance(result, pd.Series):
                        st.dataframe(result.to_frame(name="value"), use_container_width=True)
                    elif isinstance(result, (bool, np.bool_)):
                        st.write(result)
                    elif isinstance(result, (int, float, np.integer, np.floating)):
                        value = round(float(result), 4) if isinstance(result, (float, np.floating)) else result
                        st.metric(label=msg.get("question", "Result"), value=value)
                    elif result is not None:
                        st.write(result)

                    if msg.get("chart_fig") is not None:
                        st.plotly_chart(msg["chart_fig"], use_container_width=True, key=f"chat_chart_{msg_idx}")

# --------------------------------------------------------------------------
# Auto Analyst tab — agentic "Run Full Analysis": Gemini drafts an ordered
# plan, each step runs through the same safe-execution sandbox as the AI
# Analyst chat, then Gemini synthesizes the results into 5 headline findings.
# --------------------------------------------------------------------------
with tab_auto:
    ui.render_help_expander(
        "One click: Gemini plans an exploratory analysis (quality check, distributions, "
        "segments, correlations, time trends if applicable, conclusions), runs each step "
        "through the safe-execution sandbox, and summarizes the top findings."
    )

    st.subheader("Auto Analyst")

    auto_model = ai_analyst.get_model()

    if auto_model is None:
        st.warning(ai_analyst.GEMINI_SETUP_HELP)
    else:
        if st.button("Run Full Analysis", type="primary", use_container_width=True):
            plan = auto_analyst.generate_analysis_plan(auto_model, df, column_types)
            step_outcomes = []
            step_history: list[dict] = []

            with st.status("Running full analysis...", expanded=True) as run_status:
                for i, step in enumerate(plan, 1):
                    run_status.write(f"**Step {i}/{len(plan)} — {step['title']}**: running...")
                    outcome = auto_analyst.run_plan_step(auto_model, df, column_types, step, step_history)
                    step_outcomes.append(outcome)
                    step_history.append({"role": "user", "content": step["question"]})
                    step_history.append(
                        {"role": "assistant", "code": outcome.get("code"), "ask_error": outcome.get("ask_error")}
                    )
                    if outcome.get("ask_error") or outcome.get("error"):
                        run_status.write(
                            f"Step {i}/{len(plan)} — {step['title']}: failed "
                            f"({outcome.get('ask_error') or outcome.get('error')})"
                        )
                    else:
                        run_status.write(f"Step {i}/{len(plan)} — {step['title']}: done")
                run_status.update(label="Analysis complete", state="complete", expanded=False)

            with st.spinner("Synthesizing top findings..."):
                findings, findings_error = auto_analyst.synthesize_findings(auto_model, step_outcomes)

            st.session_state.auto_analyst_plan = plan
            st.session_state.auto_analyst_step_outcomes = step_outcomes
            st.session_state.auto_analyst_findings = findings
            st.session_state.auto_analyst_findings_error = findings_error

        if st.session_state.auto_analyst_step_outcomes:
            st.divider()
            st.markdown("### Analysis Complete")

            if st.session_state.auto_analyst_findings_error:
                st.error(st.session_state.auto_analyst_findings_error)
            elif st.session_state.auto_analyst_findings:
                cards_html = "".join(
                    f'<div class="insight-card"><div class="insight-number">FINDING {i + 1:02d}</div>'
                    f'<div class="insight-text">{finding}</div></div>'
                    for i, finding in enumerate(st.session_state.auto_analyst_findings)
                )
                st.markdown(cards_html, unsafe_allow_html=True)

            st.divider()
            st.markdown("**Step-by-step results**")
            for i, outcome in enumerate(st.session_state.auto_analyst_step_outcomes, 1):
                with st.expander(f"Step {i}: {outcome['title']}", expanded=False):
                    st.caption(outcome["question"])

                    if outcome.get("ask_error"):
                        st.error(outcome["ask_error"])
                        continue

                    if outcome.get("retried"):
                        st.caption(
                            f"First attempt failed ({outcome.get('original_error')}) — "
                            "Gemini corrected it automatically."
                        )

                    if outcome.get("code"):
                        st.code(outcome["code"], language="python")

                    if outcome.get("error"):
                        st.error(outcome["error"])
                        continue

                    result = outcome.get("result")
                    if isinstance(result, pd.DataFrame):
                        st.dataframe(result, use_container_width=True)
                    elif isinstance(result, pd.Series):
                        st.dataframe(result.to_frame(name="value"), use_container_width=True)
                    elif result is not None:
                        st.write(result)

# --------------------------------------------------------------------------
# Stats Lab tab — guided statistical testing. Pick two columns, get a
# suggested test (t-test / ANOVA / chi-square / Pearson correlation) with a
# one-line reason, run it via scipy.stats, and see a plain-English verdict
# plus normality/assumption-check warnings.
# --------------------------------------------------------------------------
with tab_stats:
    ui.render_help_expander(
        "Pick two columns and Stats Lab suggests the right statistical test, runs it via "
        "scipy.stats, and explains the result in plain English — with assumption-check warnings."
    )

    st.subheader("Stats Lab")

    testable_cols = [c for c, t in column_types.items() if t in ("numeric", "categorical")]
    if len(testable_cols) < 2:
        st.info("Need at least 2 numeric or categorical columns to run a statistical test.")
    else:
        sc1, sc2 = st.columns(2)
        with sc1:
            stats_col_a = st.selectbox("Column A", testable_cols, key="stats_col_a")
        with sc2:
            remaining_cols = [c for c in testable_cols if c != stats_col_a]
            stats_col_b = st.selectbox("Column B", remaining_cols, key="stats_col_b")

        suggestion = stats_lab.suggest_test(df, column_types, stats_col_a, stats_col_b)

        if suggestion.get("error"):
            st.warning(suggestion["error"])
        else:
            st.info(
                f"**Suggested test: {stats_lab.TEST_LABELS[suggestion['test']]}** — {suggestion['reason']}"
            )

            if st.button("Run Test", type="primary", use_container_width=True):
                st.session_state.stats_lab_result = stats_lab.run_test(df, suggestion)

            result = st.session_state.stats_lab_result
            if result is not None:
                if result.get("error"):
                    st.error(result["error"])
                else:
                    st.markdown(f"**{stats_lab.interpret_result(result)}**")

                    rc1, rc2, rc3 = st.columns(3)
                    rc1.metric("Test statistic", f"{result['statistic']:.4f}")
                    rc2.metric("p-value", f"{result['p_value']:.4g}")
                    rc3.metric(result["effect_size_name"], f"{result['effect_size']:.4f}")

                    if "contingency_table" in result:
                        st.markdown("**Contingency table**")
                        st.dataframe(result["contingency_table"], use_container_width=True)

                    if "means" in result:
                        st.markdown("**Group means**")
                        means_df = pd.DataFrame(
                            {
                                "Group": list(result["means"].keys()),
                                "Mean": list(result["means"].values()),
                                "n": [result["groups"][g] for g in result["means"]],
                            }
                        )
                        st.dataframe(means_df, use_container_width=True, hide_index=True)

                    for warning_msg in stats_lab.normality_warnings(result):
                        st.warning(warning_msg)

# --------------------------------------------------------------------------
# Forecasting tab — only rendered when the dataset has a datetime column.
# Pick a datetime + numeric column, get a statsmodels forecast (Exponential
# Smoothing, falling back to SARIMAX) with a confidence band, a horizon
# slider, a downloadable CSV, and a plain-English reliability caveat.
# --------------------------------------------------------------------------
if tab_forecast is not None:
    with tab_forecast:
        ui.render_help_expander(
            "Pick a datetime + numeric column to project a forecast with a confidence band, "
            "using statsmodels (Exponential Smoothing, falling back to SARIMAX)."
        )

        st.subheader("Forecasting")

        numeric_cols_for_forecast = [c for c, t in column_types.items() if t == "numeric"]
        if not numeric_cols_for_forecast:
            st.info("No numeric column detected — Forecasting needs one to project into the future.")
        else:
            datetime_cols_for_forecast = [c for c, t in column_types.items() if t == "datetime"]

            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                forecast_dt_col = st.selectbox("Datetime column", datetime_cols_for_forecast, key="forecast_dt_col")
            with fc2:
                forecast_num_col = st.selectbox("Numeric column", numeric_cols_for_forecast, key="forecast_num_col")
            with fc3:
                forecast_horizon = st.slider("Horizon (periods)", min_value=7, max_value=90, value=30, key="forecast_horizon")

            if st.button("Generate Forecast", type="primary", use_container_width=True):
                series, freq, prep_error = forecasting.prepare_series(df, forecast_dt_col, forecast_num_col)
                if prep_error:
                    st.session_state.forecast_result = None
                    st.session_state.forecast_error = prep_error
                else:
                    with st.spinner("Fitting forecast model..."):
                        forecast_outcome = forecasting.run_forecast(series, forecast_horizon, freq)
                    if forecast_outcome.get("error"):
                        st.session_state.forecast_result = None
                        st.session_state.forecast_error = forecast_outcome["error"]
                    else:
                        st.session_state.forecast_result = forecast_outcome
                        st.session_state.forecast_error = None

            if st.session_state.forecast_error:
                st.error(st.session_state.forecast_error)
            elif st.session_state.forecast_result is not None:
                forecast_outcome = st.session_state.forecast_result
                if forecast_outcome.get("warning"):
                    st.caption(forecast_outcome["warning"])
                st.caption(f"Model used: {forecast_outcome['model_used']}")

                forecast_fig = forecasting.build_forecast_chart(
                    forecast_outcome["history"], forecast_outcome["forecast"], f"{forecast_num_col} forecast"
                )
                st.plotly_chart(forecast_fig, use_container_width=True)

                st.info(
                    forecasting.forecast_caveat(
                        len(forecast_outcome["history"]), len(forecast_outcome["forecast"]), forecast_outcome["model_used"]
                    )
                )

                st.download_button(
                    "Download Forecast CSV",
                    data=forecast_outcome["forecast"].reset_index().to_csv(index=False).encode("utf-8"),
                    file_name="prism_forecast.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

# --------------------------------------------------------------------------
# Clustering tab — KMeans on standardized numeric columns with an
# elbow-method K suggestion, a 2D PCA scatter colored by cluster, and an
# optional Gemini pass to name/describe each segment in one line.
# --------------------------------------------------------------------------
with tab_cluster:
    ui.render_help_expander(
        "Pick numeric columns to segment your data with KMeans — an elbow-method suggestion "
        "picks K for you, and a 2D PCA scatter shows the resulting clusters."
    )

    st.subheader("Clustering & Segmentation")

    if len(df) < clustering.MIN_ROWS_FOR_CLUSTERING:
        st.warning(
            f"This dataset has only {len(df)} rows — clustering results below "
            f"{clustering.MIN_ROWS_FOR_CLUSTERING} rows can be unstable. Proceed with caution."
        )

    numeric_cols_for_cluster = [c for c, t in column_types.items() if t == "numeric"]
    if len(numeric_cols_for_cluster) < 2:
        st.info("Need at least 2 numeric columns to run clustering.")
    else:
        selected_cluster_cols = st.multiselect(
            "Numeric columns to cluster on",
            numeric_cols_for_cluster,
            default=numeric_cols_for_cluster[: min(5, len(numeric_cols_for_cluster))],
            key="cluster_cols",
        )

        if len(selected_cluster_cols) < 2:
            st.info("Pick at least 2 numeric columns.")
        else:
            clean_row_count = df[selected_cluster_cols].dropna().shape[0]
            if clean_row_count < 4:
                st.error(
                    f"Only {clean_row_count} complete rows across the selected columns — "
                    "need at least 4 to cluster."
                )
            else:
                suggested_k, inertias = clustering.suggest_k(df, selected_cluster_cols)
                max_k = max(2, min(clustering.MAX_K, clean_row_count - 1))

                if inertias:
                    with st.expander("Elbow method chart", expanded=False):
                        st.plotly_chart(clustering.build_elbow_chart(inertias), use_container_width=True)

                k_choice = st.slider(
                    "Number of clusters (K)", min_value=2, max_value=max_k,
                    value=min(suggested_k, max_k), key="cluster_k",
                )
                st.caption(f"Elbow-method suggestion: K={min(suggested_k, max_k)}")

                if st.button("Run Clustering", type="primary", use_container_width=True):
                    st.session_state.cluster_result = clustering.run_clustering(df, selected_cluster_cols, k_choice)
                    st.session_state.cluster_segment_names = []
                    st.session_state.cluster_segment_error = None

                cluster_result = st.session_state.cluster_result
                if cluster_result is not None:
                    if cluster_result.get("error"):
                        st.error(cluster_result["error"])
                    else:
                        st.plotly_chart(
                            clustering.build_scatter(
                                cluster_result["scatter_df"], cluster_result["pca_explained_variance"]
                            ),
                            use_container_width=True,
                        )

                        st.markdown("**Cluster stats** (mean of each column, per cluster)")
                        st.dataframe(cluster_result["cluster_stats"], use_container_width=True)

                        if st.button("Name Segments with AI", key="name_segments_btn"):
                            cluster_model = ai_analyst.get_model()
                            if cluster_model is None:
                                st.warning(ai_analyst.GEMINI_SETUP_HELP)
                            else:
                                with st.spinner("Naming segments..."):
                                    names, name_error = clustering.name_segments(
                                        cluster_model, cluster_result["cluster_stats"]
                                    )
                                st.session_state.cluster_segment_names = names
                                st.session_state.cluster_segment_error = name_error

                        if st.session_state.cluster_segment_error:
                            st.error(st.session_state.cluster_segment_error)
                        elif st.session_state.cluster_segment_names:
                            for segment_desc in st.session_state.cluster_segment_names:
                                st.info(segment_desc)

ui.render_footer()
