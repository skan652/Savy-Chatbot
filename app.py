from flask import Flask, request, redirect, url_for, jsonify, session
from flask import render_template_string
import json
import re

app = Flask(__name__)
app.secret_key = "savy-chatbot-secret-key"

# =========================================================
# PASSKEY CONFIGURATION
# =========================================================

VALID_PASSKEYS = ["12345", "pass123"]

# =========================================================
# LOAD QUESTIONS
# =========================================================

with open("response.json", "r", encoding="utf-8") as f:
    data = json.load(f)

QUESTIONS = data["questions"]

QUESTION_MAP = {q["ref"]: q for q in QUESTIONS}

# =========================================================
# PHASE CONFIGURATION
# =========================================================
# Tax Refunds Phase: Questions 1-8
# Tax Savings Phase: Questions 9-15

PHASE_1_QUESTIONS = ["1", "2", "3", "4", "5", "6", "7", "8"]
PHASE_2_QUESTIONS = ["9", "10", "11", "12", "13", "14", "15"]

# =========================================================
# HELPER FUNCTIONS
# =========================================================

def init_session():
    if "messages" not in session:
        session["messages"] = []
    if "answers" not in session:
        session["answers"] = {}
    if "current_ref" not in session:
        session["current_ref"] = "1"
    if "passkey_verified" not in session:
        session["passkey_verified"] = False
    if "waiting_for_answer" not in session:
        session["waiting_for_answer"] = False
    if "completed" not in session:
        session["completed"] = False
    if "history" not in session:
        session["history"] = []
    if "pending_proposal" not in session:
        session["pending_proposal"] = None
    if "phase" not in session:
        session["phase"] = 1  # 1 = Tax Refunds, 2 = Tax Savings
    if "phase_transition_shown" not in session:
        session["phase_transition_shown"] = False

def get_question(ref):
    return QUESTION_MAP.get(str(ref))

def clean_number(value):
    if value is None:
        return None
    cleaned = re.sub(r'[£,€$]', '', str(value))
    cleaned = re.sub(r'[^\d.]', '', cleaned)
    return cleaned

def get_question_text(question):
    """Get formatted question text"""
    if not question:
        return None
    
    text = question.get("title", "")
    
    if question.get("subTitle"):
        text = f"{text}\n\n📊 **{question['subTitle']}**"
    
    if question.get("infoTitle") and question.get("info"):
        text = f"{text}\n\nℹ️ **{question['infoTitle']}**\n{question['info']}"
    
    if question.get("placeholder"):
        text = f"{text}\n\n💡 *Example: {question['placeholder']}*"
    
    return text

def get_options(question):
    """Get options for a question"""
    if question and question.get("type") in ['radiov2', 'radio', 'single_choice']:
        options = question.get("options", [])
        return [opt.replace('\n', ' ') for opt in options]
    return None

def get_question_type(question):
    """Get the input type for a question"""
    if not question:
        return "text"
    
    q_type = question.get("type", "text")
    
    if q_type in ['radiov2', 'radio', 'single_choice']:
        return "choice"
    elif q_type in ['numeric', 'number', 'price', 'counter']:
        return "numeric"
    else:
        return "text"

def process_handler_next(current_ref, answer):
    """Process the handlerNext logic from the JSON"""
    question = get_question(current_ref)
    if not question or "handlerNext" not in question:
        # Move to next question in current phase
        return get_next_question_in_phase(current_ref)
    
    clean_answer = answer.replace('\n', ' ').strip()
    
    # Find matching handler
    handler = None
    for key, value in question["handlerNext"].items():
        clean_key = key.replace('\n', ' ').strip()
        if clean_key == clean_answer:
            handler = value
            break
    
    if not handler:
        for key, value in question["handlerNext"].items():
            if clean_answer in key.replace('\n', ' '):
                handler = value
                break
    
    if not handler:
        return get_next_question_in_phase(current_ref)
    
    action = handler.get("action")
    
    if action == "navigate_to_screen":
        ref_path = handler.get("ref", "")
        if "StartRefund" in ref_path:
            # Move to next question in phase
            return get_next_question_in_phase(current_ref)
        return {"status": "completed"}
    
    elif action == "open_question":
        next_ref = handler.get("ref")
        return {"status": "success", "next_ref": str(next_ref), "completed": False}
    
    elif action == "to_save_and_finish":
        return {"status": "completed"}
    
    elif action == "to_save_and_finish_with_error":
        return {"status": "completed"}
    
    else:
        return get_next_question_in_phase(current_ref)

