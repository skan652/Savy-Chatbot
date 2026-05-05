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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            width: 100%;
            max-width: 600px;
            display: flex;
            flex-direction: column;
            height: 90vh;
            max-height: 800px;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px 20px;
            border-radius: 20px 20px 0 0;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }
        
        .header h1 {
            font-size: 28px;
            font-weight: 600;
            margin-bottom: 5px;
        }
        
        .header p {
            font-size: 14px;
            opacity: 0.9;
        }
        
        #chat {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            background: #f8f9fa;
        }
        
        #chat::-webkit-scrollbar {
            width: 8px;
        }
        
        #chat::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 10px;
        }
        
        #chat::-webkit-scrollbar-thumb {
            background: #667eea;
            border-radius: 10px;
        }
        
        #chat::-webkit-scrollbar-thumb:hover {
            background: #764ba2;
        }
        
        .bot, .user {
            padding: 12px 16px;
            border-radius: 14px;
            max-width: 80%;
            word-wrap: break-word;
            animation: slideIn 0.3s ease-out;
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .bot {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            align-self: flex-start;
            border-radius: 14px 14px 14px 0;
            box-shadow: 0 2px 8px rgba(102, 126, 234, 0.2);
        }
        
        .user {
            background: #e8f0fe;
            color: #1f2937;
            align-self: flex-end;
            border-radius: 14px 14px 0 14px;
            text-align: right;
            border-left: 3px solid #667eea;
        }
        
        .options-container {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            padding: 0 20px;
            justify-content: center;
        }
        
        .option-btn {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            border: none;
            padding: 12px 20px;
            border-radius: 25px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(245, 87, 108, 0.2);
        }
        
        .option-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(245, 87, 108, 0.35);
        }
        
        .option-btn:active {
            transform: translateY(0);
        }
        
        .input-container {
            display: none;
            padding: 20px;
            border-top: 1px solid #e0e0e0;
            background: white;
            border-radius: 0 0 20px 20px;
            gap: 10px;
        }
        
        .input-container.show {
            display: flex;
        }
        
        #message {
            flex: 1;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 25px;
            font-size: 14px;
            outline: none;
            transition: all 0.3s ease;
            font-family: inherit;
        }
        
        #message:focus {
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        
        #message::placeholder {
            color: #999;
        }
        
        .send-btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 28px;
            border-radius: 25px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
        }
        
        .send-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
        }
        
        .send-btn:active {
            transform: translateY(0);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>💬 Savy Chatbot</h1>
            <p>Financial Information Questionnaire</p>
        </div>
        <div id="chat"></div>
        <div class="options-container" id="options"></div>
        <div class="input-container" id="input-container">
            <input type="text" id="message" placeholder="Type your answer...">
            <button class="send-btn" onclick="sendMessage()">Send</button>
        </div>
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
                        addMessage('✅ Questionnaire completed! Thank you for your responses.', 'bot');
                        document.getElementById('input-container').style.display = 'none';
                        // Add restart button
                        const restartBtn = document.createElement('button');
                        restartBtn.className = 'option-btn';
                        restartBtn.textContent = '🔄 Start New Questionnaire';
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