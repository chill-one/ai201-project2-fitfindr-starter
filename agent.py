"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract search parameters from a natural language query.

    This parser intentionally stays simple and deterministic for the mock
    dataset: it pulls out a dollar amount after "under", "below", "max", or
    "$", pulls out common size phrases, and treats the remaining text as the
    item description.
    """
    query_text = (query or "").strip()
    normalized = query_text.lower()

    max_price = None
    price_match = re.search(
        r"(?:under|below|max(?:imum)?|less than|up to)\s*\$?\s*(\d+(?:\.\d{1,2})?)",
        normalized,
    )
    if not price_match:
        price_match = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)", normalized)
    if price_match:
        max_price = float(price_match.group(1))

    size = None
    size_match = re.search(
        r"(?:size|sz)\s*[:#-]?\s*(us\s*\d+(?:\.\d)?|w\d{2}(?:\s*l\d{2})?|[a-z]{1,3}(?:/[a-z]{1,3})?|\d+(?:\.\d)?)",
        normalized,
    )
    if size_match:
        size = size_match.group(1).upper()

    description = normalized
    description = re.sub(
        r"(?:under|below|max(?:imum)?|less than|up to)\s*\$?\s*\d+(?:\.\d{1,2})?",
        " ",
        description,
    )
    description = re.sub(r"\$\s*\d+(?:\.\d{1,2})?", " ", description)
    description = re.sub(
        r"(?:in\s+)?(?:size|sz)\s*[:#-]?\s*(?:us\s*\d+(?:\.\d)?|w\d{2}(?:\s*l\d{2})?|[a-z]{1,3}(?:/[a-z]{1,3})?|\d+(?:\.\d)?)",
        " ",
        description,
    )
    description = re.sub(
        r"\b(?:i'?m|i am|looking for|look for|find|want|need|show me|what'?s out there|and how would i style it|please|a|an|the|in)\b",
        " ",
        description,
    )
    description = re.sub(r"[^a-z0-9\s/-]", " ", description)
    description = re.sub(r"\s+", " ", description).strip()

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


def _looks_like_tool_error(response: str) -> bool:
    """Return whether a tool string appears to be an actionable error message."""
    if not isinstance(response, str) or not response.strip():
        return True

    lowered = response.lower()
    return lowered.startswith("i need ") or lowered.startswith("i couldn't ")

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    Implementation follows the planning loop designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    The completed session keeps each tool result in state so later tools can use
    it without asking the user to re-enter information.
    """
    session = _new_session(query, wardrobe)
    session["parsed"] = _parse_query(query)

    description = session["parsed"]["description"]
    size = session["parsed"]["size"]
    max_price = session["parsed"]["max_price"]

    if not description:
        session["error"] = (
            "I need to know what kind of item you're looking for before I can search."
        )
        return session

    session["search_results"] = search_listings(description, size, max_price)
    if not session["search_results"]:
        details = [f'"{description}"']
        if size:
            details.append(f"size {size}")
        if max_price is not None:
            details.append(f"under ${max_price:g}")

        session["error"] = (
            "I couldn't find any listings matching "
            f"{' '.join(details)}. Try a broader description, a different size, "
            "or a higher budget."
        )
        return session

    session["selected_item"] = session["search_results"][0]

    outfit_suggestion = suggest_outfit(session["selected_item"], session["wardrobe"])
    if _looks_like_tool_error(outfit_suggestion):
        session["error"] = (
            outfit_suggestion
            if outfit_suggestion
            else "I couldn't create an outfit suggestion for the selected item."
        )
        return session
    session["outfit_suggestion"] = outfit_suggestion

    fit_card = create_fit_card(session["outfit_suggestion"], session["selected_item"])
    if _looks_like_tool_error(fit_card):
        session["error"] = (
            fit_card
            if fit_card
            else "I couldn't create a fit card from the outfit suggestion."
        )
        return session
    session["fit_card"] = fit_card

    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
