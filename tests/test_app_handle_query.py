import sys
import types
from unittest.mock import Mock


dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda: None
sys.modules.setdefault("dotenv", dotenv_stub)

groq_stub = types.ModuleType("groq")
groq_stub.Groq = object
sys.modules.setdefault("groq", groq_stub)

gradio_stub = types.ModuleType("gradio")
sys.modules.setdefault("gradio", gradio_stub)

import app


LISTING = {
    "id": "lst_002",
    "title": "Y2K Baby Tee — Butterfly Print",
    "description": "Early 2000s baby tee with butterfly graphic.",
    "category": "tops",
    "style_tags": ["y2k", "vintage", "graphic tee"],
    "size": "S/M",
    "condition": "excellent",
    "price": 18.00,
    "colors": ["white", "pink", "purple"],
    "brand": None,
    "platform": "depop",
}


def test_empty_query_returns_first_panel_error_without_running_agent(monkeypatch):
    run_agent = Mock()
    monkeypatch.setattr(app, "run_agent", run_agent)

    result = app.handle_query("   ", "Example wardrobe")

    assert result == ("Please enter what you're looking for.", "", "")
    run_agent.assert_not_called()


def test_error_session_maps_error_to_first_panel(monkeypatch):
    example_wardrobe = {"items": [{"name": "Chunky white sneakers"}]}
    monkeypatch.setattr(app, "get_example_wardrobe", Mock(return_value=example_wardrobe))
    monkeypatch.setattr(
        app,
        "run_agent",
        Mock(return_value={"error": "No listings found."}),
    )

    result = app.handle_query("designer ballgown under $5", "Example wardrobe")

    assert result == ("No listings found.", "", "")
    app.run_agent.assert_called_once_with("designer ballgown under $5", example_wardrobe)


def test_empty_wardrobe_choice_uses_empty_wardrobe_loader(monkeypatch):
    empty_wardrobe = {"items": []}
    monkeypatch.setattr(app, "get_empty_wardrobe", Mock(return_value=empty_wardrobe))
    monkeypatch.setattr(
        app,
        "run_agent",
        Mock(return_value={"error": "No listings found."}),
    )

    app.handle_query("vintage graphic tee", "Empty wardrobe (new user)")

    app.get_empty_wardrobe.assert_called_once()
    app.run_agent.assert_called_once_with("vintage graphic tee", empty_wardrobe)


def test_success_session_formats_listing_outfit_and_fit_card(monkeypatch):
    example_wardrobe = {"items": [{"name": "Baggy jeans"}]}
    session = {
        "error": None,
        "selected_item": LISTING,
        "outfit_suggestion": "Wear it with baggy jeans and chunky sneakers.",
        "fit_card": "Butterfly tee, big denim, easy thrifted fit.",
    }
    monkeypatch.setattr(app, "get_example_wardrobe", Mock(return_value=example_wardrobe))
    monkeypatch.setattr(app, "run_agent", Mock(return_value=session))

    listing_text, outfit, fit_card = app.handle_query(
        " vintage graphic tee under $30 ",
        "Example wardrobe",
    )

    app.run_agent.assert_called_once_with("vintage graphic tee under $30", example_wardrobe)
    assert "Y2K Baby Tee — Butterfly Print" in listing_text
    assert "Price: $18.0" in listing_text
    assert "Size: S/M" in listing_text
    assert "Platform: depop" in listing_text
    assert "Brand: Unbranded" in listing_text
    assert "Style tags: y2k, vintage, graphic tee" in listing_text
    assert outfit == session["outfit_suggestion"]
    assert fit_card == session["fit_card"]


def test_missing_selected_item_returns_first_panel_error(monkeypatch):
    monkeypatch.setattr(app, "get_example_wardrobe", Mock(return_value={"items": []}))
    monkeypatch.setattr(
        app,
        "run_agent",
        Mock(
            return_value={
                "error": None,
                "selected_item": None,
                "outfit_suggestion": None,
                "fit_card": None,
            }
        ),
    )

    result = app.handle_query("vintage graphic tee", "Example wardrobe")

    assert result == ("No selected listing was returned by the agent.", "", "")
