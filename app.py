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

def get_question(ref):
    return QUESTION_MAP.get(str(ref))

def clean_number(value):
    if value is None:
        return None
    # Remove £, commas, spaces
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
        # Clean up options (remove newlines)
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
        # If no handler, just move to next sequential question
        next_ref = str(int(current_ref) + 1)
        if get_question(next_ref):
            return {"status": "success", "next_ref": next_ref, "completed": False}
        return {"status": "completed"}
    
    # Clean answer for matching (remove newlines, extra spaces)
    clean_answer = answer.replace('\n', ' ').strip()
    
    # Find matching handler
    handler = None
    for key, value in question["handlerNext"].items():
        clean_key = key.replace('\n', ' ').strip()
        if clean_key == clean_answer:
            handler = value
            break
    
    if not handler:
        # Try to find by partial match
        for key, value in question["handlerNext"].items():
            if clean_answer in key.replace('\n', ' '):
                handler = value
                break
    
    if not handler:
        next_ref = str(int(current_ref) + 1)
        if get_question(next_ref):
            return {"status": "success", "next_ref": next_ref, "completed": False}
        return {"status": "completed"}
    
    action = handler.get("action")
    
    if action == "navigate_to_screen":
        # Check if it's a completion or continuation
        ref_path = handler.get("ref", "")
        if "StartRefund" in ref_path:
            # This might mean completion or continue to next section
            # Check if there are more questions after this
            next_ref = str(int(current_ref) + 1)
            if get_question(next_ref):
                return {"status": "success", "next_ref": next_ref, "completed": False}
            return {"status": "completed"}
        return {"status": "completed"}
    
    elif action == "open_question":
        next_ref = handler.get("ref")
        return {"status": "success", "next_ref": str(next_ref), "completed": False}
    
    elif action == "to_save_and_finish":
        return {"status": "completed"}
    
    elif action == "to_save_and_finish_with_error":
        return {"status": "completed"}
    
    else:
        next_ref = str(int(current_ref) + 1)
        if get_question(next_ref):
            return {"status": "success", "next_ref": next_ref, "completed": False}
        return {"status": "completed"}

def handle_proposal(current_ref, answer):
    """Handle proposal questions (like q5 with nested questions)"""
    question = get_question(current_ref)
    if not question or "proposal" not in question:
        return None
    
    proposal = question.get("proposal", {})
    clean_answer = answer.replace('\n', ' ').strip()
    
    # Find matching proposal
    for key, proposal_questions in proposal.items():
        clean_key = key.replace('\n', ' ').strip()
        if clean_key == clean_answer or clean_answer in clean_key:
            # Store that we need to ask follow-up questions
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
            # Ask the next proposal question
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

def complete_assessment():
    """Complete the assessment and show summary"""
    session["completed"] = True
    session["waiting_for_answer"] = False
    
    answers = session.get("answers", {})
    
    # Check if user qualifies (based on q13)
    qualifies = False
    if "13" in answers and answers["13"] == "Yes":
        qualifies = True
    
    summary = "🎉 **Assessment Complete!** 🎉\n\n"
    
    if qualifies:
        summary += "✅ **Good news!** Based on your answers, you may be eligible for a tax refund.\n\n"
    else:
        summary += "📋 **Assessment Summary**\n\n"
    
    summary += "**Your responses:**\n\n"
    
    # Show all answers in order
    question_order = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"]
    for ref in question_order:
        if ref in answers:
            question = get_question(ref)
            if question:
                summary += f"• **{question.get('title', ref)}**\n"
                summary += f"  → {answers[ref]}\n\n"
    
    # Show proposal answers
    for key, value in answers.items():
        if key.startswith("proposal_"):
            summary += f"• **Additional info**: {value}\n\n"
    
    if qualifies:
        summary += "📞 **Next steps:** A tax specialist will contact you shortly to discuss your refund.\n\n"
    else:
        summary += "💡 Based on your responses, you may not qualify at this time. "
        summary += "Keep track of your work expenses for future tax years!\n\n"
    
    summary += "Click 'Start New Assessment' below to begin again."
    
    add_message("assistant", summary)

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
        welcome_msg = "👋 Hello! I'm your Tax Assistant. I'll help you determine your eligibility for tax refunds and savings.\n\nLet's get started with a few questions about your income and work travel."
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
         completed=session["completed"])

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
            # Save proposal answer
            prop_q = prop_questions[prop_index]
            answer_key = f"proposal_{proposal_data['original_ref']}_{prop_index}"
            
            # Clean numeric if needed
            if prop_q.get("type") in ["numeric", "number", "price", "counter"]:
                answer = clean_number(answer)
            
            session["answers"][answer_key] = answer
            
            # Move to next proposal question
            proposal_data["current_index"] = prop_index + 1
            session["pending_proposal"] = proposal_data
            
            if prop_index + 1 >= len(prop_questions):
                # All proposal questions answered, clear pending and continue
                session["pending_proposal"] = None
                session["waiting_for_answer"] = False
                
                # Continue with main flow - get next question from original handler
                original_ref = proposal_data["original_ref"]
                result = process_handler_next(original_ref, proposal_data["answer"])
                
                if result.get("status") == "completed":
                    complete_assessment()
                    return jsonify({"status": "completed"})
                elif result.get("next_ref"):
                    session["current_ref"] = result["next_ref"]
                    process_next_question()
                else:
                    # Try to go to next sequential question
                    next_ref = str(int(original_ref) + 1)
                    if get_question(next_ref):
                        session["current_ref"] = next_ref
                        process_next_question()
                    else:
                        complete_assessment()
                        return jsonify({"status": "completed"})
            else:
                # Ask next proposal question
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
    
    # Clean number if needed
    if question.get("type") in ["numeric", "number", "price", "counter"]:
        answer = clean_number(answer)
    
    # Check for proposal first
    proposal_questions = handle_proposal(current_ref, answer)
    if proposal_questions:
        # Save the answer to the main question
        session["answers"][current_ref] = answer
        session["history"].append(current_ref)
        session["waiting_for_answer"] = False
        
        # Start proposal flow
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
    
    # Handle completion
    if result.get("status") == "completed" or result.get("completed"):
        complete_assessment()
        return jsonify({"status": "completed"})
    
    # Move to next question
    if result.get("next_ref"):
        session["current_ref"] = result["next_ref"]
        process_next_question()
    else:
        # Try to go to next sequential question
        next_ref = str(int(current_ref) + 1)
        if get_question(next_ref):
            session["current_ref"] = next_ref
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