def get_next_question_in_phase(current_ref):
    """Get the next question within the current phase"""
    if session["phase"] == 1:
        current_index = PHASE_1_QUESTIONS.index(current_ref) if current_ref in PHASE_1_QUESTIONS else -1
        if current_index >= 0 and current_index + 1 < len(PHASE_1_QUESTIONS):
            next_ref = PHASE_1_QUESTIONS[current_index + 1]
            return {"status": "success", "next_ref": next_ref, "completed": False}
        else:
            # End of phase 1, move to phase 2
            return {"status": "phase_complete"}
    else:
        current_index = PHASE_2_QUESTIONS.index(current_ref) if current_ref in PHASE_2_QUESTIONS else -1
        if current_index >= 0 and current_index + 1 < len(PHASE_2_QUESTIONS):
            next_ref = PHASE_2_QUESTIONS[current_index + 1]
            return {"status": "success", "next_ref": next_ref, "completed": False}
        else:
            # End of phase 2, complete
            return {"status": "completed"}

def handle_proposal(current_ref, answer):
    """Handle proposal questions (like q5 with nested questions)"""
    question = get_question(current_ref)
    if not question or "proposal" not in question:
        return None
    
    proposal = question.get("proposal", {})
    clean_answer = answer.replace('\n', ' ').strip()
    
    for key, proposal_questions in proposal.items():
        clean_key = key.replace('\n', ' ').strip()
        if clean_key == clean_answer or clean_answer in clean_key:
            session["pending_proposal"] = {
                "original_ref": current_ref,
                "answer": answer,
                "questions": proposal_questions,
                "current_index": 0
            }
            return proposal_questions
    
    return None

def add_message(role, content, options=None, input_type=None):
    """Add a message to the chat history"""
    message = {"role": role, "content": content}
    if options:
        message["options"] = options
    if input_type:
        message["input_type"] = input_type
    session["messages"].append(message)

def process_next_question():
    """Process and send the next question"""
    if session.get("completed"):
        return
    
    # Check if we have pending proposal questions
    if session.get("pending_proposal"):
        proposal_data = session["pending_proposal"]
        proposal_questions = proposal_data["questions"]
        
        if proposal_data.get("current_index", 0) < len(proposal_questions):
            prop_q = proposal_questions[proposal_data["current_index"]]
            question_text = get_question_text(prop_q)
            options = get_options(prop_q)
            input_type = get_question_type(prop_q)
            
            add_message("assistant", question_text, options, input_type)
            session["waiting_for_answer"] = True
            return
    
    # Regular question flow
    current_ref = session["current_ref"]
    question = get_question(current_ref)
    
    if not question:
        complete_assessment()
        return
    
    question_text = get_question_text(question)
    options = get_options(question)
    input_type = get_question_type(question)
    
    add_message("assistant", question_text, options, input_type)
    session["waiting_for_answer"] = True

def show_phase_transition():
    """Show the transition message between phases"""
    if session["phase"] == 2 and not session.get("phase_transition_shown"):
        transition_msg = "✅ **Thank you for completing the tax refunds section!**\n\n"
        transition_msg += "Now let's move to the next step: **Tax Savings Assessment**.\n"
        transition_msg += "Please answer the following questions about your travel and expenses.\n"
        transition_msg += "\n---\n"
        
        add_message("assistant", transition_msg)
        session["phase_transition_shown"] = True
        return True
    return False

