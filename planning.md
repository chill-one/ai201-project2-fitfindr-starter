# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches `data/listings.json` for secondhand items that match the user's requested item description, optional size, and optional maximum price. It filters out listings above the user's budget, optionally filters by size, scores the remaining listings by keyword/style overlap, and returns the best matches first.

**Input parameters:**
- `description` (str): The item or style the user wants, such as `"vintage graphic tee"` or `"black combat boots"`.
- `size` (str | None): The requested size, such as `"M"`, `"S/M"`, `"W30"`, or `"US 8"`. If `None`, the search does not filter by size.
- `max_price` (float | None): The highest price the user wants to pay. If `None`, the search does not filter by price.

**What it returns:**
A `list[dict]` of matching listing dictionaries, sorted from strongest to weakest match. Each result contains:
- `id` (str): Unique listing id, such as `"lst_002"`.
- `title` (str): Listing title.
- `description` (str): Seller-provided item description.
- `category` (str): One of `tops`, `bottoms`, `outerwear`, `shoes`, or `accessories`.
- `style_tags` (list[str]): Style keywords such as `["y2k", "vintage", "graphic tee"]`.
- `size` (str): Seller-listed size.
- `condition` (str): Item condition, such as `excellent`, `good`, or `fair`.
- `price` (float): Item price.
- `colors` (list[str]): Main item colors.
- `brand` (str | None): Brand name when available.
- `platform` (str): Marketplace, such as `depop`, `thredUp`, or `poshmark`.

Example return value:

```python
[
    {
        "id": "lst_002",
        "title": "Y2K Baby Tee — Butterfly Print",
        "description": "Super cute early 2000s baby tee with butterfly graphic. Fitted crop length. Tag says medium but fits like a small.",
        "category": "tops",
        "style_tags": ["y2k", "vintage", "graphic tee", "cottagecore"],
        "size": "S/M",
        "condition": "excellent",
        "price": 18.00,
        "colors": ["white", "pink", "purple"],
        "brand": None,
        "platform": "depop",
    }
]
```

**What happens if it fails or returns nothing:**
The tool returns an empty list instead of crashing. The agent stores that empty result in session state, tells the user no matching listing was found, and does not call `suggest_outfit` with missing item data. For the stretch retry path, the agent may retry with loosened filters, such as dropping the size filter and then removing the price cap, and must tell the user exactly what was adjusted.

---

### Tool 2: suggest_outfit

**What it does:**
Given one selected listing and the user's current wardrobe, suggests one or two complete outfit combinations. When the wardrobe has usable pieces, the suggestions must name specific wardrobe items; when the wardrobe is empty or very minimal, the tool gives general styling advice instead of failing.

**Input parameters:**
- `new_item` (dict): The listing dictionary selected from `search_listings`. It should include fields like `title`, `category`, `style_tags`, `colors`, `price`, and `platform`.
- `wardrobe` (dict): A wardrobe object with an `items` key. `wardrobe["items"]` is a `list[dict]`, where each wardrobe item contains `id`, `name`, `category`, `colors`, `style_tags`, and optional `notes`.

**What it returns:**
A non-empty `str` containing one or two complete outfit suggestions. A complete outfit should include the new item plus enough supporting pieces to feel wearable, such as bottoms, shoes, outerwear, and/or accessories. If possible, it should reference exact wardrobe item names like `"Baggy straight-leg jeans, dark wash"` and `"Chunky white sneakers"`.

Example return value:

```text
Outfit 1: Wear the Y2K Baby Tee — Butterfly Print with the baggy straight-leg jeans, chunky white sneakers, and black crossbody bag for a casual vintage streetwear look.

Outfit 2: Layer it under the vintage black denim jacket with the wide-leg khaki trousers and brown leather belt for a softer 2000s-meets-classic outfit.
```

**What happens if it fails or returns nothing:**
If `new_item` is missing or not a dictionary, the tool returns a clear error string explaining that an item is required before styling can happen. If `wardrobe["items"]` is empty, the tool returns general outfit guidance using categories rather than named closet items, for example: "Pair this tee with relaxed denim, white sneakers, and a small shoulder bag." The agent can still pass that general styling response to `create_fit_card` as long as the response is not empty.

---

### Tool 3: create_fit_card

