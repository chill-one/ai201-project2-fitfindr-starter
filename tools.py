"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"
FIT_CARD_TEMPERATURE = 1.0
TRENDS_PATH = Path(__file__).parent / "data" / "trends.json"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    Implementation:
        Loads all listings with load_listings(), filters by optional price and
        size constraints, scores remaining listings by keyword overlap with
        `description`, and returns positive matches in descending score order.
    """
    if not description or not description.strip():
        return []

    try:
        price_ceiling = float(max_price) if max_price is not None else None
    except (TypeError, ValueError):
        return []

    def tokenize(text: str) -> set[str]:
        """
        Convert text into lowercase alphanumeric tokens for simple matching.

        Punctuation and symbols are ignored, so values like "S/M" become
        separate searchable tokens such as {"s", "m"}.
        """
        return set(re.findall(r"[a-z0-9]+", text.lower()))

    def listing_search_text(listing: dict) -> str:
        """
        Build one searchable string from all listing fields relevant to search.

        This lets the keyword scorer compare the user's description against the
        title, description, category, size, condition, brand, platform, style
        tags, and colors using the same tokenization logic.
        """
        searchable_parts = [
            listing.get("title", ""),
            listing.get("description", ""),
            listing.get("category", ""),
            listing.get("size", ""),
            listing.get("condition", ""),
            listing.get("brand") or "",
            listing.get("platform", ""),
            " ".join(listing.get("style_tags", [])),
            " ".join(listing.get("colors", [])),
        ]
        return " ".join(searchable_parts)

    def size_matches(listing_size: str, requested_size: str | None) -> bool:
        """
        Return whether a listing size satisfies the optional requested size.

        Matching is case-insensitive and supports both token matches
        ("M" matches "S/M") and compact substring matches for sizes that use
        spacing or punctuation differently.
        """
        if not requested_size:
            return True

        requested = requested_size.strip().lower()
        listed = listing_size.lower()
        if not requested:
            return True

        requested_tokens = tokenize(requested)
        listed_tokens = tokenize(listed)
        if requested_tokens and requested_tokens.issubset(listed_tokens):
            return True

        compact_requested = re.sub(r"\s+", "", requested)
        compact_listed = re.sub(r"\s+", "", listed)
        return compact_requested in compact_listed

    query_tokens = tokenize(description)
    if not query_tokens:
        return []

    try:
        listings = load_listings()
    except (OSError, ValueError):
        return []

    if not isinstance(listings, list):
        return []

    scored_listings = []
    for listing in listings:
        if not isinstance(listing, dict):
            continue

        if price_ceiling is not None and listing.get("price", 0) > price_ceiling:
            continue

        if not size_matches(listing.get("size", ""), size):
            continue

        listing_tokens = tokenize(listing_search_text(listing))
        score = len(query_tokens & listing_tokens)
        if score == 0:
            continue

        scored_listings.append((score, listing.get("price", float("inf")), listing))

    scored_listings.sort(key=lambda result: (-result[0], result[1]))
    return [listing for _, _, listing in scored_listings]


# ── Stretch Tool: compare_price ────────────────────────────────────────────────

def compare_price(item: dict, listings: list[dict] | None = None) -> dict:
    """
    Estimate whether a listing price is fair using comparable dataset items.

    Comparables prioritize listings in the same category with overlapping style
    tags or colors. If that is too narrow, the tool falls back to same-category
    listings so the user still gets a useful price assessment.
    """
    if not isinstance(item, dict) or not item:
        return {
            "assessment": "unknown",
            "item_price": None,
            "average_comparable_price": None,
            "comparable_count": 0,
            "comparables": [],
            "reasoning": "A selected item is required before comparing price.",
        }

    try:
        item_price = float(item["price"])
    except (KeyError, TypeError, ValueError):
        return {
            "assessment": "unknown",
            "item_price": None,
            "average_comparable_price": None,
            "comparable_count": 0,
            "comparables": [],
            "reasoning": "The selected item is missing a usable price.",
        }

    if listings is None:
        try:
            listings = load_listings()
        except (OSError, ValueError):
            listings = []

    item_id = item.get("id")
    item_category = item.get("category")
    item_tags = {tag.lower() for tag in item.get("style_tags", [])}
    item_colors = {color.lower() for color in item.get("colors", [])}

    same_category = [
        listing for listing in listings
        if isinstance(listing, dict)
        and listing.get("id") != item_id
        and listing.get("category") == item_category
        and isinstance(listing.get("price"), (int, float))
    ]
    comparable_listings = [
        listing for listing in same_category
        if item_tags & {tag.lower() for tag in listing.get("style_tags", [])}
        or item_colors & {color.lower() for color in listing.get("colors", [])}
    ]

    if len(comparable_listings) < 2:
        comparable_listings = same_category

    if not comparable_listings:
        return {
            "assessment": "unknown",
            "item_price": item_price,
            "average_comparable_price": None,
            "comparable_count": 0,
            "comparables": [],
            "reasoning": "There are not enough comparable listings in the dataset.",
        }

    average_price = sum(float(listing["price"]) for listing in comparable_listings) / len(
        comparable_listings
    )
    price_difference = item_price - average_price

    if item_price <= average_price * 0.9:
        assessment = "good deal"
    elif item_price <= average_price * 1.1:
        assessment = "fair price"
    else:
        assessment = "priced high"

    comparables = [
        {
            "id": listing.get("id"),
            "title": listing.get("title"),
            "price": listing.get("price"),
        }
        for listing in sorted(comparable_listings, key=lambda listing: listing["price"])[:5]
    ]

    return {
        "assessment": assessment,
        "item_price": round(item_price, 2),
        "average_comparable_price": round(average_price, 2),
        "price_difference": round(price_difference, 2),
        "comparable_count": len(comparable_listings),
        "comparables": comparables,
        "reasoning": (
            f"This {item_category or 'item'} is ${item_price:.2f}. "
            f"Comparable dataset listings average ${average_price:.2f}, "
            f"so it is {assessment}."
        ),
    }


# ── Stretch Tool: check_trends ─────────────────────────────────────────────────

def check_trends(description: str, size: str | None = None) -> dict:
    """
    Return trend context that can influence outfit suggestions.

    The tool reads an offline trend snapshot adapted from public fashion tag
    patterns. This keeps the demo deterministic while still making trend context
    explicit and testable.
    """
    try:
        with open(TRENDS_PATH, "r", encoding="utf-8") as trend_file:
            snapshot = json.load(trend_file)
    except (OSError, ValueError, json.JSONDecodeError):
        return {
            "source": "unavailable",
            "snapshot_date": None,
            "matched_trends": [],
            "trend_tags": [],
            "influence": "Trend data is unavailable, so the outfit suggestion will rely on the item and wardrobe only.",
            "size": size,
        }

    query_tokens = set(re.findall(r"[a-z0-9]+", (description or "").lower()))
    scored_trends = []
    for trend in snapshot.get("trends", []):
        keywords = {keyword.lower() for keyword in trend.get("keywords", [])}
        style_tags = {tag.lower() for tag in trend.get("style_tags", [])}
        score = len(query_tokens & (keywords | style_tags))
        if score:
            scored_trends.append((score, trend))

    scored_trends.sort(key=lambda trend_score: trend_score[0], reverse=True)
    matched_trends = [trend for _, trend in scored_trends[:2]]

    if not matched_trends and snapshot.get("trends"):
        matched_trends = [snapshot["trends"][0]]

    trend_tags = []
    influences = []
    for trend in matched_trends:
        trend_tags.extend(trend.get("style_tags", []))
        influences.append(f"{trend.get('name')}: {trend.get('outfit_influence')}")

    unique_tags = list(dict.fromkeys(trend_tags))
    influence = " ".join(influences) if influences else (
        "No direct trend match was found, so the outfit suggestion should stay wardrobe-led."
    )

    return {
        "source": snapshot.get("source", "offline trend snapshot"),
        "snapshot_date": snapshot.get("snapshot_date"),
        "matched_trends": matched_trends,
        "trend_tags": unique_tags,
        "influence": influence,
        "size": size,
    }


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    Implementation:
        Validates the selected listing, formats the user's wardrobe if present,
        and asks Groq's llama-3.3-70b-versatile model for 1-2 outfit ideas.
    """
    if not isinstance(new_item, dict) or not new_item:
        return "I need a selected listing before I can suggest an outfit."

    required_fields = ["title", "category", "style_tags", "colors", "price", "platform"]
    missing_fields = [
        field for field in required_fields
        if field not in new_item or new_item[field] in (None, "", [])
    ]
    if missing_fields:
        return (
            "I need a complete listing before I can suggest an outfit. "
            f"Missing: {', '.join(missing_fields)}."
        )

    wardrobe_items = []
    style_profile = {}
    trend_info = {}
    if isinstance(wardrobe, dict) and isinstance(wardrobe.get("items"), list):
        wardrobe_items = [
            item for item in wardrobe["items"]
            if isinstance(item, dict) and item.get("name")
        ]
        style_profile = wardrobe.get("_style_profile") or {}
        trend_info = wardrobe.get("_trend_info") or {}

    item_summary = (
        f"Title: {new_item['title']}\n"
        f"Category: {new_item['category']}\n"
        f"Style tags: {', '.join(new_item.get('style_tags', []))}\n"
        f"Colors: {', '.join(new_item.get('colors', []))}\n"
        f"Price/platform: ${new_item['price']} on {new_item['platform']}"
    )

    context_sections = []
    remembered_preferences = style_profile.get("preferences", [])
    if remembered_preferences:
        context_sections.append(
            "Remembered style profile: "
            + ", ".join(remembered_preferences)
            + ". Use these preferences when choosing the outfit vibe."
        )

    if trend_info.get("matched_trends"):
        context_sections.append(
            "Current trend context: "
            + trend_info.get("influence", "")
            + " Trend tags: "
            + ", ".join(trend_info.get("trend_tags", []))
            + ". Let this influence the outfit suggestion visibly."
        )

    extra_context = "\n\n".join(context_sections)

    if wardrobe_items:
        wardrobe_summary = "\n".join(
            "- "
            f"{item['name']} "
            f"({item.get('category', 'unknown category')}; "
            f"colors: {', '.join(item.get('colors', [])) or 'unknown'}; "
            f"style tags: {', '.join(item.get('style_tags', [])) or 'none'}"
            f"{'; notes: ' + item['notes'] if item.get('notes') else ''})"
            for item in wardrobe_items
        )
        user_prompt = f"""
New thrifted item:
{item_summary}

User wardrobe:
{wardrobe_summary}

{extra_context}

Suggest 1-2 complete outfits using the new item. Use exact wardrobe item names
when possible, and fill in any missing category with a simple general piece.
Keep the answer specific, concise, and wearable.
""".strip()
    else:
        user_prompt = f"""
New thrifted item:
{item_summary}

The user has no saved wardrobe items yet. Suggest 1-2 complete outfits using
general clothing categories instead of named closet pieces. Mention that these
are general styling ideas because no wardrobe items were provided.

{extra_context}

Keep the answer specific, concise, and wearable.
""".strip()

    messages = [
        {
            "role": "system",
            "content": (
                "You are FitFindr, a practical secondhand styling assistant. "
                "Return only outfit suggestions, not shopping search results."
            ),
        },
        {"role": "user", "content": user_prompt},
    ]

    try:
        completion = _get_groq_client().chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=450,
        )
    except Exception:
        return (
            "I couldn't generate an outfit suggestion right now. "
            "Check your GROQ_API_KEY and try again."
        )

    try:
        outfit = completion.choices[0].message.content.strip()
    except (AttributeError, IndexError, TypeError):
        return (
            "I couldn't read the outfit suggestion from the LLM response. "
            "Try again or check the Groq response format."
        )

    if not outfit:
        return (
            "I couldn't generate an outfit suggestion from the current item. "
            "Try again or add more wardrobe details."
        )

    return outfit


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    Implementation:
        Validates the outfit and selected listing, then asks Groq's
        llama-3.3-70b-versatile model for a short caption at high temperature
        so repeated calls can produce different wording.
    """
    if not isinstance(outfit, str) or not outfit.strip():
        return "I need an outfit suggestion before I can create a fit card."

    if not isinstance(new_item, dict) or not new_item:
        return "I need a selected listing before I can create a fit card."

    required_fields = ["title", "price", "platform"]
    missing_fields = [
        field for field in required_fields
        if field not in new_item or new_item[field] in (None, "")
    ]
    if missing_fields:
        return (
            "I need complete item details before I can create a fit card. "
            f"Missing: {', '.join(missing_fields)}."
        )

    item_summary = (
        f"Title: {new_item['title']}\n"
        f"Price: ${new_item['price']}\n"
        f"Platform: {new_item['platform']}\n"
        f"Category: {new_item.get('category', 'unknown')}\n"
        f"Colors: {', '.join(new_item.get('colors', [])) or 'unknown'}\n"
        f"Style tags: {', '.join(new_item.get('style_tags', [])) or 'none'}"
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You write casual, authentic outfit captions for thrifted fits. "
                "Sound like a real social post, not a catalog description."
            ),
        },
        {
            "role": "user",
            "content": f"""
Create a 2-4 sentence fit card caption for this outfit.

Selected thrifted item:
{item_summary}

Outfit suggestion:
{outfit.strip()}

Requirements:
- Mention the item title, price, and platform naturally once.
- Capture the outfit vibe in specific terms.
- Make it shareable, casual, and caption-like.
- Do not include hashtags unless they feel natural.
- Return only the caption text.
""".strip(),
        },
    ]

    try:
        completion = _get_groq_client().chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=FIT_CARD_TEMPERATURE,
            max_tokens=220,
        )
    except Exception:
        return (
            "I couldn't generate a fit card right now. "
            "Check your GROQ_API_KEY and try again."
        )

    try:
        fit_card = completion.choices[0].message.content.strip()
    except (AttributeError, IndexError, TypeError):
        return (
            "I couldn't read the fit card from the LLM response. "
            "Try again or check the Groq response format."
        )

    if not fit_card:
        return (
            "I couldn't generate a fit card from the current outfit. "
            "Try again with a more specific outfit suggestion."
        )

    return fit_card
