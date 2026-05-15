from flask import Flask, request, redirect, url_for, jsonify
from flask import render_template_string, session
import json
from state_machine import StateMachineEngine

# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)
@app.before_request
def require_passkey():
    allowed_routes = ["passkey_page", "verify_passkey", "static"]

    if request.endpoint in allowed_routes:
        return

    if not session.get("passkey_verified"):
        return redirect(url_for("passkey_page"))
    
app.secret_key = "savy-chatbot-secret-key"

# =========================================================
# PASSKEY CONFIGURATION
# =========================================================

VALID_PASSKEYS = ["12345", "pass123"]  # Set your valid passkeys here

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

# =========================================================
# STATE MACHINE ENGINE
# =========================================================

engine = StateMachineEngine("response.json")

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

    if "current_ref" not in session or session["current_ref"] is None:
        session["current_ref"] = engine.get_first_question()["ref"]

    if "phase" not in session:
        session["phase"] = 1

    if "phase_index" not in session:
        session["phase_index"] = 0

    if "passkey_verified" not in session:
        session["passkey_verified"] = False

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

def process_answer(current_ref, answer):

    result = engine.get_next_question_ref(current_ref, answer)

    if result.get("status") == "error":
        return result

    if result.get("status") == "completed":
        return {"status": "completed"}

    next_ref = result.get("next_ref")

    # Check if next_ref is in current phase
    phase = session["phase"]
    current_phase_questions = PHASE_QUESTIONS.get(phase, [])

    if next_ref in current_phase_questions:
        # Stay in same phase
        next_index = current_phase_questions.index(next_ref)
        return {
            "status": "success",
            "next_index": next_index
        }
    else:
        # Check if it's in next phase
        next_phase = phase + 1
        next_phase_questions = PHASE_QUESTIONS.get(next_phase, [])
        if next_ref in next_phase_questions:
            return {
                "status": "phase_change",
                "next_phase": next_phase,
                "next_index": next_phase_questions.index(next_ref)
            }
        else:
            # If not in next phase, assume completed or invalid
            return {"status": "completed"}

# =========================================================
# ROOT
# =========================================================

@app.route("/")
def index():
    init_session()

    # ALWAYS force passkey first
    if not session.get("passkey_verified", False):
        return redirect(url_for("passkey_page"))

    return redirect(url_for("welcome"))

# =========================================================
# WELCOME PAGE
# =========================================================

@app.route("/welcome")
def welcome():
    init_session()

    if not session.get("passkey_verified", False):
        return redirect(url_for("passkey_page"))

    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
