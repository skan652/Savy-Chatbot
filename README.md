# Savy-Chatbot

A state machine engine for handling dynamic questionnaires based on JSON configuration, integrated with a web-based chatbot interface.

## Files

- `response.json`: JSON configuration defining the questionnaire fields, types, conditions, and validations.
- `state_machine.py`: The StateMachineEngine class that processes the questionnaire.
- `main.py`: Example script to run the questionnaire interactively.
- `app.py`: Flask web application providing a chat interface for the questionnaire.

## Usage

### Web Chatbot

Run the web application:

```bash
py -3 app.py
```

Then open your browser to `http://127.0.0.1:5000/` to interact with the chatbot.

### Console Version

Run the example:

```bash
py -3 main.py
```

The engine will guide through the questions, skipping conditional ones based on previous answers.
