import gettext
import json
from pathlib import Path
from unittest.mock import MagicMock


def test_retranslate_calls_all_setters():
    retranslatable = []

    def tr(setter, text):
        setter(text)
        retranslatable.append((setter, text))

    mock_label = MagicMock()
    mock_button = MagicMock()
    tr(mock_label.set_text, "Full Name")
    tr(mock_button.set_label, "Next")

    mock_label.set_text.assert_called_with("Full Name")
    mock_button.set_label.assert_called_with("Next")

    def retranslate(translate_fn):
        for setter, english in retranslatable:
            setter(translate_fn(english))

    retranslate(str.upper)
    mock_label.set_text.assert_called_with("FULL NAME")
    mock_button.set_label.assert_called_with("NEXT")


def test_gettext_fallback_returns_english():
    t = gettext.translation(
        "adwaita-lite-setup-wizard",
        localedir="/nonexistent",
        languages=["en"],
        fallback=True,
    )
    assert t.gettext("Next") == "Next"
    assert t.gettext("Full Name") == "Full Name"


def test_language_names_loadable():
    path = Path(__file__).resolve().parents[1] / "po" / "language-names.json"
    with open(path) as f:
        data = json.load(f)
    en_names = data["en"]
    assert en_names["de"] == "German"
    assert en_names["ja"] == "Japanese"
    assert en_names["en"] == "English"