<title>Tax Refund Eligibility Chatbot</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* { box-sizing: border-box; }
body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    margin: 0;
    padding: 20px;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
}
.container {
    background: white;
    max-width: 600px;
    width: 100%;
    padding: 40px;
    border-radius: 20px;
    box-shadow: 0 20px 40px rgba(0,0,0,0.1);
    text-align: center;
    animation: fadeIn 0.5s ease-in;
}
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
}
h1 {
    color: #333;
    margin-bottom: 20px;
    font-size: 2.2em;
    font-weight: 300;
}
p {
    color: #666;
    font-size: 1.1em;
    margin-bottom: 30px;
    line-height: 1.6;
}
.start-btn {
    background: linear-gradient(45deg, #667eea, #764ba2);
    color: white;
    border: none;
    padding: 15px 40px;
    font-size: 1.2em;
    border-radius: 50px;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
}
.start-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
}
.start-btn:active {
    transform: translateY(0);
}
</style>
</head>
<body>
<div class="container">
<h1>🌅 Good morning!</h1>
<p>Please answer a few questions to determine how eligible you are for a tax refund.</p>
<a href='/start'><button class="start-btn">Start Assessment →</button></a>
</div>
</body>
</html>
""")


# =========================================================
# PASSKEY PAGE
# =========================================================

@app.route("/passkey")
def passkey_page():

    init_session()

    if session.get("passkey_verified", False):
        return redirect(url_for("welcome"))

    error_message = session.pop("passkey_error", None)

    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
<title>Enter Passkey - Tax Refund Eligibility Chatbot</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* { box-sizing: border-box; }
body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    margin: 0;
    padding: 20px;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
}
.container {
    background: white;
    max-width: 600px;
    width: 100%;
    padding: 40px;
    border-radius: 20px;
    box-shadow: 0 20px 40px rgba(0,0,0,0.1);
    text-align: center;
    animation: fadeIn 0.5s ease-in;
}
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
}
h1 {
    color: #333;
    margin-bottom: 10px;
    font-size: 2em;
    font-weight: 300;
}
.subtitle {
    color: #666;
    margin-bottom: 30px;
    font-size: 0.95em;
}
.error {
    background: #fff2f2;
    padding: 15px;
    border-radius: 10px;
    margin-bottom: 20px;
    color: #d63031;
    border-left: 4px solid #d63031;
}
.form-group {
    margin-bottom: 20px;
}
label {
    display: block;
    text-align: left;
    color: #333;
    margin-bottom: 8px;
    font-weight: 500;
}
input[type="password"] {
    width: 100%;
    padding: 15px;
    border: 2px solid #e0e0e0;
    border-radius: 12px;
    font-size: 1em;
    transition: border-color 0.3s ease;
}
input[type="password"]:focus {
    outline: none;
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}
.submit-btn {
    width: 100%;
    padding: 15px;
    background: linear-gradient(45deg, #667eea, #764ba2);
    color: white;
    border: none;
    border-radius: 12px;
    font-size: 1.1em;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
}
.submit-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
}
.submit-btn:active {
    transform: translateY(0);
}
</style>
</head>
<body>
<div class="container">
<h1>🔐 Access Required</h1>
<p class="subtitle">Please enter the passkey to access the assessment</p>

{% if error_message %}
    <div class="error">
        ⚠️ {{ error_message }}
    </div>
{% endif %}

<form method="POST" action="/verify_passkey">
    <div class="form-group">
        <label for="passkey">Passkey</label>
        <input 
            type="password" 
            id="passkey" 
            name="passkey" 
            placeholder="Enter your passkey"
            required
            autofocus
        >
    </div>
    <button type="submit" class="submit-btn">Verify & Continue →</button>
</form>
</div>
</body>
</html>
""",
    error_message=error_message
    )

# =========================================================
# VERIFY PASSKEY
# =========================================================

@app.route("/verify_passkey", methods=["POST"])
def verify_passkey():

    passkey = request.form.get("passkey", "").strip()

    if passkey in VALID_PASSKEYS:
        session["passkey_verified"] = True
        return redirect(url_for("welcome"))
    else:
        session["passkey_error"] = "Invalid passkey. Please try again."
        return redirect(url_for("passkey_page"))

# =========================================================
# START
# =========================================================

@app.route("/start")
def start():

    init_session()

    # Verify passkey before starting
    if not session.get("passkey_verified", False):
        return redirect(url_for("passkey_page"))

    return redirect(url_for("question_page"))

# =========================================================
# QUESTION PAGE
# =========================================================

