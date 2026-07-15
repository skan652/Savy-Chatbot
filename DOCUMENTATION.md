# SAVY Tax Assistant — Code Documentation

A Flask-based conversational chatbot that walks users through a UK tax
refund/savings eligibility assessment, persists answers to an in-memory
session store, syncs progress to an external **Savy API**, and optionally
generates an AI summary of the results. The app also ships a
Swagger/OpenAPI UI (via `flasgger`) for its own REST endpoints.

---

## Table of Contents

1. [Overview & Tech Stack](#1-overview--tech-stack)
2. [Configuration & Environment](#2-configuration--environment)
3. [Swagger Documentation & Auth Protection](#3-swagger-documentation--auth-protection)
4. [App-Level Auth (Login & Passkey)](#4-app-level-auth-login--passkey)
5. [Conversation Storage](#5-conversation-storage)
6. [Savy External API Client](#6-savy-external-api-client)
7. [Question Definitions (the assessment "script")](#7-question-definitions-the-assessment-script)
8. [Flask Session State](#8-flask-session-state)
9. [Conversation Engine (question flow logic)](#9-conversation-engine-question-flow-logic)
10. [Helper / Formatting Functions](#10-helper--formatting-functions)
11. [Assessment Completion & AI Summary](#11-assessment-completion--ai-summary)
12. [Flask Routes — Pages](#12-flask-routes--pages)
13. [Flask Routes — Conversation API](#13-flask-routes--conversation-api)
14. [Flask Routes — Chat Engine API](#14-flask-routes--chat-engine-api)
15. [Flask Routes — Savy Proxy API](#15-flask-routes--savy-proxy-api)
16. [Frontend Chat UI](#16-frontend-chat-ui)
17. [Known Issues & Recommendations](#17-known-issues--recommendations)

---

## 1. Overview & Tech Stack

| Concern | Library / Tool |
|---|---|
| Web framework | `Flask` |
| API docs | `flasgger` (Swagger UI, `swag_from` decorators) |
| Basic auth for Swagger | `flask_httpauth.HTTPBasicAuth` |
| Password hashing | `werkzeug.security` |
| External tax API | `requests` (custom wrapper) |
| AI summary generation | Custom `ai_client.AIClient` (OpenAI/Gemini) |
| Question flow / branching | Custom `state_machine.StateMachineEngine` (loads `response.json`) |
| Session persistence | Flask server-side session (`filesystem`, 1 hour lifetime) |
| Tunneling (dev) | `pyngrok` (imported but not directly wired into a route in this file) |

**High-level flow:**

1. User authenticates against the Savy API (email/password) → app stores a JWT bearer token.
2. User enters a **passkey** (a second, simpler gate) to reach the chat UI.
3. User says "Hello" → bot greets them and explains the two phases.
4. User says "OK" → bot begins asking questions defined in `get_questions_list()`.
5. Each answer is scored via a state machine / handler map to decide the next question ref, and is pushed in real time to the Savy API as a refund estimation and a tax estimation.
6. When the flow reaches a terminal state, `complete_assessment()` builds a summary (optionally AI-generated) and posts final data back to Savy.

---

## 2. Configuration & Environment

```python
dotenv_path = os.path.join(os.getcwd(), ".env")
```

- A **hand-rolled `.env` loader** runs before `ai_client` is imported, so environment variables are available to it at import time. It skips keys already present in `os.environ` (i.e., real env vars take precedence over `.env` file values).
- `USE_AI` defaults to `"true"` if not already set.
- Flask app config:
  - `app.secret_key` — **hardcoded** (`"savy-chatbot-secret-key"`) — see [Known Issues](#17-known-issues--recommendations).
  - `SESSION_TYPE = 'filesystem'`, `SESSION_PERMANENT = True`, 1-hour (`3600`s) lifetime.

Relevant environment variables consumed elsewhere in the file:

| Variable | Purpose | Default |
|---|---|---|
| `SAVY_API_BASE_URL` | Base URL for the external Savy API | `https://api.savyapp.dev` |
| `SAVY_TOKEN` | Bearer token for Savy API calls (written back to `.env` after login) | — |
| `SAVY_USER_ID` | Authenticated Savy user ID | — |
| `USE_AI` | Toggles AI summary generation | `"true"` |
| `AI_PROVIDER` | `"gemini"`/`"google"` or `"openai"`/`"chatgpt"` | `"gemini"` |
| `GOOGLE_API_KEY` / `GOOGLE_API_TOKEN` | Gemini credentials | — |

---

## 3. Swagger Documentation & Auth Protection

```python
SWAGGER_USERS = {"admin": generate_password_hash("savypass123"),
                  "demo":  generate_password_hash("demopass123")}
auth = HTTPBasicAuth()
```

- `app.config['SWAGGER']` defines title, description, contact info, license, tag groupings (`Authentication`, `Chat`, `Estimations`, `Questions`, `Conversations`), a `BearerAuth` security scheme, and CDN URLs for the Swagger UI assets.
- `swagger = Swagger(app)` initializes flasgger, exposing `/apidocs/` and `/apispec.json`.
- **`protect_swagger()`** (`@app.before_request`) intercepts any request to `/apidocs*`, `/swagger_spec`, or `/apispec.json` and requires an `Authorization` header, otherwise it triggers HTTP Basic Auth. Requests to `/flasgger_static/` are always allowed through (needed to serve the UI's CSS/JS).
- **`/apidocs/login`** is a custom HTML login page (GET shows the form, POST validates credentials against `SWAGGER_USERS` and sets `session['swagger_authenticated']`).
- **`/apidocs/redirect`** bounces to the real `/apidocs/` once `swagger_authenticated` is set.
- **`protected_apidocs()`** and **`protected_swagger_spec()`** wrap the actual Swagger UI/spec routes with `@auth.login_required` (HTTP Basic Auth), which is a *second*, independent auth mechanism from the custom login page above — the two are somewhat redundant.

> Note: default Swagger credentials (`admin` / `savypass123`, `demo` / `demopass123`) are printed directly in the Swagger description and the login page HTML.

---

## 4. App-Level Auth (Login & Passkey)

The main app (not Swagger) uses a **two-step gate**:

1. **Savy login** (`/login`) — email + password, verified against the real Savy API via `authenticate_savy_user()`. Sets `session['savy_authenticated']` and `session['savy_user_id']`.
2. **Passkey** (`/passkey`) — a simple shared-secret gate:

```python
VALID_PASSKEYS = ["12345", "pass123"]
```

   Sets `session['passkey_verified']`.

The `before_request()` global hook enforces this order for every route not in an `allowed_routes` allow-list (static assets, passkey/login pages, conversation API, Swagger, etc.):

```python
if not session.get("savy_authenticated") and not SAVY_USER_ID:
    return redirect(url_for("login_page"))
if not session.get("passkey_verified"):
    return redirect(url_for("passkey_page"))
```

> Note: `VALID_PASSKEYS` are plaintext, short, and hardcoded — see [Known Issues](#17-known-issues--recommendations).

---

## 5. Conversation Storage

An **in-memory dictionary** (`conversations = {}`) doubles as the datastore for chat history — explicitly noted in the code as a placeholder for a real database.

| Function | Purpose |
|---|---|
| `get_conversation_id()` | Generates an 8-character UUID-based ID |
| `save_conversation(...)` | Upserts a conversation record (messages, answers, history, phase, completion, title, folder) |
| `get_conversation(id)` | Fetch one conversation |
| `get_all_conversations()` | Returns conversations grouped into `Today` / `Yesterday` / `Previous 7 Days` / `Older`, sorted newest-first |
| `generate_conversation_title(...)` | Builds a human-readable title like `"Inquiry #3 - Income: £14k-£50k"` by inspecting specific known question refs (income, travel, mileage, etc.) |
| `categorize_conversation()` | Buckets a conversation into a date folder (note: currently always evaluates to "Today" since it compares `datetime.now()` to itself — see [Known Issues](#17-known-issues--recommendations)) |

---

## 6. Savy External API Client

A thin `requests`-based wrapper around the external Savy REST API.

```python
SAVY_API_BASE_URL = os.environ.get("SAVY_API_BASE_URL", "https://api.savyapp.dev")
```

### Core request helper

- **`get_savy_headers()`** — builds `Content-Type`/`Accept` JSON headers, adding `Authorization: Bearer <SAVY_TOKEN>` if a token is present.
- **`make_savy_request(endpoint, method, data, params)`** — dispatches `GET`/`POST`/`PATCH`/`PUT`/`DELETE` via `requests`, with a 30s timeout, structured logging, and specific handling of `401` (returns an error dict rather than raising).

### Authentication (Step 1)

- **`authenticate_savy_user(email, password)`** — `POST /api/v1/auth/email/login`. On success:
  - Extracts a token from several possible response keys (`token`, `accessToken`, `access_token`).
  - Extracts a user ID similarly (`userId`, nested `user.id`, or `id`).
  - **Persists the token/user ID back into the `.env` file on disk** (rewriting the whole file) and into `os.environ` / module-level globals, so subsequent process restarts can reuse the token.

### Refund Estimations

- `initiate_refund_estimation()` — `POST /api/v1/refund-estimations` (empty body); stores the returned ID in `session["refund_estimation_id"]`.
- `update_refund_estimation(estimation_id, answer_data)` — `PATCH /api/v1/refund-estimations/{id}`.

### Tax Estimations (Steps 2–3)

- `initiate_tax_estimation()` — `POST /api/v1/estimations` with `{userId, startDate}`; requires a known `SAVY_USER_ID`/session user ID. Stores ID in `session["tax_estimation_id"]`.
- `update_tax_estimation(estimation_id, answer_data)` — `PATCH /api/v1/estimations/{id}`.
- `get_tax_estimation(estimation_id)` — `GET /api/v1/estimations/{id}`.
- `get_all_tax_estimations()` — `GET /api/v1/estimations`.
- `delete_tax_estimation(estimation_id)` — `DELETE /api/v1/estimations/{id}`.

All of the above return a consistent `{"success": bool, "data"/"error": ..., "estimation_id": ...}` shape, and are wrapped in `try/except` with logging.

---

## 7. Question Definitions (the assessment "script")

`get_questions_list()` returns a hardcoded, **ordered list of question dicts** (`ref` "1" through "15") mirroring an original TypeScript question set. `QUESTIONS` and `QUESTION_MAP` (`ref → question`) are built once at module load.

### Common fields per question

| Field | Meaning |
|---|---|
| `ref` | Unique string ID used for branching/history |
| `progress` | 0–100 progress-bar percentage |
| `title` | Question text; can be a **plain string or a callable** `fn(answers) -> str` for dynamic phrasing (e.g., Q12 interpolates the spend-per-day answer) |
| `type` | UI input type: `radiov2`, `radio`, `numeric`, `counter`, `price`, etc. |
| `field_name` | Logical name sent to the Savy API |
| `options` | Choice labels (for radio types) |
| `required` | Whether an answer is mandatory |
| `infoTitle` / `info` | Optional help text shown under the question |
| `placeholder` | Example input text |
| `value` | Runtime-populated answer holder (starts `""`) |
| `handlerNext` | Static map of `{answer_option: {action, ref, params}}` describing branching |
| `dynamiqyeHandlerNext` | *(sic — typo preserved from source)* A **callable** branching function used where the next step depends on more than just the raw answer (e.g., whether `annualSaving > 200`) |
| `xhrParams` | Callable that converts the raw answer into the payload fields sent to the Savy API (handles unit conversion, e.g. pence → pounds, string → float) |
| `proposal` | Optional sub-question(s) triggered by a specific answer (e.g., choosing "Mileage rate" pops up a rate-entry question) |

### Question map (phase 1 = Refund Assessment, phase 2 = Savings Assessment)

```python
PHASE_1_QUESTIONS = ["1", "2", "3", "4", "5", "6", "7", "8"]
PHASE_2_QUESTIONS = ["9", "10", "11", "12", "13", "14", "15"]
PHASE_NAMES = {1: "🔍 Refund Assessment", 2: "💰 Savings Assessment"}
```

| Ref | Topic | Branches on |
|---|---|---|
| 1 | Annual income band | Income tier |
| 2 | Do you travel for work? | Yes/No |
| 3 | How do you make work journeys? | Own vehicle / company vehicle / train |
| 4 | Annual mileage | (numeric, no branch) |
| 5 | How mileage expenses are reimbursed | Mileage rate / fuel card / none (with a `proposal` sub-question for the rate) |
| 6 | Type of work journeys | Multiple places / same place |
| 7 | Is workplace temporary? | Yes/No |
| 8 | Buy food/drink while travelling? | Yes/No — **dynamic** branch based on calculated `annualSaving` |
| 9 | Days travelled per week | (numeric) |
| 10 | Average spend per day | (price) |
| 11 | Employer food/drink reimbursement | 4 options — **dynamic** branch based on `annualSaving` |
| 12 | How much employer reimburses | (price; dynamic title interpolating Q10's answer) |
| 13 | Earned > £14k in last 4 tax years? | No → terminates with an error state |
| 14 | Other income sources? | (terminal, no branch defined here) |
| 15 | Monthly commuting spend | (terminal) |

---

## 8. Flask Session State

`init_session()` runs on every request (via `before_request`) and seeds any missing session keys with defaults, including: `messages`, `answers`, `current_ref`, `passkey_verified`, `waiting_for_answer`, `completed`, `history`, `pending_proposal`, `phase`, `phase_transition_shown`, `awaiting_greeting`, `awaiting_ok`, `error_count`, `estimation_data`, `sidebar_open`, the various `*_estimation_id` / `*_initiated` flags, `savy_authenticated`, `savy_user_id`, and `conversation_id`.

If session initialization itself throws, the handler **clears the whole session and retries** (`session.clear(); init_session()`), rather than propagating the error.

`calculate_annual_saving(answers)` reproduces the frontend's estimation formula:

```python
annual_saving = (spend_per_day - reimbursed_per_day) * days_per_week * 48
```

(48 assumed working weeks/year), pulling `9`/`10`/`12` from the answers dict.

---

## 9. Conversation Engine (question flow logic)

This is the heart of the bot — it decides, after each answer, what question comes next (or whether the assessment is complete).

### `evaluate_dynamic_handler(question, answer, all_answers)`
- Only runs if the question defines `dynamiqyeHandlerNext`.
- Refreshes `session["estimation_data"]["annualSaving"]` via `calculate_annual_saving()`.
- Calls the handler with either 1 or 2 arguments depending on its signature (introspected via `inspect.signature`), then maps its returned `action` (`open_question`, `navigate_to_screen`, `to_save_and_finish`, `to_save_and_finish_with_error`) to a `{status, next_ref, completed}` result.

### `process_handler_next(current_ref, answer)`
Resolution order for "what's next":
1. Ask the external **`StateMachineEngine`** (`state_engine.get_next_question_ref`) first — this is presumably the canonical source of truth loaded from `response.json`.
2. If that doesn't resolve, fall back to `evaluate_dynamic_handler()`.
3. If still unresolved, fall back to the question's static `handlerNext` map — matching the cleaned answer text against option keys (exact match first, then substring match, both after stripping newlines/whitespace).
4. Defaults to `{"status": "completed"}` if nothing matches.

### `get_next_question_in_phase(current_ref)`
A simpler variant used elsewhere: if the current question has no recorded answer yet, re-serves it; otherwise defers entirely to `state_engine.get_next_question_ref`.

### `handle_proposal(current_ref, answer)`
If the current question has a `proposal` map and the given answer matches one of its keys, stores a `session["pending_proposal"]` record (original ref, chosen answer, the sub-questions to ask, and a running index) and returns those sub-questions so the caller can start asking them.

### `process_next_question()`
Central dispatcher that decides what message to send next:
1. If `completed` — no-op.
2. If there's a `pending_proposal` with unanswered sub-questions — serve the next sub-question.
3. Otherwise — serve `session["current_ref"]`'s question (or complete the assessment if the ref doesn't resolve to a real question).

### `show_phase_transition()`
Sends a one-time transition message when moving from phase 1 → phase 2, guarded by `session["phase_transition_shown"]`.

### `run_xhr_params(question, answer, current_ref)`
Executes the question's `xhrParams` callable (1- or 2-arg, introspected like the dynamic handler) and merges its result dict into `session["estimation_data"]`, which is what ultimately gets sent to Savy.

---

## 10. Helper / Formatting Functions

| Function | Purpose |
|---|---|
| `get_question(ref)` | Looks up a question by ref, resolving a callable `title` against current answers |
| `clean_number(value)` | Strips currency symbols (`£€$,`) and non-numeric characters from user input |
| `get_question_text(question)` | Builds the full chat message text: title + optional subtitle/info/placeholder, formatted with emoji markers |
| `get_options(question)` | Returns cleaned option labels for choice-type questions, else `None` |
| `get_question_type(question)` | Maps internal `type` values to a simplified UI type: `choice`, `numeric`, or `text` |
| `add_message(role, content, options, input_type)` | Appends a message to `session["messages"]`, persists the conversation via `save_conversation()`, and caps history at the last 100 messages |
| `format_answer_for_display(question, answer)` | Formats an answer for the sidebar (e.g., prefixes `£` and 2-decimal formatting for `price`/`numeric` types) |

---

## 11. Assessment Completion & AI Summary

`complete_assessment()` is the terminal step of the flow:

1. Marks `session["completed"] = True`.
2. Builds a plain-text summary of all Q&A pairs.
3. Checks whether AI generation is enabled (`USE_AI` truthy) **and** the configured provider (`gemini`/`google` or `openai`/`chatgpt`) has credentials present.
4. Shows a temporary "AI Assistant is analyzing…" message, then (if enabled) calls `ai_client.generate(prompt=plain_summary, system_prompt=..., max_tokens=500, temperature=0.7)`, with a small artificial `time.sleep(0.8)` before the call and extensive logging of inputs/outputs.
5. Removes the temporary "analyzing" message once done.
6. **Falls back to a manually constructed summary** (bulleted list of the first 10 answers, +"and N more") if AI generation is disabled, unconfigured, or returns nothing.
7. Sends the full answer set + summary to Savy via `send_to_savy()` (`POST /api/v1/refund-estimations`).
8. If a tax estimation was initiated, `PATCH`es it with final answers, estimation data, AI summary, and `status: "completed"`.
9. Builds and appends a rich final chat message: full Q&A recap, the AI/summary block, and a "next steps" note.
10. Persists the completed conversation via `save_conversation()`.

`send_to_savy(answers, phase, phase_name, ai_summary)` packages answers (with resolved question titles/types) plus the AI summary and posts to `/api/v1/refund-estimations`, storing the returned `savy_estimation_id` in session.

---

## 12. Flask Routes — Pages

| Route | Methods | Purpose |
|---|---|---|
| `/` | GET | Redirects to login → passkey → chat, in that order of precedence |
| `/api/docs` | GET | Redirects to `/apidocs/` |
| `/start_new_assessment` | GET | Clears the session and redirects to the passkey page |
| `/login` | GET, POST | Savy email/password login form; on success sets `savy_authenticated` |
| `/api/auth/email/login` | POST | JSON API equivalent of `/login`, documented in Swagger under **Authentication** |
| `/passkey` | GET | Renders the passkey entry screen (SVG "SAVY" logo, styled form) |
| `/verify_passkey` | POST | Validates the submitted passkey against `VALID_PASSKEYS` |
| `/chat` | GET | Main chat UI. On first visit (if not completed) it lazily initiates both the refund estimation and the tax estimation against Savy, then renders the full HTML/CSS/JS single-page chat interface inline via `render_template_string` |
| `/toggle_sidebar` | POST | Flips `session["sidebar_open"]` |
| `/edit_answer` | POST | Rewinds the conversation to a previously answered question: removes that question and everything after it from `answers`/`history`, resets phase/completion flags, truncates the message log back to just before that question was asked, and re-serves it |
| `/restart_chat` | POST | Clears the entire session and reinitializes it |

Both `/login` and `/passkey` render large inline HTML/CSS forms via `render_template_string` (SAVY pink branding, gradient buttons, responsive layout) rather than separate template files.

---

## 13. Flask Routes — Conversation API

All under the `Conversations` Swagger tag; operate on the in-memory `conversations` dict.

| Route | Methods | Purpose |
|---|---|---|
| `/api/conversations` | GET | Returns all conversations grouped into date folders |
| `/api/conversation/<id>` | GET | Loads one conversation **into the current session** (messages, answers, history, phase, completed) and returns it |
| `/api/conversation/<id>` | DELETE | Deletes a conversation from the in-memory store |
| `/api/conversation/new` | POST | Resets session state for a brand-new conversation and returns its generated ID |

---

## 14. Flask Routes — Chat Engine API

| Route | Methods | Purpose |
|---|---|---|
| `/send_message` | POST | The core conversational endpoint (documented in Swagger under **Chat**) |

### `/send_message` behavior

Given `{"answer": "<user text>"}`, in order:

1. If already `completed` → returns `{"status": "completed"}` immediately.
2. If `awaiting_greeting` → only accepts a greeting ("hello"/"hi"/etc.); on success sends the welcome message and flips to `awaiting_ok`.
3. If `awaiting_ok` → only accepts an affirmative ("ok"/"okay"/"sure"/"ready"/"yes"); on success calls `process_next_question()` to start Q1.
4. If not `waiting_for_answer` → returns an error (nothing pending to answer).
5. If a **pending proposal** exists → validates/stores the sub-answer, advances the proposal index, and either serves the next sub-question or resolves the original question's `handlerNext`/state machine once all sub-questions are answered.
6. Otherwise, standard flow:
   - Validates numeric input types via `clean_number()`.
   - Checks whether the answer triggers a `proposal` (sub-question chain).
   - Resolves the next step via `process_handler_next()`.
   - Records the answer into `session["answers"]`/`history`.
   - Runs `xhrParams` to update `estimation_data`.
   - **Pushes the answer in real time** to both the refund estimation and tax estimation endpoints on Savy (separate `PATCH` calls, each wrapped in its own try/except so one failing doesn't block the other).
   - Based on the resolution status, either serves the next question, transitions phases, or calls `complete_assessment()`.

Response shape (per the Swagger schema): `{"status": "success"|"completed"|"phase_complete"|"error", "messages": [...]}` — typically just the newest 1–2 messages, since the frontend appends incrementally rather than re-rendering the full log.

---

## 15. Flask Routes — Savy Proxy API

Under the `Estimations` Swagger tag — these largely expose the internal Savy client functions as REST endpoints (useful for external testing/integration, separate from the automatic real-time syncing that already happens inside `/send_message`).

| Route | Methods | Wraps |
|---|---|---|
| `/api/savy/initiate-refund` | POST | `initiate_refund_estimation()` |
| `/api/savy/update-refund` | POST | `update_refund_estimation()` — builds `answer_data` from the current session |
| `/api/savy/initiate-estimation` | POST | `initiate_tax_estimation()` (requires `savy_authenticated` or a set `SAVY_USER_ID`) |
| `/api/savy/update-estimation` | POST | `update_tax_estimation()` — builds `answer_data` from the current session |
| `/api/savy/get-estimation/<id>` | GET | `get_tax_estimation(id)` |
| `/api/savy/get-all-estimations` | GET | `get_all_tax_estimations()` |
| `/api/savy/delete-estimation/<id>` | DELETE | `delete_tax_estimation(id)` |

All routes are wrapped in `@safe_route`, which catches any unhandled exception and returns a generic `500 {"status": "error", "message": "An unexpected error occurred."}` instead of a stack trace.

---

## 16. Frontend Chat UI

Rendered entirely inline from `/chat` via `render_template_string` — no separate template files or static assets beyond CDN-free inline `<style>`/`<script>`. Key pieces:

- **Sidebar**: SAVY logo, "New Chat" button (→ `/start_new_assessment`), nav item, and a **recent conversations list** fetched client-side from `/api/conversations` and rendered by `renderConversations()`.
- **Message list**: Server-rendered initial messages (Jinja loop over `session["messages"]`) plus client-appended messages from subsequent `/send_message` calls.
- **Typing effect**: `typeMessage()` animates assistant replies character-by-character (~25–40ms/char) after a short "typing dots" indicator, purely cosmetic.
- **AI "thinking" indicator**: Shown while awaiting `/send_message`'s response, and a separate "✨ Generating your summary…" indicator shown specifically around assessment completion.
- **Options rendering**: Choice-type questions render as pill buttons (`option-btn`) that call `sendMessage(option)` directly instead of requiring free-text typing.
- **Editing past answers**: Each sidebar answer entry has an edit affordance that calls `/edit_answer` and reloads the page.
- Responsive breakpoint at `768px` shrinks fonts/padding for mobile.

---

## 17. Known Issues & Recommendations

These are observations about the current implementation, not fixes:

- **Hardcoded secrets**: `app.secret_key`, `SWAGGER_USERS` passwords, and `VALID_PASSKEYS` are all hardcoded in source and printed in-page (Swagger description, login HTML). These should move to environment variables / secrets management before any production use.
- **In-memory data stores**: Both `conversations` and the Flask session's estimation IDs live in process memory (`SESSION_TYPE = 'filesystem'` persists sessions to disk, but `conversations` does not persist at all) — restarting the server loses all conversation history, and it won't scale across multiple worker processes.
- **`.env` file is rewritten on every login**: `authenticate_savy_user()` reads and rewrites the whole `.env` file to persist the token, which is fragile (race conditions with concurrent logins) and stores credentials in plaintext on disk.
- **`categorize_conversation()` is a no-op**: It compares `datetime.now()` against itself (`conv_date = datetime.now()`), so every conversation is always categorized as `"Today"`; it never actually uses the conversation's `last_updated` timestamp.
- **Duplicate/overlapping Swagger auth**: The custom `/apidocs/login` session-based flow and the `@auth.login_required` HTTP Basic Auth on `protected_apidocs()` are two independent mechanisms guarding overlapping paths, which is confusing and only one may actually be enforced depending on request path matching.
- **`dynamiqyeHandlerNext`** appears to be an unintentional typo (likely meant "dynamic handler next") but is preserved as-is since it's a literal dict key relied upon elsewhere in the code.
- **No CSRF protection** is visible on any of the POST endpoints (login, passkey, send_message, edit_answer, etc.).
- **Broad exception handling**: Most functions catch `Exception` broadly and log + return a generic error/fallback, which aids resilience but can mask real bugs (e.g., a malformed Savy response silently becomes `{"status": "completed"}`).
