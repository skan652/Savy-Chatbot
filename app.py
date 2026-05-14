from flask import Flask, request, redirect, url_for, jsonify
from flask import render_template_string, session
import json

# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)
app.secret_key = "savy-chatbot-secret-key"

# =========================================================
# LOAD QUESTIONS
# =========================================================

with open("response.json", "r", encoding="utf-8") as f:
    data = json.load(f)

QUESTIONS = data["questions"]

QUESTION_MAP = {
    q["ref"]: q for q in QUESTIONS
}

QUESTION_ORDER = [
    q["ref"] for q in QUESTIONS
]

PHASE_QUESTIONS = {
    1: ['1','2','3','4','5','6','7','8'],  # tax refunds
    2: ['9','10','11','12','13','14','15']  # tax savings
}

# =========================================================
# SESSION INIT
# =========================================================

def init_session():

    # SAFETY RESET
    if (
        "answers" not in session
        or not isinstance(session["answers"], dict)
    ):
        session["answers"] = {}

    if (
        "history" not in session
        or not isinstance(session["history"], list)
    ):
        session["history"] = []

    if "current_ref" not in session:
        session["current_ref"] = None

    if "phase" not in session:
        session["phase"] = 1

    if "phase_index" not in session:
        session["phase_index"] = 0

# =========================================================
# GET QUESTION
# =========================================================

def get_question(ref):

    return QUESTION_MAP.get(ref)

# =========================================================
# CLEAN NUMBERS
# =========================================================

def clean_number(value):

    if value is None:
        return None

    value = (
        str(value)
        .replace(",", "")
        .replace("£", "")
        .strip()
    )

    return value

# =========================================================
# NEXT QUESTION LOGIC
# =========================================================

def process_answer(question, answer):

    q_type = question.get("type")

    # -----------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------

    if question.get("required"):

        if answer is None or answer == "":
            return {
                "status": "error",
                "message": "This question is required."
            }

    # -----------------------------------------------------
    # NUMBER VALIDATION
    # -----------------------------------------------------

    if q_type in ["numeric", "number", "price", "counter"]:

        answer = clean_number(answer)

        try:
            float(answer)

        except:
            return {
                "status": "error",
                "message": "Please enter a valid number."
            }

    # -----------------------------------------------------
    # PHASE LOGIC
    # -----------------------------------------------------

    phase = session["phase"]
    phase_index = session["phase_index"]

    if phase_index < len(PHASE_QUESTIONS[phase]) - 1:
        next_index = phase_index + 1
        return {
            "status": "success",
            "next_index": next_index
        }
    else:
        if phase == 1:
            return {
                "status": "phase_change"
            }
        else:
            return {
                "status": "completed"
            }

# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
<title>Tax Refund Chatbot</title>
<style>
body{font-family:Arial;background:#f5f5f5;padding:40px;}
.container{background:white;max-width:700px;margin:auto;padding:30px;border-radius:12px;text-align:center;}
button{padding:15px;border:none;background:#667eea;color:white;border-radius:10px;cursor:pointer;font-size:16px;}
button:hover{background:#5a67d8;}
</style>
</head>
<body>
<div class="container">
<h1>Good morning, please answer to determine how eligible you are for a refund</h1>
<a href='/start'><button>Start</button></a>
</div>
</body>
</html>
""")

# =========================================================
# START
# =========================================================

@app.route("/start")
def start():

    init_session()

    return redirect(url_for("question_page"))

# =========================================================
# QUESTION PAGE
# =========================================================

@app.route("/question")
def question_page():

    init_session()

    phase = session["phase"]
    phase_index = session["phase_index"]

    if phase_index >= len(PHASE_QUESTIONS[phase]):
        return redirect(url_for("completed"))

    current_ref = PHASE_QUESTIONS[phase][phase_index]

    question = get_question(current_ref)

    if not question:
        return redirect(url_for("completed"))

    error_message = session.pop("error_message", None)

    progress = int(((phase-1)*8 + phase_index + 1) / 15 * 100)

    return render_template_string("""

<!DOCTYPE html>

<html>

<head>

<title>Questionnaire</title>

<style>

body{
    font-family:Arial;
    background:#f5f5f5;
    padding:40px;
}

.container{
    background:white;
    max-width:700px;
    margin:auto;
    padding:30px;
    border-radius:12px;
}

.progress{
    color:#666;
    margin-bottom:20px;
}

.info{
    background:#eef2ff;
    padding:15px;
    border-radius:10px;
    margin-bottom:20px;
}

.error{
    background:#ffdddd;
    padding:15px;
    border-radius:10px;
    margin-bottom:20px;
    color:#b00020;
}

.option{
    border:1px solid #ddd;
    border-radius:10px;
    padding:15px;
    margin-top:10px;
}

.option:hover{
    background:#f8f8f8;
}

button{
    width:100%;
    padding:15px;
    margin-top:20px;
    border:none;
    border-radius:10px;
    background:#667eea;
    color:white;
    font-size:16px;
    cursor:pointer;
}

button:hover{
    background:#5a67d8;
}

.back-btn{
    background:#ccc;
    color:black;
}

input[type=text]{
    width:100%;
    padding:15px;
    margin-top:20px;
    border-radius:10px;
    border:1px solid #ccc;
    box-sizing:border-box;
}

</style>

</head>

<body>

<div class="container">

    <div class="progress">
        Progress: {{ progress }}%
    </div>

    {% if error_message %}
        <div class="error">
            {{ error_message }}
        </div>
    {% endif %}

    <h1>{{ question.title }}</h1>

    {% if question.infoTitle %}
        <div class="info">

            <strong>
                {{ question.infoTitle }}
            </strong>

            <br><br>

            {{ question.info }}

        </div>
    {% endif %}

    <form method="POST" action="/answer">

    {% if question.type in ['radiov2','radio','single_choice'] %}

        {% for opt in question.options %}

            <div class="option">

                <label>

                    <input
                        type="radio"
                        name="answer"
                        value="{{ opt }}"
                        required
                    >

                    {{ opt }}

                </label>

            </div>

        {% endfor %}

        <button type="submit">
            Next
        </button>

    {% elif question.type in ['numeric','number','price','counter'] %}

        <input
            type="text"
            name="answer"
            placeholder="{{ question.placeholder }}"
            required
        >

        <button type="submit">
            Next
        </button>

    {% else %}

        <input
            type="text"
            name="answer"
            required
        >

        <button type="submit">
            Next
        </button>

    {% endif %}

    </form>

    {% if session.history|length > 0 %}

        <form method="POST" action="/back">

            <button
                type="submit"
                class="back-btn"
            >
                ⬅ Back
            </button>

        </form>

    {% endif %}

</div>

</body>

</html>

""",
    question=question,
    session=session,
    error_message=error_message,
    progress=progress
    )

# =========================================================
# ANSWER
# =========================================================

# =========================================================
# GET CURRENT QUESTION (API)

@app.route("/get_question")
def get_question_api():

    init_session()

    current_ref = session["current_ref"]
    question = get_question(current_ref)

    if not question:
        return jsonify({
            "status": "completed",
            "message": "No current question",
            "current_ref": current_ref
        })

    return jsonify({
        "status": "success",
        "current_ref": current_ref,
        "question": question
    })

# =========================================================
# ANSWER

@app.route("/answer", methods=["POST"])
def answer():

    init_session()

    current_ref = session["current_ref"]

    question = get_question(current_ref)

    if not question:
        return redirect(url_for("completed"))

    if request.is_json:
        payload = request.get_json(silent=True) or {}
        answer_value = payload.get("answer")
    else:
        answer_value = request.form.get("answer")

    # CLEAN NUMBERS
    if question.get("type") in [
        "numeric",
        "number",
        "price",
        "counter"
    ]:
        answer_value = clean_number(answer_value)

    result = process_answer(
        question,
        answer_value
    )

    # -----------------------------------------------------
    # ERROR
    # -----------------------------------------------------

    if result["status"] == "error":

        if request.is_json:
            return jsonify({
                "status": "error",
                "message": result["message"]
            }), 400

        session["error_message"] = result["message"]

        return redirect(url_for("question_page"))

    # -----------------------------------------------------
    # SAVE ANSWER
    # -----------------------------------------------------

    answers = session["answers"]

    answers[current_ref] = answer_value

    session["answers"] = answers

    # -----------------------------------------------------
    # SAVE HISTORY
    # -----------------------------------------------------

    history = session["history"]

    history.append(current_ref)

    session["history"] = history

    # -----------------------------------------------------
    # PHASE CHANGE
    # -----------------------------------------------------

    if result["status"] == "phase_change":

        session["phase"] = 2
        session["phase_index"] = 0

        return redirect(url_for("phase_message"))

    # -----------------------------------------------------
    # COMPLETE
    # -----------------------------------------------------

    if result["status"] == "completed":

        return redirect(url_for("completed"))

    # -----------------------------------------------------
    # NEXT QUESTION
    # -----------------------------------------------------

    session["phase_index"] = result["next_index"]

    return redirect(url_for("question_page"))

# =========================================================
# BACK
# =========================================================

@app.route("/back", methods=["POST"])
def back():

    init_session()

    history = session["history"]

    if history:

        current_ref = session["current_ref"]

        # REMOVE CURRENT ANSWER
        answers = session["answers"]

        if current_ref in answers:
            del answers[current_ref]

        session["answers"] = answers

        # GO BACK
        previous_ref = history.pop()

        session["history"] = history

        session["current_ref"] = previous_ref

    return redirect(url_for("question_page"))

# =========================================================
# PHASE MESSAGE
# =========================================================

@app.route("/phase_message")
def phase_message():

    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
<title>Tax Refund Chatbot</title>
<style>
body{font-family:Arial;background:#f5f5f5;padding:40px;}
.container{background:white;max-width:700px;margin:auto;padding:30px;border-radius:12px;text-align:center;}
button{padding:15px;border:none;background:#667eea;color:white;border-radius:10px;cursor:pointer;font-size:16px;}
button:hover{background:#5a67d8;}
</style>
</head>
<body>
<div class="container">
<h1>Thank you, next step</h1>
<a href='/continue'><button>Continue</button></a>
</div>
</body>
</html>
""")

# =========================================================
# CONTINUE
# =========================================================

@app.route("/continue")
def continue_phase():

    return redirect(url_for("question_page"))

# =========================================================
# COMPLETED
# =========================================================

@app.route("/completed")
def completed():

    answers = session.get("answers", {})

    formatted_answers = ""

    for ref in QUESTION_ORDER:
        if ref in answers:
            formatted_answers += f"<p><strong>{ref}</strong>: {answers[ref]}</p>"

    return f"""

<html>

<body style='font-family:Arial;padding:40px;'>

<h1>
    Thank you for submitting!
</h1>

<h2>
    Your Answers
</h2>

{formatted_answers}

<br><br>

<a href='/restart'>

<button
style='
padding:15px;
border:none;
background:#667eea;
color:white;
border-radius:10px;
cursor:pointer;
'
>

Restart

</button>

</a>

</body>

</html>

"""

# =========================================================
# RESTART
# =========================================================

@app.route("/restart")
def restart():

    session.clear()

    return redirect(url_for("home"))

# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    app.run(debug=True)
