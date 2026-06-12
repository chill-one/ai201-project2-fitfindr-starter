import sys
import types
import unittest
from unittest.mock import patch


dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda: None
sys.modules.setdefault("dotenv", dotenv_stub)

groq_stub = types.ModuleType("groq")
groq_stub.Groq = object
sys.modules.setdefault("groq", groq_stub)

from tools import search_listings


class SearchListingsTest(unittest.TestCase):
    def test_returns_ranked_matches_for_description_size_and_price(self):
        results = search_listings("vintage graphic tee", size="M", max_price=30)

        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["id"], "lst_002")
        self.assertLessEqual(results[0]["price"], 30)

    def test_filters_out_items_above_max_price(self):
        results = search_listings("graphic tee", max_price="25")

        self.assertGreater(len(results), 0)
        self.assertTrue(all(item["price"] <= 25 for item in results))
        self.assertIn("lst_006", [item["id"] for item in results])

    def test_filters_by_size_when_size_is_provided(self):
        results = search_listings("jeans", size="W30", max_price=100)

        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["id"], "lst_001")
        self.assertTrue(all("W30" in item["size"] for item in results))

    def test_returns_empty_list_when_no_results_match(self):
        results = search_listings("designer ballgown", size="XXS", max_price=5)

        self.assertEqual(results, [])

    def test_returns_empty_list_for_invalid_inputs(self):
        self.assertEqual(search_listings("", size="M", max_price=30), [])
        self.assertEqual(
            search_listings("graphic tee", size="M", max_price="not-a-number"),
            [],
        )

    def test_returns_empty_list_when_listings_cannot_load(self):
        with patch("tools.load_listings", side_effect=OSError("missing file")):
            self.assertEqual(search_listings("graphic tee", size="M", max_price=30), [])


if __name__ == "__main__":
    unittest.main()
