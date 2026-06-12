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

Purpose: Searches `data/listings.json` for secondhand items matching the user's requested item, optional size, and optional budget.

Inputs:
- `description` (`str`): Search keywords, such as `"vintage graphic tee"`.
- `size` (`str | None`): Optional size filter, such as `"M"`, `"S/M"`, `"W30"`, or `"US 8"`.
- `max_price` (`float | None`): Optional maximum item price.

Output:
- `list[dict]`: Matching listing dictionaries sorted by relevance and then price. Each listing includes `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`.
- Returns `[]` when there are no matches or the search input cannot be used safely.

### `suggest_outfit(new_item, wardrobe)`

Purpose: Uses Groq `llama-3.3-70b-versatile` to suggest one or two complete outfits for the selected listing.

Inputs:
- `new_item` (`dict`): The selected listing from `search_listings`; expected fields include `title`, `category`, `style_tags`, `colors`, `price`, and `platform`.
- `wardrobe` (`dict`): A wardrobe object with an `items` list. Each wardrobe item can include `id`, `name`, `category`, `colors`, `style_tags`, and `notes`.

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
- Uses `FIT_CARD_TEMPERATURE = 1.0` so repeated calls can produce different wording.
- Returns a clear error string if `outfit` is empty, item details are missing, or the LLM call fails.

## Planning Loop

`run_agent(query, wardrobe)` in `agent.py` is the planning loop. It does not call all tools unconditionally.

The loop follows this conditional flow:

1. Create a session dictionary with `_new_session(query, wardrobe)`.
2. Parse the natural language query into `description`, `size`, and `max_price`.
3. If no usable description is found, set `session["error"]` and stop before calling tools.
4. Call `search_listings(description, size, max_price)`.
5. If search returns `[]`, set a specific no-results error and stop. The agent does not call `suggest_outfit` or `create_fit_card`.
6. If search returns results, store the top result as `session["selected_item"]`.
7. Call `suggest_outfit(session["selected_item"], session["wardrobe"])`.
8. If the outfit tool returns an error-like string, store that in `session["error"]` and stop.
9. Call `create_fit_card(session["outfit_suggestion"], session["selected_item"])`.
10. If the fit-card tool succeeds, return the completed session with `fit_card` populated.

This means a successful query and a no-results query take different paths. The integration tests verify that `designer ballgown size XXS under $5` stops after search, while a valid query continues through all three tools.

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
- `error`: A message explaining why the workflow stopped early.

State flow:
- The top result from `search_listings` is stored as `selected_item`.
- That same `selected_item` dict is passed into `suggest_outfit`.
- The returned `outfit_suggestion` string is passed into `create_fit_card`.
- `create_fit_card` also receives the same `selected_item`, so the caption matches the exact listing that was searched.

The test `test_planning_walkthrough_query_preserves_state_between_tool_calls` prints `session["selected_item"]` and `session["outfit_suggestion"]`, then asserts those exact values are passed into the next tool calls.

## Error Handling

| Tool | Failure mode | Agent/tool response | Tested example |
|------|--------------|---------------------|----------------|
| `search_listings` | Empty description | Returns `[]`; the agent stops with an error asking for an item description. | `test_returns_empty_list_for_invalid_inputs` |
| `search_listings` | No matching listing | Returns `[]`; the agent tells the user to broaden description, size, or budget and does not call later tools. | `test_no_search_results_stops_before_outfit_and_fit_card` |
| `search_listings` | Listings cannot load | Returns `[]` instead of crashing. | `test_returns_empty_list_when_listings_cannot_load` |
| `suggest_outfit` | Empty wardrobe | Calls the LLM with a general styling prompt rather than crashing. | `test_empty_wardrobe_calls_llm_for_general_styling` |
| `suggest_outfit` | Missing or incomplete `new_item` | Returns an actionable error string and does not call Groq. | `test_missing_new_item_returns_actionable_error_without_llm_call`, `test_incomplete_new_item_returns_missing_fields_without_llm_call` |
| `suggest_outfit` | LLM/API failure | Returns `"I couldn't generate an outfit suggestion right now. Check your GROQ_API_KEY and try again."` | `test_llm_failure_returns_actionable_error` |
| `create_fit_card` | Empty outfit string | Returns `"I need an outfit suggestion before I can create a fit card."` | `test_empty_outfit_returns_error_without_llm_call` |
| `create_fit_card` | Missing item details | Returns an error listing the missing fields. | `test_incomplete_new_item_returns_missing_fields_without_llm_call` |
| `create_fit_card` | LLM/API failure or malformed response | Returns an actionable error string instead of crashing. | `test_llm_failure_returns_actionable_error`, `test_malformed_llm_response_returns_actionable_error` |

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
2. `search_listings` returns matching listings and the agent stores the first result as `selected_item`.
3. `suggest_outfit` receives that exact selected item plus the wardrobe.
4. `create_fit_card` receives the outfit suggestion and the same selected item.
5. The UI displays the listing summary, outfit suggestion, and fit card in three panels.

## Testing

Run all tests:

```bash
pytest tests/
```

Current coverage includes:
- Tool behavior and failure cases for all three required tools.
- LLM calls mocked so tests do not require network access.
- Fit-card variation behavior with repeated same-input calls.
- Agent planning-loop integration tests showing success and no-results paths behave differently.
- UI handler tests for mapping session fields into Gradio output panels.

## Spec Reflection

One way the spec helped: requiring named function signatures and clear return values made the implementation easier to test in isolation. `search_listings`, `suggest_outfit`, and `create_fit_card` each have focused tests before being wired together through `run_agent`.

One divergence from the initial plan: the query parser in `run_agent` is deterministic regex/string logic instead of an LLM parser. This keeps tests predictable and avoids spending LLM calls before the user has even selected an item. The LLM is reserved for the two places where generation is actually useful: styling and fit-card captions.

Another useful spec constraint was the adaptive planning loop. The integration tests now check that the agent stops after a failed search instead of blindly calling every tool, which directly protects the core agent behavior required by the rubric.
