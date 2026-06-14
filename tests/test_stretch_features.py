import sys
import types
from unittest.mock import Mock, patch


dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda: None
sys.modules.setdefault("dotenv", dotenv_stub)

groq_stub = types.ModuleType("groq")
groq_stub.Groq = object
sys.modules.setdefault("groq", groq_stub)

import agent
import tools
from tools import check_trends, compare_price, suggest_outfit
from utils.data_loader import load_listings


LISTING = {
    "id": "lst_002",
    "title": "Y2K Baby Tee - Butterfly Print",
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


def fake_groq_client(content: str):
    response = types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                message=types.SimpleNamespace(content=content),
            )
        ]
    )
    create = Mock(return_value=response)
    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=create),
        )
    )
    return client, create


def test_compare_price_returns_assessment_with_dataset_comparables():
    listings = load_listings()
    item = next(listing for listing in listings if listing["id"] == "lst_002")

    result = compare_price(item, listings)

    assert result["assessment"] in {"good deal", "fair price", "priced high"}
    assert result["item_price"] == 18.0
    assert result["average_comparable_price"] is not None
    assert result["comparable_count"] > 0
    assert result["comparables"]
    assert "Comparable dataset listings average" in result["reasoning"]


def test_check_trends_returns_matching_trend_context_for_graphic_tee():
    result = check_trends("vintage graphic tee", size="M")

    trend_names = [trend["name"] for trend in result["matched_trends"]]
    assert "Graphic tee with baggy denim" in trend_names
    assert "chunky sneakers" in result["trend_tags"]
    assert "Graphic tee with baggy denim" in result["influence"]
    assert result["size"] == "M"


def test_retry_logic_removes_size_filter_and_continues_workflow(monkeypatch):
    search = Mock(side_effect=[[], [LISTING]])
    suggest = Mock(return_value="Wear it with baggy jeans and chunky sneakers.")
    create = Mock(return_value="Butterfly tee, big denim, easy thrifted fit.")

    monkeypatch.setattr(agent, "search_listings", search)
    monkeypatch.setattr(agent, "suggest_outfit", suggest)
    monkeypatch.setattr(agent, "create_fit_card", create)
    monkeypatch.setattr(agent, "update_style_profile", Mock(return_value={"preferences": []}))

    session = agent.run_agent("vintage graphic tee size XXS under $30", WARDROBE)

    assert search.call_args_list[0].args == ("vintage graphic tee", "XXS", 30.0)
    assert search.call_args_list[1].args == ("vintage graphic tee", None, 30.0)
    assert search.call_count == 2
    assert session["retry_attempts"][0]["adjustment"] == "removed size filter XXS"
    assert session["retry_attempts"][0]["result_count"] == 1
    assert "removed size filter XXS" in session["retry_message"]
    assert session["selected_item"] == LISTING
    suggest.assert_called_once()
    create.assert_called_once()
    assert session["error"] is None


def test_style_profile_memory_persists_across_sessions(monkeypatch, tmp_path):
    profile_path = tmp_path / "style_profile.json"
    search = Mock(return_value=[LISTING])
    suggest = Mock(return_value="Wear it with baggy jeans and chunky sneakers.")
    create = Mock(return_value="Butterfly tee, big denim, easy thrifted fit.")

    monkeypatch.setattr(agent, "STYLE_PROFILE_PATH", profile_path)
    monkeypatch.setattr(agent, "search_listings", search)
    monkeypatch.setattr(agent, "suggest_outfit", suggest)
    monkeypatch.setattr(agent, "create_fit_card", create)

    agent.run_agent(
        "vintage graphic tee under $30. I mostly wear grunge streetwear and chunky sneakers.",
        {"items": []},
    )
    second_session = agent.run_agent("vintage graphic tee under $30", {"items": []})

    preferences = second_session["style_profile"]["preferences"]
    assert profile_path.exists()
    assert "grunge" in preferences
    assert "streetwear" in preferences
    assert "chunky" in preferences

    second_wardrobe_context = suggest.call_args_list[1].args[1]
    assert second_wardrobe_context["_style_profile"] == second_session["style_profile"]
    assert "grunge" in second_wardrobe_context["_style_profile"]["preferences"]


def test_suggest_outfit_prompt_includes_style_memory_and_trend_context():
    client, create = fake_groq_client(
        "Style the tee with baggy denim, chunky sneakers, and a compact bag."
    )
    wardrobe_with_context = {
        **WARDROBE,
        "_style_profile": {"preferences": ["grunge", "streetwear"]},
        "_trend_info": check_trends("vintage graphic tee", size="M"),
    }

    with patch.object(tools, "_get_groq_client", return_value=client):
        result = suggest_outfit(LISTING, wardrobe_with_context)

    prompt = create.call_args.kwargs["messages"][1]["content"]
    assert "Style the tee" in result
    assert "Remembered style profile: grunge, streetwear" in prompt
    assert "Current trend context" in prompt
    assert "Graphic tee with baggy denim" in prompt
    assert "Let this influence the outfit suggestion visibly" in prompt