**What it does:**
Creates a short, shareable caption for the completed outfit. The caption should sound like an outfit post, not a product description, and should naturally mention the selected item, its price, platform, and overall outfit vibe.

**Input parameters:**
- `outfit` (str): The outfit suggestion returned by `suggest_outfit`.
- `new_item` (dict): The selected listing dictionary returned by `search_listings`.

**What it returns:**
A `str` containing a 2-4 sentence fit card caption. It should be concise, social-media-friendly, and specific to the chosen item and outfit. Different inputs should produce different captions because the prompt includes the selected item details and outfit context.

Example return value:

```text
Found this butterfly baby tee on Depop for $18 and immediately knew it needed baggy denim and chunky sneakers. The whole fit gives soft Y2K thrift energy without trying too hard. Tiny tee, big jeans, easy win.
```

**What happens if it fails or returns nothing:**
If `outfit` is empty, whitespace-only, or missing, the tool returns a specific error message: `"I need an outfit suggestion before I can create a fit card."` If `new_item` is missing required fields like `title`, `price`, or `platform`, the agent tells the user which item details are missing and asks them to choose another listing or retry the search.

---

### Additional Tools (if any)

### Stretch Tool: compare_price

**What it does:**
Compares the selected listing price against similar listings in the mock dataset. It checks same-category listings first, then prioritizes comparables with overlapping style tags or colors.

**Input parameters:**
- `item` (dict): The selected listing.
- `listings` (list[dict] | None): Optional comparable mock listings from the same dataset. If `None`, the tool uses `load_listings()`.

**What it returns:**
A `dict` with:
- `assessment` (str): `"good deal"`, `"fair price"`, `"priced high"`, or `"unknown"`.
- `item_price` (float | None): The selected item's price.
- `average_comparable_price` (float | None): Average price of comparable listings.
- `price_difference` (float | None): Selected price minus comparable average.
- `comparable_count` (int): Number of comparable listings used.
- `comparables` (list[dict]): Up to five comparable listing summaries.
- `reasoning` (str): Short explanation for the assessment.

**What happens if it fails or returns nothing:**
If there are not enough comparable listings, the tool returns an explanation that the dataset is too small for a confident price assessment.

### Stretch Tool: check_trends

**What it does:**
Checks an offline trend snapshot in `data/trends.json` and returns trend context that can influence the outfit suggestion. This makes trend awareness deterministic for tests and demos.

**Input parameters:**
- `description` (str): The parsed search description, such as `"vintage graphic tee"`.
- `size` (str | None): The user's requested size, stored in the result for display and future filtering.

**What it returns:**
A `dict` with:
- `source` (str): Where the trend snapshot came from.
- `snapshot_date` (str | None): Date of the snapshot.
- `matched_trends` (list[dict]): Trends whose keywords overlap the search.
- `trend_tags` (list[str]): Style tags from the matched trends.
- `influence` (str): Styling guidance to pass into `suggest_outfit`.
- `size` (str | None): The requested size.

**What happens if it fails or returns nothing:**
If the trend file cannot be loaded, the tool returns an empty trend result and explains that styling should rely on the selected item and wardrobe only.

### Stretch Feature: style profile memory

**What it does:**
Stores remembered style preferences across sessions in `.fitfindr_style_profile.json`.

**Input parameters:**
- `query` (str): The user's latest request.
- `wardrobe` (dict): The user's wardrobe.

**What it returns:**
A profile `dict` with:
- `preferences` (list[str]): Remembered style terms such as `"grunge"`, `"streetwear"`, and `"chunky"`.
- `interaction_count` (int): Number of interactions saved.

**What happens if it fails or returns nothing:**
If the memory file is missing or malformed, the agent starts with an empty profile. If saving fails, the agent continues the current interaction without crashing.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The agent uses a session dictionary and a loop that checks what information is already available before choosing the next action. It does not call all tools blindly.

1. Start with the user's natural language query and wardrobe.
2. Parse the query into:
   - `description`
   - `size`
   - `max_price`
3. Update style memory from the query and wardrobe, then store it in `session["style_profile"]`.
4. If the parsed description is missing, ask the user what kind of item they want before calling search.
5. If there is no `search_results` in session state, call `search_listings(description, size, max_price)`.
6. If `search_listings` returns an empty list, retry with loosened constraints:
   - First retry with the size filter removed.
   - If that still fails and the user gave a price cap, retry with the price cap removed.
   - Store each fallback in `session["retry_attempts"]`.
