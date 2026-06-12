import inspect
import sys
import types
from unittest.mock import Mock

import pytest


dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda: None
sys.modules.setdefault("dotenv", dotenv_stub)

groq_stub = types.ModuleType("groq")
groq_stub.Groq = object
sys.modules.setdefault("groq", groq_stub)

import agent


AGENT_STILL_STUBBED = "Planning loop not yet implemented." in inspect.getsource(
    agent.run_agent
)

pytestmark = pytest.mark.xfail(
    AGENT_STILL_STUBBED,
    reason="run_agent planning loop is not implemented yet",
    strict=False,
)


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

WARDROBE = {
    "items": [
        {
            "id": "w_001",
            "name": "Baggy straight-leg jeans, dark wash",
            "category": "bottoms",
            "colors": ["dark blue", "indigo"],
            "style_tags": ["denim", "streetwear", "baggy"],
            "notes": "High-waisted, sits above the hip",
        }
    ]
}


def test_happy_path_passes_state_between_all_three_tools(monkeypatch):
    search = Mock(return_value=[LISTING])
    suggest = Mock(return_value="Wear it with baggy jeans and chunky sneakers.")
    create = Mock(return_value="Butterfly tee, big denim, easy thrifted fit.")

    monkeypatch.setattr(agent, "search_listings", search)
    monkeypatch.setattr(agent, "suggest_outfit", suggest)
    monkeypatch.setattr(agent, "create_fit_card", create)

    session = agent.run_agent("vintage graphic tee under $30 size M", WARDROBE)

    search.assert_called_once_with("vintage graphic tee", "M", 30.0)
    suggest.assert_called_once_with(LISTING, WARDROBE)
    create.assert_called_once_with(suggest.return_value, LISTING)
    assert session["error"] is None
    assert session["search_results"] == [LISTING]
    assert session["selected_item"] == LISTING
    assert session["outfit_suggestion"] == suggest.return_value
    assert session["fit_card"] == create.return_value


def test_no_search_results_stops_before_outfit_and_fit_card(monkeypatch):
    search = Mock(return_value=[])
    suggest = Mock()
    create = Mock()

    monkeypatch.setattr(agent, "search_listings", search)
    monkeypatch.setattr(agent, "suggest_outfit", suggest)
    monkeypatch.setattr(agent, "create_fit_card", create)

    session = agent.run_agent("designer ballgown size XXS under $5", WARDROBE)

    search.assert_called_once_with("designer ballgown", "XXS", 5.0)
    suggest.assert_not_called()
    create.assert_not_called()
    assert session["error"]
    assert session["search_results"] == []
    assert session["selected_item"] is None
    assert session["outfit_suggestion"] is None
    assert session["fit_card"] is None


def test_agent_takes_different_paths_for_success_and_no_results(monkeypatch):
    search = Mock(side_effect=[[LISTING], []])
    suggest = Mock(return_value="Wear it with baggy jeans and chunky sneakers.")
    create = Mock(return_value="Butterfly tee, big denim, easy thrifted fit.")

    monkeypatch.setattr(agent, "search_listings", search)
    monkeypatch.setattr(agent, "suggest_outfit", suggest)
    monkeypatch.setattr(agent, "create_fit_card", create)

    successful_session = agent.run_agent("vintage graphic tee under $30", WARDROBE)
    failed_session = agent.run_agent("designer ballgown size XXS under $5", WARDROBE)

    assert search.call_count == 2
    assert search.call_args_list[0].args == ("vintage graphic tee", None, 30.0)
    assert search.call_args_list[1].args == ("designer ballgown", "XXS", 5.0)
    assert suggest.call_count == 1
    assert create.call_count == 1
    assert successful_session["fit_card"] == create.return_value
    assert successful_session["error"] is None
    assert failed_session["fit_card"] is None
    assert failed_session["error"]


def test_planning_walkthrough_query_preserves_state_between_tool_calls(monkeypatch):
    outfit = (
        "Outfit 1: Wear the Y2K Baby Tee — Butterfly Print with baggy "
        "straight-leg jeans, chunky white sneakers, and a black crossbody bag."
    )
    fit_card = "Butterfly tee, big denim, and chunky sneakers for an easy thrifted fit."
    search = Mock(return_value=[LISTING])
    suggest = Mock(return_value=outfit)
    create = Mock(return_value=fit_card)

    monkeypatch.setattr(agent, "search_listings", search)
    monkeypatch.setattr(agent, "suggest_outfit", suggest)
    monkeypatch.setattr(agent, "create_fit_card", create)

    session = agent.run_agent(
        "I'm looking for a vintage graphic tee under $30, size M. "
        "I mostly wear baggy jeans and chunky sneakers. "
        "What's out there and how would I style it?",
        WARDROBE,
    )

    print("selected_item:", session["selected_item"])
    print("outfit_suggestion:", session["outfit_suggestion"])

    selected_item_passed_to_suggest = suggest.call_args.args[0]
    outfit_passed_to_create = create.call_args.args[0]
    selected_item_passed_to_create = create.call_args.args[1]

    assert session["selected_item"] is LISTING
    assert selected_item_passed_to_suggest is session["selected_item"]
    assert selected_item_passed_to_create is session["selected_item"]
    assert session["outfit_suggestion"] == outfit
    assert outfit_passed_to_create == session["outfit_suggestion"]
    assert session["fit_card"] == fit_card
    assert session["error"] is None
