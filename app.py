from flask import Flask, request, redirect, url_for, render_template_string, session
from state_machine import StateMachineEngine

app = Flask(__name__)
app.secret_key = 'savy-chatbot-secret-key'

engines = {}

def init_session():
    if '_id' not in session:
        session['_id'] = str(len(engines) + 1)
        session['answers'] = []  # 🔹 store history


def build_engine_from_history():
    """Rebuild engine from stored answers"""
    session_id = session['_id']

    engine = StateMachineEngine('response.json')

    for ans in session.get('answers', []):
        engine.answer_question(ans)

    engines[session_id] = engine
    return engine


def get_engine():
    init_session()
    session_id = session['_id']

    if session_id not in engines:
        return build_engine_from_history()

    return engines[session_id]


# 🔹 Home
@app.route('/')
def index():
    return redirect(url_for('question_page'))


# 🔹 Question Page
@app.route('/question')
def question_page():
    engine = get_engine()
    question = engine.get_current_question()

    if not question:
        return redirect(url_for('completed'))

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Questionnaire</title>
        <style>
            body {
                font-family: Arial;
                background: linear-gradient(135deg, #667eea, #764ba2);
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
            }

            .container {
                background: white;
                padding: 30px;
                border-radius: 15px;
                width: 400px;
                text-align: center;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            }

            h2 {
                margin-bottom: 20px;
            }

            button {
                width: 100%;
                padding: 10px;
                margin: 8px 0;
                border: none;
                border-radius: 8px;
                background: #667eea;
                color: white;
                cursor: pointer;
            }

            button:hover {
                background: #5a67d8;
            }

            .back-btn {
                background: #ccc;
                color: black;
            }

            .back-btn:hover {
                background: #bbb;
            }

            input {
                width: 100%;
                padding: 10px;
                margin-top: 10px;
                border-radius: 8px;
                border: 1px solid #ccc;
            }
        </style>
    </head>
    <body>

        <div class="container">
            <h2>{{ question.question }}</h2>

            <form method="POST" action="/answer">

                {% if question.type == 'single_choice' %}
                    {% for opt in question.options %}
                        <button type="submit" name="answer" value="{{ opt }}">{{ opt }}</button>
                    {% endfor %}

                {% elif question.type == 'boolean' %}
                    <button type="submit" name="answer" value="true">Yes</button>
                    <button type="submit" name="answer" value="false">No</button>

                {% elif question.type == 'number' %}
                    <input type="number" name="answer" required>
                    <button type="submit">Submit</button>

                {% else %}
                    <input type="text" name="answer" required>
                    <button type="submit">Submit</button>

                {% endif %}
            </form>

            {% if session.answers|length > 0 %}
                <form method="POST" action="/back">
                    <button class="back-btn">⬅ Back</button>
                </form>
            {% endif %}
        </div>

    </body>
    </html>
    """, question=question)


# 🔹 Answer
@app.route('/answer', methods=['POST'])
def answer():
    # 🔹 Ensure session is initialized
    init_session()

    # 🔹 Ensure answers list exists (extra safety)
    if 'answers' not in session:
        session['answers'] = []

    answer_value = request.form.get('answer')
    engine = get_engine()

    current_q = engine.get_current_question()

    # Convert types
    if current_q['type'] == 'boolean':
        answer_value = answer_value == 'true'
    elif current_q['type'] == 'number':
        answer_value = float(answer_value)

    # 🔹 Store answer safely
    session['answers'].append(answer_value)

    engine.answer_question(answer_value)

    return redirect(url_for('question_page'))


# 🔹 BACK BUTTON LOGIC
@app.route('/back', methods=['POST'])
def go_back():
    if session.get('answers'):
        session['answers'].pop()  # remove last answer

    # 🔹 rebuild engine from remaining answers
    build_engine_from_history()

    return redirect(url_for('question_page'))


# 🔹 Completed
@app.route('/completed')
def completed():
    return """
    <html>
    <body style="text-align:center; font-family:Arial; margin-top:50px;">
        <h1>✅ Questionnaire Completed!</h1>
        <br>
        <a href="/restart">
            <button style="padding:10px 20px;">Restart</button>
        </a>
    </body>
    </html>
    """


# 🔹 Restart
@app.route('/restart')
def restart():
    session_id = session.get('_id')

    if session_id in engines:
        del engines[session_id]

    session.clear()

    return redirect(url_for('question_page'))


if __name__ == '__main__':
    app.run(debug=True)