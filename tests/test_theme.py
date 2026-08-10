"""Tests for modules/theme.py — first test coverage for this module.

Covers the mobile Atlas-panel reflow fix shipped in the 2026-08-10 Run 4
routine pass (`.st-key-atlas_side_panel` overlapping/hiding main content
at phone widths — flagged by three prior runs). It's a pure CSS string
emitted as part of the theme's `<style>` block, verified here by asserting
the rule text is present since there's no DOM to assert layout against in
a unit test (covered visually instead, see `.prism/runs/2026-08-10-run4/`).

The other bug this run investigated and fixed — Overview's "Missing
Values by Column" / "Outliers (IQR method)" tables staying dark-styled
under the Arctic (Light) theme — turned out not to be fixable via CSS at
all (see the investigation note above `apply_custom_theme` below); the
actual fix swapped those two tables from `st.dataframe` to `st.table` in
app.py, so it isn't theme-module behavior to test here.
"""

from modules import theme


def test_atlas_side_panel_mobile_reflow_rule_present():
    css = theme._CSS_TEMPLATE.template
    assert "@media (max-width: 768px)" in css
    assert ".st-key-atlas_side_panel" in css
    assert "max-height: 40vh" in css


def test_atlas_side_panel_mobile_reflow_docks_bottom_not_static():
    """Regression guard: an earlier attempt during this same run used
    `position: static`, which Playwright screenshots showed Streamlit's
    flex column layout collapsing to ~32px wide and rendering thousands
    of pixels off-screen. The shipped rule keeps `position: fixed` and
    docks to the bottom edge instead — this asserts that choice sticks.
    """
    css = theme._CSS_TEMPLATE.template
    media_block = css.split("@media (max-width: 768px)")[1]
    assert "position: static" not in media_block
    assert "bottom: 0;" in media_block


def test_stable_text_color_override_present():
    """st.table's cell text otherwise inherits Streamlit's own base
    stylesheet color (fixed dark, from config.toml) instead of the active
    theme — found while verifying this run's Overview table light-theme
    fix (see app.py's `st.table` swap). Confirms the override rule ships
    in every theme's stylesheet, not just a specific one, since the bug
    reproduces under any light theme.
    """
    css = theme._CSS_TEMPLATE.template
    assert 'div[data-testid="stTable"] table' in css
    assert 'div[data-testid="stTable"] td' in css
    assert "color: $text !important" in css


def test_all_themes_still_define_required_tokens():
    """Baseline sanity check — first test coverage for THEMES at all.
    Every theme must define every token the CSS template substitutes,
    or apply_custom_theme() raises a KeyError at runtime for that theme.
    """
    required = {
        "bg", "surface", "surface_hover", "border", "text", "text_muted",
        "accent", "accent_rgb", "accent2", "accent2_rgb", "accent3", "accent3_rgb",
        "success", "warning", "danger", "on_accent", "mode",
    }
    for key, tokens in theme.THEMES.items():
        missing = required - tokens.keys()
        assert not missing, f"theme '{key}' missing tokens: {missing}"
