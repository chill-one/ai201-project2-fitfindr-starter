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
from tools import FIT_CARD_TEMPERATURE, GROQ_MODEL, create_fit_card


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

OUTFIT = (
    "Outfit 1: Wear the Y2K Baby Tee — Butterfly Print with baggy straight-leg "
    "jeans, chunky white sneakers, and a black crossbody bag."
)


def response_with_content(content: str):
    return types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                message=types.SimpleNamespace(content=content),
            )
        ]
    )


def fake_groq_client(*contents: str):
    responses = [response_with_content(content) for content in contents]
    create = Mock(side_effect=responses)
    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=create),
        )
    )
    return client, create


class CreateFitCardTest(unittest.TestCase):
    def test_uses_groq_model_high_temperature_and_item_context(self):
        client, create = fake_groq_client(
            "Found this Y2K Baby Tee — Butterfly Print on Depop for $18.0 and "
            "styled it with baggy denim and chunky sneakers."
        )

        with patch.object(tools, "_get_groq_client", return_value=client):
            result = create_fit_card(OUTFIT, VALID_ITEM)

        self.assertIn("Y2K Baby Tee", result)
        create.assert_called_once()
        request = create.call_args.kwargs
        self.assertEqual(request["model"], GROQ_MODEL)
        self.assertEqual(request["temperature"], FIT_CARD_TEMPERATURE)
        self.assertGreaterEqual(FIT_CARD_TEMPERATURE, 0.9)
        self.assertIn("Y2K Baby Tee", request["messages"][1]["content"])
        self.assertIn("Depop".lower(), request["messages"][1]["content"].lower())
        self.assertIn(OUTFIT, request["messages"][1]["content"])

    def test_empty_outfit_returns_error_without_llm_call(self):
        with patch.object(tools, "_get_groq_client") as get_client:
            result = create_fit_card("   ", VALID_ITEM)

        self.assertEqual(
            result,
            "I need an outfit suggestion before I can create a fit card.",
        )
        get_client.assert_not_called()

    def test_missing_new_item_returns_error_without_llm_call(self):
        with patch.object(tools, "_get_groq_client") as get_client:
            result = create_fit_card(OUTFIT, {})

        self.assertIn("selected listing", result.lower())
        get_client.assert_not_called()

    def test_incomplete_new_item_returns_missing_fields_without_llm_call(self):
        incomplete_item = {"title": "Mystery top"}

        with patch.object(tools, "_get_groq_client") as get_client:
            result = create_fit_card(OUTFIT, incomplete_item)

        self.assertIn("complete item details", result.lower())
        self.assertIn("price", result)
        self.assertIn("platform", result)
        get_client.assert_not_called()

    def test_llm_failure_returns_actionable_error(self):
        with patch.object(
            tools,
            "_get_groq_client",
            side_effect=ValueError("GROQ_API_KEY not set"),
        ):
            result = create_fit_card(OUTFIT, VALID_ITEM)

        self.assertIn("couldn't generate a fit card", result.lower())
        self.assertIn("GROQ_API_KEY", result)

    def test_malformed_llm_response_returns_actionable_error(self):
        create = Mock(return_value=types.SimpleNamespace(choices=[]))
        client = types.SimpleNamespace(
            chat=types.SimpleNamespace(
                completions=types.SimpleNamespace(create=create),
            )
        )

        with patch.object(tools, "_get_groq_client", return_value=client):
            result = create_fit_card(OUTFIT, VALID_ITEM)

        self.assertIn("couldn't read", result.lower())
        self.assertIn("Groq response format", result)

    def test_empty_llm_response_returns_actionable_error(self):
        client, _ = fake_groq_client("   ")

        with patch.object(tools, "_get_groq_client", return_value=client):
            result = create_fit_card(OUTFIT, VALID_ITEM)

        self.assertIn("couldn't generate a fit card", result.lower())
        self.assertIn("more specific outfit", result.lower())

    def test_repeated_same_input_can_return_varied_outputs(self):
        client, create = fake_groq_client(
            "Caption A: Butterfly tee, baggy denim, easy Y2K energy.",
            "Caption B: Depop baby tee with chunky sneakers and soft 2000s vibes.",
            "Caption C: Tiny tee, big denim, thrifted fit-card mood.",
        )

        with patch.object(tools, "_get_groq_client", return_value=client):
            outputs = [
                create_fit_card(OUTFIT, VALID_ITEM),
                create_fit_card(OUTFIT, VALID_ITEM),
                create_fit_card(OUTFIT, VALID_ITEM),
            ]

        self.assertEqual(len(set(outputs)), 3)
        self.assertEqual(create.call_count, 3)
        for call in create.call_args_list:
            self.assertEqual(call.kwargs["temperature"], FIT_CARD_TEMPERATURE)


if __name__ == "__main__":
    unittest.main()