7. If all search attempts return empty lists, stop the happy path. The agent tells the user what failed, which fallbacks were tried, and asks the user to broaden the item description, size, or budget.
8. If search results exist but `selected_item` is empty, choose the top-ranked listing and store it as `selected_item`.
9. If `selected_item` exists, call `compare_price(selected_item)` and store the returned assessment.
10. If `selected_item` exists, call `check_trends(description, size)` and store the trend context.
11. If `selected_item` exists but `outfit_suggestion` is empty, call `suggest_outfit(selected_item, contextual_wardrobe)`, where `contextual_wardrobe` contains the original wardrobe plus the style profile and trend info.
12. If `suggest_outfit` returns an empty or error response, tell the user the selected item could not be styled and ask for more wardrobe details or use general styling advice if possible.
13. If `outfit_suggestion` exists but `fit_card` is empty, call `create_fit_card(outfit_suggestion, selected_item)`.
14. The loop is done when `fit_card` is populated or when `session["error"]` is set.

This makes the agent adaptive. For a normal query, it searches, checks price and trends, styles the selected item, and creates a caption. For a retry query like `"vintage graphic tee size XXS under $30"`, it tries the exact search first, then removes the size filter and continues only if that produces a listing. For a no-result query like `"designer ballgown size XXS under $5"`, it stops after fallback search attempts and gives a specific no-results message instead of trying to create an outfit from nonexistent data.

---

## State Management

**How does information from one tool get passed to the next?**

The agent stores all session data in one dictionary created by `_new_session(query, wardrobe)`. This dictionary is the shared state for the whole interaction.

Tracked state:
- `query`: The original user request.
- `parsed`: The extracted `description`, `size`, and `max_price`.
- `search_results`: The list returned by `search_listings`.
- `selected_item`: The top listing chosen from `search_results`.
- `wardrobe`: The user's wardrobe dict.
- `outfit_suggestion`: The string returned by `suggest_outfit`.
- `fit_card`: The string returned by `create_fit_card`.
- `price_assessment`: The dict returned by `compare_price`.
- `trend_info`: The dict returned by `check_trends`.
- `style_profile`: Remembered preferences loaded from and saved to `.fitfindr_style_profile.json`.
- `retry_attempts`: Search fallback attempts and result counts.
- `retry_message`: A user-facing explanation when fallback search succeeds.
- `error`: A clear message if the workflow stops early.

Data flow:
- `search_listings` returns `search_results`.
- The agent saves the first/best result as `selected_item`.
- `selected_item` is passed directly into `compare_price` and then into `suggest_outfit` as `new_item`; the user does not re-enter it.
- `check_trends` uses the parsed description and size, then stores trend context in `trend_info`.
- Style memory is attached to a copy of the wardrobe along with `trend_info`.
- `suggest_outfit` returns `outfit_suggestion`.
- `outfit_suggestion` and the same `selected_item` are passed directly into `create_fit_card`.
- The final UI reads `selected_item`, `outfit_suggestion`, and `fit_card` from the session dict.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No results match the description, size, and price filters. | Store `search_results = []`, retry with loosened constraints, and do not call `suggest_outfit` unless a fallback search returns a listing. If all fallbacks fail, tell the user what to broaden. |
| `search_listings` | Listings file cannot be loaded or has invalid data. | Catch the error, set `session["error"]`, and tell the user the listing catalog is unavailable instead of crashing. |
| `suggest_outfit` | `wardrobe["items"]` is empty. | Return general styling advice based on the selected item category, colors, and style tags. Tell the user that no saved wardrobe items were available, so the suggestion uses general pieces. |
| `suggest_outfit` | `new_item` is missing or malformed. | Return an actionable error string and stop before `create_fit_card`, because a fit card needs a real listing. |
| `create_fit_card` | `outfit` input is missing, empty, or only whitespace. | Return `"I need an outfit suggestion before I can create a fit card."` The agent displays this as the fit card panel error. |
| `create_fit_card` | `new_item` is missing key details like title, price, or platform. | Return a message explaining which details are missing and ask the user to choose another listing or retry the search. |
| `compare_price` | The selected item is missing a usable price or there are no comparable listings. | Return `assessment = "unknown"` with a concrete reason, and continue the main workflow because outfit styling can still happen. |
| `check_trends` | The trend snapshot file cannot be read. | Return empty trend context with a message explaining that styling will rely on the item and wardrobe only. |
| Style profile memory | Memory file is missing, malformed, or cannot be saved. | Start from an empty profile or skip saving, then continue the current interaction without crashing. |
| Retry fallback | Exact search returns no results. | Retry with size removed first, then price cap removed if needed. Tell the user what was adjusted if a retry succeeds, or list the fallback attempts if all retries fail. |

