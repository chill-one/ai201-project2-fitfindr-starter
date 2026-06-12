import sys
import types
import unittest
from unittest.mock import Mock, patch


dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda: None
sys.modules.setdefault("dotenv", dotenv_stub)

groq_stub = types.ModuleType("groq")
groq_stub.Groq = object
sys.modules.setdefault("groq", groq_stub)

import tools
from tools import GROQ_MODEL, suggest_outfit


VALID_ITEM = {
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
        },
        {
            "id": "w_007",
            "name": "Chunky white sneakers",
            "category": "shoes",
            "colors": ["white"],
            "style_tags": ["sneakers", "chunky", "streetwear"],
            "notes": None,
        },
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


class SuggestOutfitTest(unittest.TestCase):
    def test_uses_groq_model_and_includes_named_wardrobe_items(self):
        client, create = fake_groq_client(
            "Outfit 1: Pair the tee with Baggy straight-leg jeans, dark wash "
            "and Chunky white sneakers."
        )

        with patch.object(tools, "_get_groq_client", return_value=client):
            result = suggest_outfit(VALID_ITEM, WARDROBE)

        self.assertIn("Baggy straight-leg jeans", result)
        create.assert_called_once()
        request = create.call_args.kwargs
        self.assertEqual(request["model"], GROQ_MODEL)
        self.assertEqual(request["temperature"], 0.7)
        self.assertIn("Y2K Baby Tee", request["messages"][1]["content"])
        self.assertIn("Baggy straight-leg jeans, dark wash", request["messages"][1]["content"])

    def test_empty_wardrobe_calls_llm_for_general_styling(self):
        client, create = fake_groq_client(
            "No saved wardrobe yet, so try relaxed denim, white sneakers, and a small bag."
        )

        with patch.object(tools, "_get_groq_client", return_value=client):
            result = suggest_outfit(VALID_ITEM, {"items": []})

        self.assertIn("relaxed denim", result)
        create.assert_called_once()
        prompt = create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("no saved wardrobe items", prompt.lower())
        self.assertIn("general clothing categories", prompt.lower())

    def test_malformed_wardrobe_is_treated_like_empty_wardrobe(self):
        client, create = fake_groq_client("General outfit idea with jeans and sneakers.")

        with patch.object(tools, "_get_groq_client", return_value=client):
            result = suggest_outfit(VALID_ITEM, {"items": "not-a-list"})

        self.assertIn("General outfit idea", result)
        create.assert_called_once()
        prompt = create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("no saved wardrobe items", prompt.lower())

    def test_missing_new_item_returns_actionable_error_without_llm_call(self):
        with patch.object(tools, "_get_groq_client") as get_client:
            result = suggest_outfit({}, WARDROBE)

        self.assertIn("selected listing", result.lower())
        get_client.assert_not_called()

    def test_incomplete_new_item_returns_missing_fields_without_llm_call(self):
        incomplete_item = {"title": "Mystery top", "category": "tops"}

        with patch.object(tools, "_get_groq_client") as get_client:
            result = suggest_outfit(incomplete_item, WARDROBE)

        self.assertIn("complete listing", result.lower())
        self.assertIn("style_tags", result)
        self.assertIn("colors", result)
        get_client.assert_not_called()

    def test_llm_failure_returns_actionable_error(self):
        with patch.object(
            tools,
            "_get_groq_client",
            side_effect=ValueError("GROQ_API_KEY not set"),
        ):
            result = suggest_outfit(VALID_ITEM, WARDROBE)

        self.assertIn("couldn't generate", result.lower())
        self.assertIn("GROQ_API_KEY", result)

    def test_empty_llm_response_returns_actionable_error(self):
        client, _ = fake_groq_client("   ")

        with patch.object(tools, "_get_groq_client", return_value=client):
            result = suggest_outfit(VALID_ITEM, WARDROBE)

        self.assertIn("couldn't generate", result.lower())
        self.assertIn("wardrobe details", result.lower())

    def test_malformed_llm_response_returns_actionable_error(self):
        create = Mock(return_value=types.SimpleNamespace(choices=[]))
        client = types.SimpleNamespace(
            chat=types.SimpleNamespace(
                completions=types.SimpleNamespace(create=create),
            )
        )

        with patch.object(tools, "_get_groq_client", return_value=client):
            result = suggest_outfit(VALID_ITEM, WARDROBE)

        self.assertIn("couldn't read", result.lower())
        self.assertIn("Groq response format", result)


if __name__ == "__main__":
    unittest.main()
