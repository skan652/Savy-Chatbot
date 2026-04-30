from flask import Flask, request, jsonify, render_template_string, session
from state_machine import StateMachineEngine
import json

app = Flask(__name__)
app.secret_key = 'savy-chatbot-secret-key'
engines = {}  # Store engines per session

def get_engine():
    """Get or create engine for current session"""
    session_id = session.get('_id')
    if session_id not in engines:
        engines[session_id] = StateMachineEngine('response.json')
    return engines[session_id]

@app.route('/')
def index():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Savy Chatbot</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }
        #chat { border: 1px solid #ccc; height: 400px; overflow-y: auto; padding: 10px; margin-bottom: 10px; }
        #message { width: 80%; padding: 5px; }
        button { padding: 5px 10px; margin: 2px; }
        .option-btn { background-color: #f0f0f0; border: 1px solid #ccc; padding: 8px 12px; margin: 2px; cursor: pointer; border-radius: 4px; }
        .option-btn:hover { background-color: #e0e0e0; }
        .bot { color: blue; }
        .user { color: green; text-align: right; }
        .options-container { margin: 10px 0; }
        .input-container { display: none; }
        .input-container.show { display: block; }
    </style>
</head>
<body>
    <h1>Savy Chatbot</h1>
    <div id="chat"></div>
    <div class="options-container" id="options"></div>
    <div class="input-container" id="input-container">
        <input type="text" id="message" placeholder="Type your answer...">
        <button onclick="sendMessage()">Send</button>
    </div>
    <script>
        let currentQuestion = null;

        function addMessage(text, sender) {
            const chat = document.getElementById('chat');
            const msg = document.createElement('div');
            msg.className = sender;
            msg.textContent = text;
            chat.appendChild(msg);
            chat.scrollTop = chat.scrollHeight;
        }

        function clearOptions() {
            const optionsContainer = document.getElementById('options');
            optionsContainer.innerHTML = '';
        }

        function showOptions(options) {
            const optionsContainer = document.getElementById('options');
            clearOptions();
            options.forEach((option, index) => {
                const btn = document.createElement('button');
                btn.className = 'option-btn';
                btn.textContent = `${index + 1}. ${option}`;
                btn.onclick = () => selectOption(option);
                optionsContainer.appendChild(btn);
            });
        }

        function showOptionsWithOther(options) {
            const optionsContainer = document.getElementById('options');
            clearOptions();
            options.forEach((option, index) => {
                const btn = document.createElement('button');
                btn.className = 'option-btn';
                btn.textContent = `${index + 1}. ${option}`;
                btn.onclick = () => selectOption(option);
                optionsContainer.appendChild(btn);
            });
            
            // Add "Other" button for numeric questions with options
            const otherBtn = document.createElement('button');
            otherBtn.className = 'option-btn';
            otherBtn.textContent = `${options.length + 1}. Other (specify)`;
            otherBtn.onclick = () => selectOtherOption();
            optionsContainer.appendChild(otherBtn);
        }

        function selectOption(option) {
            addMessage(option, 'user');
            clearOptions();
            sendAnswer(option);
        }

        function selectOtherOption() {
            clearOptions();
            document.getElementById('input-container').style.display = 'block';
            document.getElementById('message').placeholder = 'Enter a custom amount...';
            document.getElementById('message').type = 'number';
            document.getElementById('message').focus();
        }

        function getQuestion() {
            fetch('/get_question')
                .then(response => response.json())
                .then(data => {
                    if (data.completed) {
                        addMessage('Questionnaire completed!', 'bot');
                        document.getElementById('input-container').style.display = 'none';
                        // Add restart button
                        const restartBtn = document.createElement('button');
                        restartBtn.className = 'option-btn';
                        restartBtn.textContent = 'Start New Questionnaire';
                        restartBtn.onclick = () => restartQuestionnaire();
                        document.getElementById('options').appendChild(restartBtn);
                    } else {
                        currentQuestion = data;
                        addMessage(data.question, 'bot');
                        if (data.type === 'single_choice') {
                            showOptions(data.options);
                            document.getElementById('input-container').style.display = 'none';
                        } else if (data.type === 'boolean') {
                            showOptions(['Yes', 'No']);
                            document.getElementById('input-container').style.display = 'none';
                        } else if (data.type === 'number' && data.options) {
                            showOptionsWithOther(data.options);
                            document.getElementById('input-container').style.display = 'none';
                        } else if (data.type === 'number') {
                            document.getElementById('input-container').style.display = 'block';
                            document.getElementById('message').placeholder = 'Enter a number...';
                            document.getElementById('message').type = 'number';
                            document.getElementById('message').focus();
                        } else {
                            document.getElementById('input-container').style.display = 'block';
                        }
                    }
                });
        }

        function sendMessage() {
            const input = document.getElementById('message');
            const answer = input.value.trim();
            if (!answer) return;

            addMessage(answer, 'user');
            input.value = '';
            input.placeholder = 'Type your answer...';
            input.type = 'text'; // Reset type back to text

            sendAnswer(answer);
        }

        function initializeChat() {
            getQuestion();
        }

        document.addEventListener('DOMContentLoaded', initializeChat);
        document.addEventListener('keypress', (e) => {
            const input = document.getElementById('message');
            if (e.key === 'Enter' && input.offsetParent !== null && input.offsetParent !== undefined) {
                sendMessage();
            }
        });

        function sendAnswer(answer) {
            let processedAnswer;
            if (currentQuestion.type === 'boolean') {
                processedAnswer = answer.toLowerCase() === 'yes';
            } else if (currentQuestion.type === 'number') {
                processedAnswer = parseFloat(answer);
            } else {
                processedAnswer = answer;
            }

            fetch('/answer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ answer: processedAnswer })
            })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'error') {
                        addMessage(data.message, 'bot');
                    } else {
                        addMessage(data.message, 'bot');
                        getQuestion();
                    }
                });
        }

        function restartQuestionnaire() {
            // Clear session and restart
            fetch('/restart', { method: 'POST' })
                .then(() => {
                    // Clear chat and restart
                    document.getElementById('chat').innerHTML = '';
                    document.getElementById('options').innerHTML = '';
                    getQuestion();
                });
        }
    </script>
</body>
</html>
    """)

@app.route('/get_question')
def get_question():
    engine = get_engine()
    question = engine.get_current_question()
    if question:
        return jsonify(question)
    else:
        return jsonify({'completed': True})

@app.route('/answer', methods=['POST'])
def answer():
    data = request.get_json()
    answer_value = data.get('answer')
    
    engine = get_engine()
    result = engine.answer_question(answer_value)
    
    return jsonify(result)

@app.route('/restart', methods=['POST'])
def restart():
    # Clear engine for current session
    session_id = session.get('_id')
    if session_id in engines:
        del engines[session_id]
    session.clear()
    return jsonify({'status': 'restarted'})

if __name__ == '__main__':
    app.run(debug=True)