def complete_assessment():
    """Complete the assessment and show final results"""
    session["completed"] = True
    session["waiting_for_answer"] = False
    
    answers = session.get("answers", {})
    
    # Calculate eligibility based on answers
    eligible_for_refund = False
    eligible_for_savings = False
    
    # Check eligibility criteria
    if "1" in answers:
        income = answers["1"]
        if income in ["Between £14k & £50k", "Over £50k"]:
            eligible_for_refund = True
    
    if "2" in answers and answers["2"] == "Yes":
        eligible_for_refund = eligible_for_refund and True
    
    if "13" in answers and answers["13"] == "Yes":
        eligible_for_savings = True
    
    # Build final results message
    final_message = "🎉 **Assessment Complete!** 🎉\n\n"
    final_message += "=" * 50 + "\n\n"
    
    final_message += "📊 **FINAL RESULTS**\n\n"
    
    # Tax Refund Eligibility
    final_message += "💰 **Tax Refund Eligibility:**\n"
    if eligible_for_refund:
        final_message += "✅ **You may be eligible for a tax refund!**\n"
        final_message += "Based on your responses about income and work travel, you could claim back:\n"
        final_message += "• Travel expenses\n"
        final_message += "• Mileage costs\n"
        final_message += "• Food and drink expenses\n\n"
    else:
        final_message += "❌ Not eligible for tax refund at this time.\n"
        final_message += "You may still qualify for other tax savings.\n\n"
    
    # Tax Savings Eligibility
    final_message += "💡 **Tax Savings Eligibility:**\n"
    if eligible_for_savings:
        final_message += "✅ **You may be eligible for additional tax savings!**\n"
        final_message += "Your responses indicate you might qualify for:\n"
        final_message += "• Work-from-home tax relief\n"
        final_message += "• Professional subscription deductions\n"
        final_message += "• Uniform and tool allowances\n\n"
    else:
        final_message += "ℹ️ Limited tax savings identified at this time.\n\n"
    
    # Summary of key answers
    final_message += "=" * 50 + "\n\n"
    final_message += "📋 **Summary of Your Responses:**\n\n"
    
    key_info = []
    if "1" in answers:
        key_info.append(f"• Annual Income: {answers['1']}")
    if "2" in answers:
        key_info.append(f"• Travel for Work: {answers['2']}")
    if "4" in answers:
        key_info.append(f"• Annual Mileage: {answers['4']} miles")
    if "9" in answers:
        key_info.append(f"• Travel Days/Week: {answers['9']} days")
    if "13" in answers:
        key_info.append(f"• Past Income >£14k: {answers['13']}")
    
    final_message += "\n".join(key_info)
    
    final_message += "\n\n" + "=" * 50 + "\n\n"
    final_message += "📞 **Next Steps:**\n\n"
    
    if eligible_for_refund or eligible_for_savings:
        final_message += "A tax specialist will contact you within 2-3 business days to:\n"
        final_message += "• Review your eligibility in detail\n"
        final_message += "• Calculate your potential refund amount\n"
        final_message += "• Guide you through the claims process\n\n"
    else:
        final_message += "While you may not qualify at this time, keep track of:\n"
        final_message += "• Work-related travel expenses\n"
        final_message += "• Mileage records\n"
        final_message += "• Food and drink receipts for future claims\n\n"
    
    final_message += "Thank you for using the Tax Assistant Bot! 🙏\n\n"
    final_message += "Click 'Start New Assessment' below to begin again."
    
    add_message("assistant", final_message)

# =========================================================
# ROUTES
# =========================================================

@app.before_request
def require_passkey():
    allowed_routes = ["passkey_page", "verify_passkey", "static", "favicon"]
    
    if request.endpoint in allowed_routes:
        return
    
    if not session.get("passkey_verified"):
        return redirect(url_for("passkey_page"))