---

## Architecture

```mermaid
flowchart TD
    A[User query + wardrobe choice] --> B[Create session dict]
    B --> C[Parse query into description, size, max_price]
    C --> C2[Update style profile memory]
    C2 --> D{Description found?}
    D -- No --> E[Ask user for item description]
    E --> Z[Return session to UI]
    D -- Yes --> F[search_listings(description, size, max_price)]

    F --> G{Any matching listings?}
    G -- No --> J[Retry with loosened filters]
    J --> G
    G -- Still no --> H[Set session error and suggest broader search]
    H --> Z[Return session to UI]

    G -- Yes --> K[Store search_results]
    K --> L[Select top result as selected_item]
    L --> L2[compare_price(selected_item)]
    L2 --> L3[check_trends(description, size)]
    L3 --> L4[Attach style_profile and trend_info to wardrobe copy]
    L4 --> M[suggest_outfit(selected_item, contextual_wardrobe)]

    M --> N{Outfit returned?}
    N -- No --> O[Set styling error or ask for wardrobe details]
    O --> Z
    N -- Yes --> P[Store outfit_suggestion]
    P --> Q[create_fit_card(outfit_suggestion, selected_item)]

    Q --> R{Fit card returned?}
    R -- No --> S[Show fit card error]
    S --> Z
    R -- Yes --> T[Store fit_card]
    T --> Z[Return selected listing, outfit, and fit card]
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

I will use ChatGPT/Codex to help implement the three required tools one at a time. I will give the AI the `Tools` section of this planning document, the `data_loader.py` helper functions, and the relevant data shapes from `listings.json` and `wardrobe_schema.json`.

For `search_listings`, I will ask the AI to implement keyword scoring, optional size filtering, optional max price filtering, and empty-list behavior. I will verify the output by testing at least three searches:
- A happy path query like `"vintage graphic tee"` under `$30`.
- A price-filtered query that should exclude expensive listings.
- A no-results query like `"designer ballgown size XXS under $5"`.

For `suggest_outfit`, I will ask the AI to implement the prompt or rule-based logic using the selected listing and wardrobe schema. I will verify it with:
- The example wardrobe, where it should name real wardrobe pieces.
- The empty wardrobe, where it should give general styling advice instead of crashing.

For `create_fit_card`, I will ask the AI to write the prompt and guard clauses based on the `create_fit_card` spec. I will verify that it:
- Returns a caption for a valid outfit.
- Mentions the selected item, platform, and price naturally.
- Returns a clear error message when the outfit input is empty.

**Milestone 4 — Planning loop and state management:**

I will use ChatGPT/Codex to implement `run_agent` using the `Planning Loop`, `State Management`, `Error Handling`, and `Architecture` sections of this planning document. I will ask it to preserve the session keys already defined in `_new_session` so the demo can show state flowing between tools.

I will verify the planning loop by running:
- A complete happy-path interaction that fills `selected_item`, `outfit_suggestion`, and `fit_card`.
- A no-results interaction that sets `session["error"]` and does not call the later tools.
- An empty-wardrobe interaction that still produces a styling suggestion and fit card.

I will also review any generated code manually to make sure it matches this spec instead of adding unrelated tools or changing function signatures.

**Milestone 5 — Stretch features:**

I will use ChatGPT/Codex to implement and test the four stretch features after the core workflow is working:
- Price comparison with `compare_price(item, listings=None)`.
- Style profile memory stored in `.fitfindr_style_profile.json`.
- Trend awareness with `check_trends(description, size=None)` using a deterministic local trend snapshot.
- Retry logic that removes the size filter first, then removes the price cap if no results are still found.

I will verify the stretch work by running tests that prove:
- Price comparison returns an assessment and reasoning based on comparable listings.
- Style memory persists across two sessions without the user re-entering preferences.
- Trend context is passed into the `suggest_outfit` LLM prompt.
- The planning loop continues after a successful fallback search, but still stops gracefully when every fallback fails.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30, size M. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1: Parse the query**

The agent creates a new session and extracts:

```python
session["parsed"] = {
    "description": "vintage graphic tee",
    "size": "M",
    "max_price": 30.00,
}
```

The wardrobe is loaded from the example wardrobe, which includes items like baggy straight-leg jeans, chunky white sneakers, a vintage black denim jacket, and a black crossbody bag.

The agent also updates style memory from the query and wardrobe. For this example, the remembered profile can include terms like `baggy`, `chunky`, `streetwear`, and `vintage`.

**Step 2: Search listings**

The agent calls:

```python
search_listings(
    description="vintage graphic tee",
    size="M",
    max_price=30.00,
)
```

The tool searches the mock listings dataset and returns matching items. A likely top result is:

```python
{
    "id": "lst_002",
    "title": "Y2K Baby Tee — Butterfly Print",
    "category": "tops",
    "style_tags": ["y2k", "vintage", "graphic tee", "cottagecore"],
    "size": "S/M",
    "price": 18.00,
    "platform": "depop",
    "colors": ["white", "pink", "purple"],
}
```

The agent stores the full result list in `session["search_results"]` and stores the best result in `session["selected_item"]`.

If there are no exact matches, the agent retries by removing the size filter first, then removing the price cap if needed. If every fallback fails, the agent stops here, explains that no listing matched the user's constraints, lists the fallback attempts, and asks the user to loosen one of those constraints.

**Step 3: Compare price and check trends**

Because `session["selected_item"]` exists, the agent calls:

```python
compare_price(session["selected_item"])
check_trends(description="vintage graphic tee", size="M")
```

The price result is stored in `session["price_assessment"]`. The trend result is stored in `session["trend_info"]`, then passed into the outfit prompt so the styling can visibly reflect current graphic tee, baggy denim, and chunky sneaker trends.

**Step 4: Suggest an outfit**

Because `session["selected_item"]` exists, the agent calls:

```python
suggest_outfit(
    new_item=session["selected_item"],
    wardrobe=contextual_wardrobe,
)
```

`contextual_wardrobe` contains the original wardrobe items plus `session["style_profile"]` and `session["trend_info"]`. The tool uses the selected tee, the wardrobe items, remembered style preferences, and trend context to suggest complete outfits, for example:

```text
Outfit 1: Wear the Y2K Baby Tee — Butterfly Print with the baggy straight-leg jeans, chunky white sneakers, and black crossbody bag for an easy vintage streetwear outfit.

