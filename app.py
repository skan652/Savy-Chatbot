from flask import Flask, request, jsonify, render_template_string
from state_machine import StateMachineEngine
import json

app = Flask(__name__)

# Global engine instance (for demo; in production, use sessions)
engine = StateMachineEngine('response.json')

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
        button { padding: 5px 10px; }
        .bot { color: blue; }
        .user { color: green; text-align: right; }
    </style>
</head>
<body>
    <h1>Savy Chatbot</h1>
    <div id="chat"></div>
    <input type="text" id="message" placeholder="Type your answer...">
    <button onclick="sendMessage()">Send</button>
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

        function getQuestion() {
            fetch('/get_question')
                .then(response => response.json())
                .then(data => {
                    if (data.completed) {
                        addMessage('Questionnaire completed!', 'bot');
                        document.getElementById('message').disabled = true;
                    } else {
                        currentQuestion = data;
                        addMessage(data.question, 'bot');
                        if (data.type === 'single_choice') {
                            addMessage('Options: ' + data.options.join(', '), 'bot');
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

            let processedAnswer;
            if (currentQuestion.type === 'boolean') {
                processedAnswer = answer.toLowerCase() === 'yes' || answer.toLowerCase() === 'true';
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

        // Start the chat
        getQuestion();
    </script>
</body>
</html>
    """)

@app.route('/get_question')
def get_question():
    question = engine.get_current_question()
    if question:
        return jsonify(question)
    else:
        return jsonify({'completed': True})

@app.route('/answer', methods=['POST'])
def answer():
    data = request.get_json()
    answer = data.get('answer')
    result = engine.answer_question(answer)
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)