@app.route("/")
def index():
    init_session()
    if not session.get("passkey_verified"):
        return redirect(url_for("passkey_page"))
    return redirect(url_for("chat"))

@app.route("/passkey")
def passkey_page():
    init_session()
    if session.get("passkey_verified"):
        return redirect(url_for("chat"))
    
    error_message = session.pop("passkey_error", None)
    
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Passkey Required - Tax Bot</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
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
            max-width: 500px;
            width: 100%;
            padding: 40px;
            border-radius: 24px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 1.8em;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
        }
        .error {
            background: #fee;
            padding: 12px;
            border-radius: 12px;
            color: #c33;
            margin-bottom: 20px;
            font-size: 0.9em;
        }
        input {
            width: 100%;
            padding: 14px;
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            font-size: 1em;
            margin-bottom: 20px;
            transition: border-color 0.2s;
        }
        input:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 1.1em;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔐 Access Required</h1>
        <p class="subtitle">Enter passkey to continue</p>
        {% if error_message %}
            <div class="error">{{ error_message }}</div>
        {% endif %}
        <form method="POST" action="/verify_passkey">
            <input type="password" name="passkey" placeholder="Enter passkey" required autofocus>
            <button type="submit">Verify →</button>
        </form>
    </div>
</body>
</html>
""", error_message=error_message)

@app.route("/verify_passkey", methods=["POST"])
def verify_passkey():
    passkey = request.form.get("passkey", "").strip()
    
    if passkey in VALID_PASSKEYS:
        session["passkey_verified"] = True
        return redirect(url_for("chat"))
    else:
        session["passkey_error"] = "Invalid passkey. Please try again."
        return redirect(url_for("passkey_page"))

@app.route("/chat")
def chat():
    init_session()
    
    if not session.get("passkey_verified"):
        return redirect(url_for("passkey_page"))
    
    # Start the conversation if it hasn't started
    if not session["messages"] and not session["completed"]:
        welcome_msg = "🌅 **Good morning!**\n\n"
        welcome_msg += "Please answer a few questions to determine how eligible you are for a tax refund and tax savings.\n\n"
        welcome_msg += "Let's start with the **Tax Refunds Assessment**."
        add_message("assistant", welcome_msg)
        process_next_question()
    
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Tax Assistant Bot</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        
        .chat-container {
            max-width: 900px;
            width: 100%;
            margin: 0 auto;
            background: white;
            height: 100vh;
            display: flex;
            flex-direction: column;
            box-shadow: 0 0 40px rgba(0,0,0,0.1);
        }
        
        .chat-header {
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            padding: 20px;
            text-align: center;
            border-radius: 0;
        }
        
        .chat-header h1 {
            font-size: 1.5em;
            font-weight: 500;
        }
        
        .chat-header p {
            font-size: 0.85em;
            opacity: 0.9;
            margin-top: 5px;
        }
        
        .phase-indicator {
            background: rgba(255,255,255,0.2);
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.8em;
            margin-top: 8px;
            display: inline-block;
        }
        
        .messages-container {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: #f7f7f8;
        }
        
        .message {
            margin-bottom: 20px;
            display: flex;
            animation: fadeIn 0.3s ease-in;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .message.user {
            justify-content: flex-end;
        }
        
        .message-content {
            max-width: 70%;
            padding: 12px 16px;
            border-radius: 18px;
            line-height: 1.5;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        
        .message.user .message-content {
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            border-bottom-right-radius: 4px;
        }
        
        .message.assistant .message-content {
            background: white;
            color: #333;
            border-bottom-left-radius: 4px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }
        
        .options-container {
            margin-top: 12px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }
        
        .option-btn {
            background: #f0f0f0;
            border: 1px solid #ddd;
            padding: 8px 16px;
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 0.9em;
            color: #333;
        }
        
        .option-btn:hover {
            background: #667eea;
            border-color: #667eea;
            color: white;
            transform: translateY(-1px);
        }
        
        .input-container {
            background: white;
            border-top: 1px solid #e0e0e0;
            padding: 20px;
            display: flex;
            gap: 10px;
        }
        
        .input-container input {
            flex: 1;
            padding: 12px;
            border: 1px solid #e0e0e0;
            border-radius: 24px;
            font-size: 1em;
            outline: none;
            transition: border-color 0.2s;
        }
        
        .input-container input:focus {
            border-color: #667eea;
        }
        
        .input-container button {
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 24px;
            cursor: pointer;
            font-size: 1em;
            transition: transform 0.2s;
        }
        
        .input-container button:hover {
            transform: translateY(-1px);
        }
        
        .input-container button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        .restart-btn {
            background: #f0f0f0;
            color: #666;
            margin-top: 10px;
        }
        
        .restart-btn:hover {
            background: #e0e0e0;
            transform: translateY(-1px);
        }
        
        .typing-indicator {
            display: flex;
            gap: 4px;
            padding: 12px 16px;
            background: white;
            border-radius: 18px;
            width: fit-content;
        }
        
        .typing-indicator span {
            width: 8px;
            height: 8px;
            background: #999;
            border-radius: 50%;
            animation: bounce 1.4s infinite;
        }
        
        .typing-indicator span:nth-child(2) {
            animation-delay: 0.2s;
        }
        
        .typing-indicator span:nth-child(3) {
            animation-delay: 0.4s;
        }
        
        @keyframes bounce {
            0%, 60%, 100% { transform: translateY(0); }
            30% { transform: translateY(-10px); }
        }
        
        @media (max-width: 768px) {
            .message-content {
                max-width: 85%;
            }
            
            .input-container {
                padding: 15px;
            }
        }
    </style>
</head>
<body>
    <div class="chat-container">
        <div class="chat-header">
            <h1>💬 Tax Assistant Bot</h1>
            <p>Your personal tax eligibility advisor</p>
            <div class="phase-indicator">
                {% if not completed %}
                    {% if phase == 1 %}
                        📋 Phase 1/2: Tax Refunds Assessment
                    {% else %}
                        💰 Phase 2/2: Tax Savings Assessment
                    {% endif %}
                {% endif %}
            </div>
        </div>
        
        <div class="messages-container" id="messages-container">
            {% for message in messages %}
                <div class="message {{ message.role }}">
                    <div class="message-content">
                        {{ message.content | replace('\\n', '<br>') | safe }}
                        {% if message.options %}
                            <div class="options-container">
                                {% for option in message.options %}
                                    <button class="option-btn" onclick="sendMessage('{{ option | replace("'", "\\'") | replace("\\n", " ") }}')">
                                        {{ option | replace('\\n', ' ') }}
                                    </button>
                                {% endfor %}
                            </div>
                        {% endif %}
                    </div>
                </div>
            {% endfor %}
            
            {% if waiting_for_answer and not completed %}
                <div class="message assistant">
                    <div class="typing-indicator">
                        <span></span>
                        <span></span>
                        <span></span>
                    </div>
                </div>
            {% endif %}
        </div>
        
        <div class="input-container">
            <input type="text" id="message-input" placeholder="Type your answer here..." autocomplete="off">
            <button onclick="sendMessage()" id="send-btn">Send</button>
        </div>
        
        {% if completed %}
            <div class="input-container">
                <button onclick="restartChat()" class="restart-btn">🔄 Start New Assessment</button>
            </div>
        {% endif %}
    </div>
    
    <script>
        const messagesContainer = document.getElementById('messages-container');
        const messageInput = document.getElementById('message-input');
        const sendBtn = document.getElementById('send-btn');
        
        function scrollToBottom() {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
        
        scrollToBottom();
        
        function sendMessage(predefinedAnswer = null) {
            let answer = predefinedAnswer || messageInput.value.trim();
            
            if (!answer && !predefinedAnswer) return;
            
            addMessageToUI('user', answer);
            
            if (!predefinedAnswer) {
                messageInput.value = '';
            }
            
            setInputEnabled(false);
            
            fetch('/send_message', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({answer: answer})
            })
            .then(response => response.json())
            .then(data => {
                setInputEnabled(true);
                
                if (data.status === 'completed') {
                    window.location.reload();
                } else if (data.status === 'phase_complete') {
                    window.location.reload();
                } else if (data.messages) {
                    data.messages.forEach(msg => {
                        addMessageToUI(msg.role, msg.content, msg.options);
                    });
                    scrollToBottom();
                }
            })
            .catch(error => {
                console.error('Error:', error);
                setInputEnabled(true);
                addMessageToUI('assistant', 'Sorry, there was an error. Please try again.');
            });
        }
        
        function addMessageToUI(role, content, options = null) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${role}`;
            
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            contentDiv.innerHTML = content.replace(/\\n/g, '<br>');
            
            if (options && options.length > 0) {
                const optionsDiv = document.createElement('div');
                optionsDiv.className = 'options-container';
                options.forEach(option => {
                    const btn = document.createElement('button');
                    btn.className = 'option-btn';
                    const cleanOption = option.replace(/\\n/g, ' ');
                    btn.textContent = cleanOption;
                    btn.onclick = () => sendMessage(option);
                    optionsDiv.appendChild(btn);
                });
                contentDiv.appendChild(optionsDiv);
            }
            
            messageDiv.appendChild(contentDiv);
            messagesContainer.appendChild(messageDiv);
            scrollToBottom();
        }
        
        function setInputEnabled(enabled) {
            messageInput.disabled = !enabled;
            sendBtn.disabled = !enabled;
            if (enabled) {
                messageInput.focus();
            }
        }
        
        function restartChat() {
            fetch('/restart_chat', {method: 'POST'})
            .then(() => window.location.reload());
        }
        
        messageInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
        
        messageInput.focus();
    </script>
</body>
</html>
""", messages=session["messages"], 
         waiting_for_answer=session["waiting_for_answer"],
         completed=session["completed"],
         phase=session.get("phase", 1))