@app.route("/question")
def question_page():

    init_session()

    # Verify passkey before showing question
    if not session.get("passkey_verified", False):
        return redirect(url_for("passkey_page"))

    phase = session["phase"]
    phase_index = session["phase_index"]

    if phase_index >= len(PHASE_QUESTIONS[phase]):
        return redirect(url_for("completed"))

    current_ref = PHASE_QUESTIONS[phase][phase_index]

    question = get_question(current_ref)

    if not question:
        return redirect(url_for("completed"))

    error_message = session.pop("error_message", None)

    # Calculate progress based on phase
    total_questions = sum(len(qs) for qs in PHASE_QUESTIONS.values())
    current_question_index = sum(len(PHASE_QUESTIONS[p]) for p in range(1, phase)) + phase_index
    progress = int((current_question_index + 1) / total_questions * 100)

    return render_template_string("""

<!DOCTYPE html>

<html>

<head>

<title>Questionnaire</title>

<style>

* { box-sizing: border-box; }
body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    margin: 0;
    padding: 20px;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
}
.container {
    background: white;
    max-width: 700px;
    width: 100%;
    padding: 30px;
    border-radius: 20px;
    box-shadow: 0 20px 40px rgba(0,0,0,0.1);
    animation: fadeIn 0.5s ease-in;
}
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
}
.progress-container {
    margin-bottom: 30px;
}
.progress-bar {
    width: 100%;
    height: 8px;
    background: #e0e0e0;
    border-radius: 4px;
    overflow: hidden;
}
.progress-fill {
    height: 100%;
    background: linear-gradient(45deg, #667eea, #764ba2);
    border-radius: 4px;
    transition: width 0.3s ease;
}
.progress-text {
    text-align: center;
    margin-top: 10px;
    color: #666;
    font-size: 0.9em;
}
.info {
    background: #f8f9ff;
    padding: 20px;
    border-radius: 12px;
    margin-bottom: 25px;
    border-left: 4px solid #667eea;
}
.info strong {
    color: #333;
}
.error {
    background: #fff2f2;
    padding: 15px;
    border-radius: 10px;
    margin-bottom: 20px;
    color: #d63031;
    border-left: 4px solid #d63031;
}
h1 {
    color: #333;
    margin-bottom: 15px;
    font-size: 1.8em;
    font-weight: 400;
}
.option {
    border: 2px solid #e0e0e0;
    border-radius: 12px;
    padding: 15px;
    margin-top: 10px;
    transition: all 0.3s ease;
    cursor: pointer;
}
.option:hover {
    border-color: #667eea;
    background: #f8f9ff;
    transform: translateY(-2px);
}
.option input[type="radio"] {
    margin-right: 10px;
    accent-color: #667eea;
}
.submit-btn {
    width: 100%;
    padding: 15px;
    margin-top: 25px;
    border: none;
    border-radius: 12px;
    background: linear-gradient(45deg, #667eea, #764ba2);
    color: white;
    font-size: 1.1em;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
}
.submit-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
}
.submit-btn:active {
    transform: translateY(0);
}
.back-btn {
    background: #f1f1f1;
    color: #666;
    border: 2px solid #e0e0e0;
    margin-top: 15px;
    width: 100%;
    padding: 12px;
    border-radius: 12px;
    cursor: pointer;
    transition: all 0.3s ease;
}
.back-btn:hover {
    background: #e8e8e8;
    border-color: #ccc;
}
input[type="text"] {
    width: 100%;
    padding: 15px;
    margin-top: 15px;
    border-radius: 12px;
    border: 2px solid #e0e0e0;
    font-size: 1em;
    transition: border-color 0.3s ease;
}
input[type="text"]:focus {
    outline: none;
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}
.submit-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}
.validation-error {
    color: #d63031;
    font-size: 0.9em;
    margin-top: 8px;
    display: none;
}
.validation-error.show {
    display: block;
}

</style>

</head>

<body>

<div class="container">
    <div class="progress-container">
        <div class="progress-bar">
            <div class="progress-fill" style="width: {{ progress }}%"></div>
        </div>
        <div class="progress-text">Progress: {{ progress }}%</div>
    </div>

    {% if error_message %}
        <div class="error">
            ⚠️ {{ error_message }}
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

    <form method="POST" action="/answer" onsubmit="return validateForm(event)">

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
        <button type="submit" class="submit-btn">Next →</button>

    {% elif question.type in ['numeric','number','price','counter'] %}

        <input type="text" id="numericInput" name="answer" placeholder="{{ question.placeholder }}" required oninput="validateNumericInput()">
        <div id="validationError" class="validation-error">⚠️ Please enter a valid number</div>
        <button type="submit" id="submitBtn" class="submit-btn">Next →</button>

    {% else %}


        <input type="text" name="answer" required>
        <button type="submit" class="submit-btn">Next →</button>

    {% endif %}

    </form>

    {% if session.history|length > 0 %}

        <form method="POST" action="/back">

            <button type="submit" class="back-btn">← Back</button>

        </form>

    {% endif %}

</div>

<script>
function validateNumericInput() {
    const input = document.getElementById('numericInput');
    const errorMsg = document.getElementById('validationError');
    const submitBtn = document.getElementById('submitBtn');
    
    if (!input || !errorMsg || !submitBtn) return;
    
    const value = input.value.trim();
    const cleanedValue = value.replace(/,/g, '').replace(/£/g, '').trim();
    
    // Check if it's a valid number
    const isValidNumber = cleanedValue !== '' && !isNaN(cleanedValue) && cleanedValue !== '0' || cleanedValue === '0';
    
    if (value === '') {
        errorMsg.classList.remove('show');
        submitBtn.disabled = true;
    } else if (!isValidNumber || isNaN(parseFloat(cleanedValue))) {
        errorMsg.classList.add('show');
        submitBtn.disabled = true;
    } else {
        errorMsg.classList.remove('show');
        submitBtn.disabled = false;
    }
}

function validateForm(event) {
    const input = document.getElementById('numericInput');
    
    // If this is a numeric question
    if (input) {
        const value = input.value.trim();
        const cleanedValue = value.replace(/,/g, '').replace(/£/g, '').trim();
        
        // Check if it's a valid number
        if (value === '' || isNaN(cleanedValue) || cleanedValue === '') {
            event.preventDefault();
            return false;
        }
    }
    
    return true;
}

// Initialize validation on page load
document.addEventListener('DOMContentLoaded', function() {
    const input = document.getElementById('numericInput');
    if (input) {
        validateNumericInput();
    }
});
</script>

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
        current_ref,
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

        session["phase"] = result["next_phase"]
        session["phase_index"] = result["next_index"]
        session["current_ref"] = PHASE_QUESTIONS[result["next_phase"]][result["next_index"]]

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
    session["current_ref"] = PHASE_QUESTIONS[session["phase"]][result["next_index"]]

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

        # Update phase and phase_index
        for ph, questions in PHASE_QUESTIONS.items():
            if previous_ref in questions:
                session["phase"] = ph
                session["phase_index"] = questions.index(previous_ref)
                break

    return redirect(url_for("question_page"))

# =========================================================
# PHASE MESSAGE
# =========================================================

@app.route("/phase_message")
def phase_message():

    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
<title>Tax Refund Chatbot</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* { box-sizing: border-box; }
body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    margin: 0;
    padding: 20px;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
}
.container {
    background: white;
    max-width: 600px;
    width: 100%;
    padding: 40px;
    border-radius: 20px;
    box-shadow: 0 20px 40px rgba(0,0,0,0.1);
    text-align: center;
    animation: fadeIn 0.5s ease-in;
}
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
}
h1 {
    color: #333;
    margin-bottom: 20px;
    font-size: 2.2em;
    font-weight: 300;
}
p {
    color: #666;
    font-size: 1.1em;
    margin-bottom: 30px;
    line-height: 1.6;
}
.continue-btn {
    background: linear-gradient(45deg, #667eea, #764ba2);
    color: white;
    border: none;
    padding: 15px 40px;
    font-size: 1.2em;
    border-radius: 50px;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
}
.continue-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
}
.continue-btn:active {
    transform: translateY(0);
}
</style>
</head>
<body>
<div class="container">
<h1>✅ Thank you!</h1>
<p>Now let's move to the next step: tax savings assessment.</p>
<a href='/continue'><button class="continue-btn">Continue →</button></a>
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

<html lang="en">

<head>
<title>Assessment Complete</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* {{ box-sizing: border-box; }}
body {{
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    margin: 0;
    padding: 20px;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
}}
.container {{
    background: white;
    max-width: 700px;
    width: 100%;
    padding: 40px;
    border-radius: 20px;
    box-shadow: 0 20px 40px rgba(0,0,0,0.1);
    text-align: center;
    animation: fadeIn 0.5s ease-in;
}}
@keyframes fadeIn {{
    from {{ opacity: 0; transform: translateY(20px); }}
    to {{ opacity: 1; transform: translateY(0); }}
}}
h1 {{
    color: #333;
    margin-bottom: 20px;
    font-size: 2.2em;
    font-weight: 300;
}}
p {{
    color: #666;
    margin-bottom: 15px;
    line-height: 1.6;
    text-align: left;
}}
.restart-btn {{
    background: linear-gradient(45deg, #667eea, #764ba2);
    color: white;
    border: none;
    padding: 15px 40px;
    font-size: 1.2em;
    border-radius: 50px;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
    margin-top: 20px;
}}
.restart-btn:hover {{
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
}}
.restart-btn:active {{
    transform: translateY(0);
}}
</style>
</head>

<body>

<div class="container">

<h1>🎉 Thank you for submitting!</h1>

<p>Your assessment has been completed. Here are your answers:</p>

{formatted_answers}

<a href='/restart'>

<button class="restart-btn">Take Assessment Again →</button>

</a>

</div>

</body>

</html>

"""

# =========================================================
# RESTART
# =========================================================

@app.route("/restart")
def restart():

    session.clear()

    return redirect(url_for("passkey_page"))

# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    app.run(debug=True)
