# FitFindr

FitFindr is a small agent that searches a mock secondhand listings dataset, suggests how to style a selected item with a user's wardrobe, and creates a short shareable fit-card caption.

## Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```text
GROQ_API_KEY=your_key_here
```

Run the app:

```bash
python app.py
```

Run tests:

```bash
pytest tests/
```

## Tool Inventory

### `search_listings(description, size, max_price)`

Purpose: Searches `data/listings.json` for secondhand items matching the user's requested item, optional size, and optional budget. It uses `load_listings()` from `utils/data_loader.py`.

Inputs:
- `description` (`str`): Search keywords, such as `"vintage graphic tee"`.
- `size` (`str | None`): Optional size filter, such as `"M"`, `"S/M"`, `"W30"`, or `"US 8"`.
- `max_price` (`float | None`): Optional maximum item price.

Output:
- `list[dict]`: Matching listing dictionaries sorted by relevance and then price. Each listing includes `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`.
- Returns `[]` when there are no matches or the search input cannot be used safely.

### `suggest_outfit(new_item, wardrobe)`

Purpose: Uses Groq `llama-3.3-70b-versatile` to suggest one or two complete outfits for the selected listing. It also reads optional agent context from `wardrobe["_style_profile"]` and `wardrobe["_trend_info"]` so style memory and trend awareness can influence the suggestion.

Inputs:
- `new_item` (`dict`): The selected listing from `search_listings`; expected fields include `title`, `category`, `style_tags`, `colors`, `price`, and `platform`.
- `wardrobe` (`dict`): A wardrobe object with an `items` list. Each wardrobe item can include `id`, `name`, `category`, `colors`, `style_tags`, and `notes`. The agent may add `_style_profile` and `_trend_info` before calling this tool.

Output:
- `str`: A non-empty outfit suggestion. If wardrobe items exist, the prompt asks the model to use exact wardrobe item names. If the wardrobe is empty or malformed, the prompt asks for general styling ideas instead.
- Returns a clear error string if `new_item` is missing/incomplete or the LLM call fails.

### `create_fit_card(outfit, new_item)`

Purpose: Uses Groq `llama-3.3-70b-versatile` to generate a short social-caption-style fit card for the completed outfit.

Inputs:
- `outfit` (`str`): The outfit suggestion returned by `suggest_outfit`.
- `new_item` (`dict`): The selected listing originally returned by `search_listings`.

Output:
- `str`: A 2-4 sentence caption that naturally mentions the selected item, price, platform, and outfit vibe.
- Uses `FIT_CARD_TEMPERATURE = 1.0` so repeated calls can produce varied wording.
- Returns a clear error string if `outfit` is empty, item details are missing, or the LLM call fails.

### `compare_price(item, listings=None)`

Purpose: Stretch feature. Estimates whether the selected listing is a good deal, fair price, or priced high compared with similar listings in the mock dataset.

Inputs:
- `item` (`dict`): The selected listing.
- `listings` (`list[dict] | None`): Optional comparable listings. If omitted, the tool loads the mock dataset with `load_listings()`.

Output:
- `dict`: Includes `assessment`, `item_price`, `average_comparable_price`, `price_difference`, `comparable_count`, `comparables`, and `reasoning`.
- Returns an `"unknown"` assessment with a reason if the selected item is missing a price or there are no comparables.

### `check_trends(description, size=None)`

Purpose: Stretch feature. Reads `data/trends.json`, an offline classroom trend snapshot adapted from public fashion tag patterns, and returns style context that can influence the outfit suggestion.

Inputs:
- `description` (`str`): The parsed search description.
- `size` (`str | None`): Optional user size, stored in the response for display and future filtering.

Output:
- `dict`: Includes `source`, `snapshot_date`, `matched_trends`, `trend_tags`, `influence`, and `size`.
- Returns an empty trend result with an explanation if trend data cannot be loaded.

## Planning Loop

`run_agent(query, wardrobe)` in `agent.py` is the planning loop. It does not call all tools unconditionally.

Current conditional flow:

1. Create a session dictionary with `_new_session(query, wardrobe)`.
2. Parse the natural language query into `description`, `size`, and `max_price`.
3. Update style memory with `update_style_profile(query, wardrobe)` and store it in `session["style_profile"]`.
4. If no usable description is found, set `session["error"]` and stop before search.
5. Call `search_listings(description, size, max_price)`.
6. If search returns `[]`, retry with fallback constraints:
   - First remove the size filter, if one was supplied.
   - Then remove the price cap, if one was supplied and the size fallback still failed.
   - Store each attempt in `session["retry_attempts"]` and store a user-facing explanation in `session["retry_message"]` when a retry succeeds.
7. If no results remain after fallback attempts, set a specific no-results error and stop. The agent does not call `suggest_outfit` or `create_fit_card`.
8. If search returns results, store the top result as `session["selected_item"]`.
9. Call `compare_price(session["selected_item"])` and store the result in `session["price_assessment"]`.
10. Call `check_trends(description, size)` and store the result in `session["trend_info"]`.
11. Build a contextual wardrobe that includes the original wardrobe items plus `_style_profile` and `_trend_info`.
12. Call `suggest_outfit(session["selected_item"], contextual_wardrobe)`.
13. If the outfit tool returns an error-like string, store that in `session["error"]` and stop.
14. Call `create_fit_card(session["outfit_suggestion"], session["selected_item"])`.
15. If the fit-card tool succeeds, return the completed session with `fit_card` populated.

This means a successful query, a retry-success query, and a no-results query take different paths. The integration tests verify that the agent does not blindly call every tool after failed search.

## State Management

The session dictionary is the source of truth for one interaction.

Tracked state:
- `query`: Original user query.
- `parsed`: Extracted `description`, `size`, and `max_price`.
- `search_results`: List returned by `search_listings`.
- `selected_item`: Top listing from `search_results`.
- `wardrobe`: Wardrobe dict selected in the UI.
- `outfit_suggestion`: String returned by `suggest_outfit`.
- `fit_card`: String returned by `create_fit_card`.
- `price_assessment`: Dict returned by `compare_price`.
- `trend_info`: Dict returned by `check_trends`.
- `style_profile`: Preferences loaded and updated from `.fitfindr_style_profile.json`.
- `retry_attempts`: Fallback searches attempted after zero exact matches.
- `retry_message`: User-facing explanation when fallback search succeeds.
- `error`: A message explaining why the workflow stopped early.

State flow:
- The top result from `search_listings` is stored as `selected_item`.
- That same `selected_item` dict is passed into `compare_price` and then into `suggest_outfit`.
- The returned `outfit_suggestion` string is passed into `create_fit_card`.
- `create_fit_card` also receives the same `selected_item`, so the caption matches the exact listing that was searched.
- Style memory and trend context are attached to the wardrobe copy passed into `suggest_outfit`, without mutating the original wardrobe.

The test `test_planning_walkthrough_query_preserves_state_between_tool_calls` prints `session["selected_item"]` and `session["outfit_suggestion"]`, then asserts those exact values are passed into the next tool calls.

## Error Handling

| Tool or feature | Failure mode | Agent/tool response | Tested example |
|---|---|---|---|
| `search_listings` | Empty description | Returns `[]`; the agent stops with an error asking for an item description. | `test_returns_empty_list_for_invalid_inputs` |
| `search_listings` | No exact match | Agent retries with loosened constraints before giving up. | `test_retry_logic_removes_size_filter_and_continues_workflow` |
| `search_listings` | No match after fallback | Agent tells the user what failed and what to broaden; later tools are not called. | `test_no_search_results_stops_before_outfit_and_fit_card` |
| `search_listings` | Listings cannot load | Returns `[]` instead of crashing. | `test_returns_empty_list_when_listings_cannot_load` |
| `suggest_outfit` | Empty wardrobe | Calls the LLM with a general styling prompt rather than crashing. | `test_empty_wardrobe_calls_llm_for_general_styling` |
| `suggest_outfit` | Missing or incomplete `new_item` | Returns an actionable error string and does not call Groq. | `test_missing_new_item_returns_actionable_error_without_llm_call`, `test_incomplete_new_item_returns_missing_fields_without_llm_call` |
| `suggest_outfit` | LLM/API failure | Returns `"I couldn't generate an outfit suggestion right now. Check your GROQ_API_KEY and try again."` | `test_llm_failure_returns_actionable_error` |
| `create_fit_card` | Empty outfit string | Returns `"I need an outfit suggestion before I can create a fit card."` | `test_empty_outfit_returns_error_without_llm_call` |
| `create_fit_card` | Missing item details | Returns an error listing the missing fields. | `test_incomplete_new_item_returns_missing_fields_without_llm_call` |
| `create_fit_card` | LLM/API failure or malformed response | Returns an actionable error string instead of crashing. | `test_llm_failure_returns_actionable_error`, `test_malformed_llm_response_returns_actionable_error` |
| `compare_price` | Missing price or no comparables | Returns `assessment: "unknown"` with a reason instead of crashing. | `test_compare_price_returns_assessment_with_dataset_comparables` |
| `check_trends` | Trend snapshot unavailable | Returns empty trend context and explains that styling will rely on item and wardrobe only. | Covered by implementation guard; happy path in `test_check_trends_returns_matching_trend_context_for_graphic_tee` |
| Style profile memory | Memory file missing or malformed | Starts with an empty profile and continues. Save failures are ignored so the app still works. | `test_style_profile_memory_persists_across_sessions` |

Concrete failure example: the query `"designer ballgown size XXS under $5"` deliberately returns no matching listings. The agent retries by removing size and price constraints, then responds with a specific error telling the user to broaden the description, size, or budget. It does not call `suggest_outfit` or `create_fit_card`.

## Complete Interaction Example

Example query from `planning.md`:

```text
I'm looking for a vintage graphic tee under $30, size M. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?
```

Expected flow:

1. The agent parses:
   - `description`: `"vintage graphic tee"`
   - `size`: `"M"`
   - `max_price`: `30.0`
2. Style memory records preferences like `baggy`, `chunky`, `streetwear`, and `vintage`.
3. `search_listings` returns matching listings and the agent stores the first result as `selected_item`.
4. `compare_price` assesses whether the selected item is a good deal, fair price, or priced high.
5. `check_trends` returns trend context for graphic tees, baggy denim, and chunky sneakers.
6. `suggest_outfit` receives the exact selected item plus the wardrobe, style memory, and trend context.
7. `create_fit_card` receives the outfit suggestion and the same selected item.
8. The UI displays the listing summary, stretch notes, outfit suggestion, and fit card.

## Stretch Features Implemented

### Price Comparison Tool

Implemented as `compare_price(item, listings=None)`.

The tool compares the selected listing against dataset listings in the same category. It prioritizes comparables with overlapping style tags or colors, then falls back to same-category listings if the filtered group is too small. The UI displays the assessment and reasoning in the first output panel.

### Style Profile Memory

Implemented with `load_style_profile()`, `save_style_profile()`, and `update_style_profile()` in `agent.py`.

The agent extracts style terms from the query and wardrobe, stores them in `.fitfindr_style_profile.json`, and uses them in later sessions without asking the user to re-enter preferences. The file is ignored by git because it is local runtime memory.

### Trend Awareness Tool

Implemented as `check_trends(description, size=None)`.

The tool reads `data/trends.json`, which is an offline classroom trend snapshot adapted from public fashion tag patterns on Depop Explore, Pinterest Trends, and TikTok outfit hashtags. The matched trend influence is passed into `suggest_outfit`, and tests confirm the prompt includes that trend context.

### Retry Logic With Fallback

Implemented in `_retry_search_with_fallbacks(session)`.

If exact search returns zero results, the agent automatically retries by removing the size filter first, then removing the price cap if needed. When a retry succeeds, the UI tells the user exactly what was adjusted. When every retry fails, the error message includes the fallback attempts.

## Testing

Run all tests:

```bash
pytest tests/
```

Current coverage includes:
- Tool behavior and failure cases for all three required tools.
- LLM calls mocked so tests do not require network access.
- Fit-card variation behavior with repeated same-input calls.
- Agent planning-loop integration tests showing success, retry-success, and no-results paths behave differently.
- Stretch tests for price comparison, style memory, trend awareness, and retry fallback.
- UI handler tests for mapping session fields and stretch notes into Gradio output panels.

Current result:

```text
37 passed
```

## AI Usage

I used AI tools during implementation, but reviewed and changed the generated code before keeping it.

### Instance 1: Tool implementation help

Input given to AI:
- The `planning.md` Tool Inventory sections for `search_listings`, `suggest_outfit`, and `create_fit_card`.
- The `utils/data_loader.py` helper description, especially the requirement to use `load_listings()` instead of re-implementing file loading.
- The dataset fields from `data/listings.json` and wardrobe item fields from `data/wardrobe_schema.json`.

What the AI helped produce:
- Initial implementation structure for the three tool functions.
- Keyword matching and filtering logic for `search_listings`.
- Groq prompt structure for `suggest_outfit` and `create_fit_card`.
- Guard clauses for empty search results, empty wardrobes, empty outfit strings, and incomplete item dictionaries.

What I reviewed, revised, or overrode:
- I kept `search_listings` deterministic instead of using an LLM, because search should be testable and repeatable.
- I added explicit helper docstrings for the nested search helper functions.
- I added `FIT_CARD_TEMPERATURE = 1.0` after the spec required varied fit-card outputs.
- I added response parsing guards for malformed Groq responses so LLM failures return user-facing error strings instead of crashing.

### Instance 2: Planning loop and state-flow tests

Input given to AI:
- The `planning.md` Planning Loop, State Management, Error Handling, and architecture diagram.
- The numbered TODO steps inside `agent.py`.
- The rubric note that the agent must respond differently to different inputs and must not call all three tools unconditionally.

What the AI helped produce:
- The `run_agent()` implementation that stores `parsed`, `search_results`, `selected_item`, `outfit_suggestion`, `fit_card`, and `error` in the session dictionary.
- Integration tests that mock the three tools and verify the happy path, no-results path, and planning walkthrough path.

What I reviewed, revised, or overrode:
- I chose a deterministic regex parser for `description`, `size`, and `max_price` instead of asking an LLM to parse the query.
- I tightened the integration tests to assert exact parsed arguments passed into `search_listings`.
- I added the walkthrough test that prints `session["selected_item"]` and `session["outfit_suggestion"]`, then confirms those exact values flow into the next tool calls.

### Instance 3: Stretch feature implementation

Input given to AI:
- The stretch feature rubric for price comparison, style profile memory, trend awareness, and retry fallback.
- The existing `agent.py`, `tools.py`, and app output structure.
- The requirement that stretch behavior should be visible in the demo and covered by tests.

What the AI helped produce:
- `compare_price()`, `check_trends()`, style memory helpers, and retry fallback logic.
- Tests for retry behavior, style memory across sessions, trend context in the LLM prompt, and price assessment output.
- README sections explaining how each stretch feature works.

What I reviewed, revised, or overrode:
- I used a local `data/trends.json` snapshot instead of live scraping so the demo and tests are deterministic.
- I made retry fallback conservative: remove size first, then remove price cap only if needed.
- I surfaced stretch notes in the app's listing panel so the video can show them without opening code.

## Spec Reflection

One way the spec helped: requiring named function signatures and clear return values made the implementation easier to test in isolation. `search_listings`, `suggest_outfit`, and `create_fit_card` each have focused tests before being wired together through `run_agent`.

One divergence from the initial plan: the query parser in `run_agent` is deterministic regex/string logic instead of an LLM parser. This keeps tests predictable and avoids spending LLM calls before the user has even selected an item. The LLM is reserved for the two places where generation is actually useful: styling and fit-card captions.

Another useful spec constraint was the adaptive planning loop. The integration tests now check that the agent stops after a failed search instead of blindly calling every tool, which directly protects the core agent behavior required by the rubric.