@app.route("/send_message", methods=["POST"])
def send_message():
    init_session()
    
    if session.get("completed"):
        return jsonify({"status": "completed"})
    
    if not session.get("waiting_for_answer"):
        return jsonify({"status": "error", "message": "Not waiting for answer"})
    
    data = request.get_json()
    answer = data.get("answer", "").strip()
    
    if not answer:
        return jsonify({"status": "error", "message": "Please provide an answer"})
    
    # Check if we're in a proposal flow
    if session.get("pending_proposal"):
        proposal_data = session["pending_proposal"]
        prop_index = proposal_data.get("current_index", 0)
        prop_questions = proposal_data["questions"]
        
        if prop_index < len(prop_questions):
            prop_q = prop_questions[prop_index]
            answer_key = f"proposal_{proposal_data['original_ref']}_{prop_index}"
            
            if prop_q.get("type") in ["numeric", "number", "price", "counter"]:
                answer = clean_number(answer)
            
            session["answers"][answer_key] = answer
            
            proposal_data["current_index"] = prop_index + 1
            session["pending_proposal"] = proposal_data
            
            if prop_index + 1 >= len(prop_questions):
                session["pending_proposal"] = None
                session["waiting_for_answer"] = False
                
                original_ref = proposal_data["original_ref"]
                result = process_handler_next(original_ref, proposal_data["answer"])
                
                if result.get("status") == "completed":
                    complete_assessment()
                    return jsonify({"status": "completed"})
                elif result.get("status") == "phase_complete":
                    # Move to phase 2
                    session["phase"] = 2
                    session["current_ref"] = PHASE_2_QUESTIONS[0]
                    session["phase_transition_shown"] = False
                    session["waiting_for_answer"] = False
                    show_phase_transition()
                    process_next_question()
                    return jsonify({"status": "phase_complete", "messages": session["messages"][-2:]})
                elif result.get("next_ref"):
                    session["current_ref"] = result["next_ref"]
                    process_next_question()
                else:
                    next_ref = get_next_question_in_phase(original_ref)
                    if next_ref.get("status") == "phase_complete":
                        session["phase"] = 2
                        session["current_ref"] = PHASE_2_QUESTIONS[0]
                        session["phase_transition_shown"] = False
                        session["waiting_for_answer"] = False
                        show_phase_transition()
                        process_next_question()
                        return jsonify({"status": "phase_complete", "messages": session["messages"][-2:]})
                    elif next_ref.get("next_ref"):
                        session["current_ref"] = next_ref["next_ref"]
                        process_next_question()
                    else:
                        complete_assessment()
                        return jsonify({"status": "completed"})
            else:
                session["waiting_for_answer"] = False
                process_next_question()
            
            return jsonify({
                "status": "success",
                "messages": [session["messages"][-1]] if session["messages"] else []
            })
    
    # Regular question flow
    current_ref = session["current_ref"]
    question = get_question(current_ref)
    
    if not question:
        complete_assessment()
        return jsonify({"status": "completed"})
    
    if question.get("type") in ["numeric", "number", "price", "counter"]:
        answer = clean_number(answer)
    
    # Check for proposal first
    proposal_questions = handle_proposal(current_ref, answer)
    if proposal_questions:
        session["answers"][current_ref] = answer
        session["history"].append(current_ref)
        session["waiting_for_answer"] = False
        process_next_question()
        
        return jsonify({
            "status": "success",
            "messages": [session["messages"][-1]]
        })
    
    # Process handler
    result = process_handler_next(current_ref, answer)
    
    if result.get("status") == "error":
        add_message("assistant", f"❌ {result.get('message', 'Invalid answer. Please try again.')}")
        return jsonify({
            "status": "error",
            "messages": [session["messages"][-1]]
        })
    
    # Save answer
    session["answers"][current_ref] = answer
    session["history"].append(current_ref)
    session["waiting_for_answer"] = False
    
    # Handle phase complete
    if result.get("status") == "phase_complete":
        # Move to phase 2
        session["phase"] = 2
        session["current_ref"] = PHASE_2_QUESTIONS[0]
        session["phase_transition_shown"] = False
        show_phase_transition()
        process_next_question()
        return jsonify({"status": "phase_complete", "messages": session["messages"][-2:]})
    
    # Handle completion
    if result.get("status") == "completed":
        complete_assessment()
        return jsonify({"status": "completed"})
    
    # Move to next question
    if result.get("next_ref"):
        session["current_ref"] = result["next_ref"]
        process_next_question()
    else:
        next_in_phase = get_next_question_in_phase(current_ref)
        if next_in_phase.get("status") == "phase_complete":
            session["phase"] = 2
            session["current_ref"] = PHASE_2_QUESTIONS[0]
            session["phase_transition_shown"] = False
            show_phase_transition()
            process_next_question()
            return jsonify({"status": "phase_complete", "messages": session["messages"][-2:]})
        elif next_in_phase.get("next_ref"):
            session["current_ref"] = next_in_phase["next_ref"]
            process_next_question()
        else:
            complete_assessment()
            return jsonify({"status": "completed"})
    
    return jsonify({
        "status": "success",
        "messages": [session["messages"][-1]]
    })

@app.route("/restart_chat", methods=["POST"])
def restart_chat():
    session.clear()
    init_session()
    return jsonify({"status": "success"})

if __name__ == "__main__":
    app.run(debug=True)