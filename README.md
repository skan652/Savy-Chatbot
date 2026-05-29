# Savy-Chatbot

A state machine engine for handling dynamic questionnaires based on JSON configuration, integrated with a web-based chatbot interface featuring MCQ (Multiple Choice Question) format.

## Files

- `response.json`: JSON configuration defining the questionnaire fields, types, conditions, and validations.
- `state_machine.py`: The StateMachineEngine class that processes the questionnaire.
- `main.py`: Example script to run the questionnaire interactively.
- `app.py`: Flask web application providing a chat interface for the questionnaire with MCQ support.

## Features

- **MCQ Format**: All questions are displayed as clickable numbered buttons
- **Session Management**: Each user gets their own independent questionnaire session
- **Dynamic Flow**: Questions are shown/hidden based on previous answers using conditional logic
- **Input Validation**: Automatic validation of answers based on question types
- **Web Interface**: Clean, responsive chat interface
- **State Management**: Maintains conversation state throughout the questionnaire
- **Restart Functionality**: "Start New Questionnaire" button appears after completion to begin again

## Usage

### Web Chatbot

Run the web application:

```bash
py -3 app.py
```

Then open your browser to `http://127.0.0.1:5000/` to interact with the chatbot.

#### ChatGPT Integration

Set `AI_PROVIDER=chatgpt` and provide either `CHATGPT_API_KEY` or `OPENAI_API_KEY`.
You can also optionally set `CHATGPT_MODEL` (default: `gpt-4o-mini`).

Example environment variables:

```bash
set AI_PROVIDER=chatgpt
set CHATGPT_API_KEY=your-key-here
set CHATGPT_MODEL=gpt-4o-mini
```

#### Gemini Integration

Set `AI_PROVIDER=gemini` and provide either `GOOGLE_API_KEY` or `GOOGLE_API_TOKEN`.
You can optionally set `GOOGLE_MODEL` to a supported Gemini model such as `gemini-1.0` or `text-bison-001`.

Example environment variables:

```bash
set AI_PROVIDER=gemini
set GOOGLE_API_KEY=your-google-api-key
set GOOGLE_MODEL=gemini-1.0
```

**Question Types:**
- **Single-choice & Boolean**: Click on the numbered option buttons
- **Numeric with Options**: Click predefined amounts or "Other (specify)" for custom input
- **Numeric (Free-form)**: Type any number in the input field

**Numeric Questions with MCQ Options:**
- **Monthly Salary**: 500, 1000, 2000, 3000, 5000, 10000 + "Other (specify)"
- **Monthly Expenses**: 250, 500, 1000, 1500, 2000, 3000 + "Other (specify)"
- **Government Benefits**: 250, 500, 1000, 1500, 2000, 3000 + "Other (specify)"
- **Business Income**: 500, 1000, 2000, 3000, 5000, 10000 + "Other (specify)"
- **Number of Dependents**: Free-form text input

### Console Testing

Run test files:

```bash
py -3 test_flow.py
py -3 test_flow_smooth.py
```

These scripts test the questionnaire flow and state machine engine.