Outfit 2: Layer it with the vintage black denim jacket, wide-leg khaki trousers, and brown leather belt for a softer Y2K-meets-classic look.
```

The agent stores this in `session["outfit_suggestion"]`.

If the wardrobe is empty, the tool still returns a useful suggestion using general items, such as relaxed denim, white sneakers, and a small bag. The agent tells the user the suggestion is general because no saved wardrobe items were available.

**Step 5: Create the fit card**

Because `session["outfit_suggestion"]` exists, the agent calls:

```python
create_fit_card(
    outfit=session["outfit_suggestion"],
    new_item=session["selected_item"],
)
```

The tool returns a short caption:

```text
Found this butterfly baby tee on Depop for $18 and immediately knew it needed baggy denim and chunky sneakers. The whole fit gives soft Y2K thrift energy without trying too hard. Tiny tee, big jeans, easy win.
```

The agent stores this in `session["fit_card"]`.

**Final output to user:**

The user sees three panels:

1. Top listing found: the selected listing title, price, size, platform, condition, colors, short description, price check, trend context, style memory, and fallback message when applicable.
2. Outfit idea: one or two complete outfit suggestions using the selected item and wardrobe.
3. Fit card: a short shareable caption for the outfit.

This full interaction uses all three required tools in sequence, while the planning loop still adapts when search fails or the wardrobe is empty.
