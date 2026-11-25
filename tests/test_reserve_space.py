"""A component keeps its place while its view loads, and a sequence view takes help."""

from unittest.mock import patch

from openms_insight.rendering import bridge


def test_css_class_matches_streamlit():
    assert bridge._css_class("viewer volcano/1") == "st-key-viewer-volcano-1"


def test_reserve_uses_last_frame_height():
    state = {bridge._FRAME_HEIGHTS_KEY: {"plot": 612}}
    with (
        patch.object(bridge.st, "session_state", state),
        patch.object(bridge.st, "html") as html,
    ):
        bridge._reserve_space("plot", 400)
    css = html.call_args[0][0]
    assert ".st-key-plot:has(iframe[height='0'])" in css
    assert "min-height: 612px" in css


def test_reserve_falls_back_to_given_height():
    with (
        patch.object(bridge.st, "session_state", {}),
        patch.object(bridge.st, "html") as html,
    ):
        bridge._reserve_space("plot", 400)
        assert "min-height: 400px" in html.call_args[0][0]
        html.reset_mock()
        bridge._reserve_space("other", None)
        html.assert_not_called()


def test_sequence_view_help(tmp_path):
    from openms_insight import SequenceView

    view = SequenceView(
        cache_id="s",
        cache_path=str(tmp_path),
        sequence_data=("PEPTIDE", 2),
        help="About it",
    )
    assert view._help == "About it"
    assert "help" not in view._config
