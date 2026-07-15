from flask import Flask, request, redirect, url_for, jsonify, session
from flask import render_template_string
from flasgger import Swagger, swag_from
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
import json
import re
import logging
from datetime import datetime, timedelta
from functools import wraps
from pyngrok import ngrok
import inspect
import os
import time
import requests
import uuid


# Load .env BEFORE importing ai_client to ensure env vars are set
dotenv_path = os.path.join(os.getcwd(), ".env")
if os.path.exists(dotenv_path):
    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
    except Exception as e:
        print(f"Warning: Could not load .env file: {e}")

from ai_client import AIClient
from state_machine import StateMachineEngine

ai_client = AIClient()
state_engine = StateMachineEngine("response.json")

# Enable AI summary generation by default
if "USE_AI" not in os.environ:
    os.environ["USE_AI"] = "true"

app = Flask(__name__)
app.secret_key = "savy-chatbot-secret-key"
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 3600

# =========================================================
# AUTHENTIFICATION SWAGGER
# =========================================================

# Configuration des utilisateurs Swagger
SWAGGER_USERS = {
    "admin": generate_password_hash("savypass123"),
    "demo": generate_password_hash("demopass123")
}

auth = HTTPBasicAuth()

@auth.verify_password
def verify_password(username, password):
    """Vérifie le mot de passe pour l'accès à Swagger"""
    if username in SWAGGER_USERS and check_password_hash(SWAGGER_USERS.get(username), password):
        return username
    return None

# =========================================================
# SWAGGER CONFIGURATION
# =========================================================

app.config['SWAGGER'] = {
    'title': 'SAVY Tax Assistant API',
    'description': '''
    API for the SAVY Tax Assessment Bot.
    
    🔒 **Authentification requise pour accéder à cette documentation**
    Utilisez les identifiants suivants :
    - Utilisateur: `admin`
    - Mot de passe: `savypass123`
    ''',
    'version': '1.0.0',
    'termsOfService': 'https://savyapp.dev/terms',
    'contact': {
        'name': 'SAVY Support',
        'email': 'support@savyapp.dev',
        'url': 'https://savyapp.dev'
    },
    'license': {
        'name': 'MIT',
        'url': 'https://opensource.org/licenses/MIT'
    },
    'tags': [
        {'name': 'Authentication', 'description': '🔐 Authentification endpoints'},
        {'name': 'Chat', 'description': '💬 Chat endpoints'},
        {'name': 'Estimations', 'description': '📊 Estimation endpoints'},
        {'name': 'Questions', 'description': '❓ Question management'},
        {'name': 'Conversations', 'description': '📁 Conversation management'}
    ],
    'securityDefinitions': {
        'BearerAuth': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
            'description': 'JWT token for authentication. Format: Bearer <token>'
        }
    },
    'security': [
        {'BearerAuth': []}
    ],
    'specs_route': '/apidocs/',
    'uiversion': 3,
    'swagger_ui_bundle_js': '//unpkg.com/swagger-ui-dist@3/swagger-ui-bundle.js',
    'swagger_ui_standalone_preset_js': '//unpkg.com/swagger-ui-dist@3/swagger-ui-standalone-preset.js',
    'swagger_ui_css': '//unpkg.com/swagger-ui-dist@3/swagger-ui.css',
}

# Initialiser Swagger
swagger = Swagger(app)

# =========================================================
# PROTECTION DE L'INTERFACE SWAGGER
# =========================================================

@app.before_request
def protect_swagger():
    """Protège l'interface Swagger avec une authentification HTTP"""
    if request.path.startswith('/apidocs/') or request.path == '/apidocs' or request.path == '/swagger_spec' or request.path == '/apispec.json':
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return auth.login_required(lambda: None)()
    # Permettre l'accès au serveur Swagger
    if request.path.startswith('/flasgger_static/'):
        return None
    
# =========================================================
# PAGE DE LOGIN SWAGGER PERSONNALISÉE
# =========================================================

@app.route('/apidocs/login', methods=['GET', 'POST'])
def swagger_login():
    """Page de login pour Swagger"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in SWAGGER_USERS and check_password_hash(SWAGGER_USERS.get(username), password):
            # Créer une session pour Swagger
            session['swagger_authenticated'] = True
            session['swagger_user'] = username
            return redirect(url_for('apidocs_redirect'))
        else:
            return render_template_string("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Login - Swagger API Documentation</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    * { box-sizing: border-box; }
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                        background: linear-gradient(135deg, #1a1a2e, #16213e);
                        margin: 0;
                        padding: 20px;
                        min-height: 100vh;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    }
                    .container {
                        background: white;
                        max-width: 400px;
                        width: 100%;
                        padding: 40px;
                        border-radius: 16px;
                        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                        text-align: center;
                    }
                    .logo {
                        font-size: 2em;
                        font-weight: 700;
                        color: #1a1a2e;
                        margin-bottom: 5px;
                    }
                    .logo span { color: #d63384; }
                    .subtitle {
                        color: #666;
                        margin-bottom: 30px;
                        font-size: 0.9em;
                    }
                    input {
                        width: 100%;
                        padding: 14px;
                        border: 2px solid #e0e0e0;
                        border-radius: 12px;
                        font-size: 1em;
                        margin-bottom: 15px;
                        transition: border-color 0.3s ease;
                    }
                    input:focus {
                        outline: none;
                        border-color: #d63384;
                    }
                    button {
                        width: 100%;
                        padding: 14px;
                        background: linear-gradient(45deg, #d63384, #a02070);
                        color: white;
                        border: none;
                        border-radius: 12px;
                        font-size: 1.1em;
                        cursor: pointer;
                        font-weight: 600;
                        transition: transform 0.2s ease, box-shadow 0.2s ease;
                    }
                    button:hover {
                        transform: translateY(-2px);
                        box-shadow: 0 10px 20px rgba(214, 51, 132, 0.3);
                    }
                    .error {
                        background: #fee;
                        padding: 12px;
                        border-radius: 12px;
                        color: #c33;
                        margin-bottom: 20px;
                        font-size: 0.9em;
                    }
                    .credits {
                        margin-top: 20px;
                        padding: 15px;
                        background: #f8f8fa;
                        border-radius: 12px;
                        font-size: 0.85em;
                        color: #666;
                        text-align: left;
                    }
                    .credits strong { color: #333; }
                    .credits code {
                        background: #f0f0f0;
                        padding: 2px 8px;
                        border-radius: 4px;
                        font-size: 0.85em;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="logo">SAV<span>Y</span></div>
                    <p class="subtitle">🔒 API Documentation Access</p>
                    <div class="error">❌ Invalid credentials. Please try again.</div>
                    <form method="POST">
                        <input type="text" name="username" placeholder="Username" required autofocus>
                        <input type="password" name="password" placeholder="Password" required>
                        <button type="submit">Access Documentation</button>
                    </form>
                    <div class="credits">
                        <strong>🔑 Default Credentials:</strong><br>
                        Username: <code>admin</code><br>
                        Password: <code>savypass123</code>
                    </div>
                </div>
            </body>
            </html>
            """)
    
    # GET request - show login form
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login - Swagger API Documentation</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                background: linear-gradient(135deg, #1a1a2e, #16213e);
                margin: 0;
                padding: 20px;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .container {
                background: white;
                max-width: 400px;
                width: 100%;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                text-align: center;
            }
            .logo {
                font-size: 2em;
                font-weight: 700;
                color: #1a1a2e;
                margin-bottom: 5px;
            }
            .logo span { color: #d63384; }
            .subtitle {
                color: #666;
                margin-bottom: 30px;
                font-size: 0.9em;
            }
            input {
                width: 100%;
                padding: 14px;
                border: 2px solid #e0e0e0;
                border-radius: 12px;
                font-size: 1em;
                margin-bottom: 15px;
                transition: border-color 0.3s ease;
            }
            input:focus {
                outline: none;
                border-color: #d63384;
            }
            button {
                width: 100%;
                padding: 14px;
                background: linear-gradient(45deg, #d63384, #a02070);
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 1.1em;
                cursor: pointer;
                font-weight: 600;
                transition: transform 0.2s ease, box-shadow 0.2s ease;
            }
            button:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(214, 51, 132, 0.3);
            }
            .credits {
                margin-top: 20px;
                padding: 15px;
                background: #f8f8fa;
                border-radius: 12px;
                font-size: 0.85em;
                color: #666;
                text-align: left;
            }
            .credits strong { color: #333; }
            .credits code {
                background: #f0f0f0;
                padding: 2px 8px;
                border-radius: 4px;
                font-size: 0.85em;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">SAV<span>Y</span></div>
            <p class="subtitle">🔒 API Documentation Access</p>
            <form method="POST">
                <input type="text" name="username" placeholder="Username" required autofocus>
                <input type="password" name="password" placeholder="Password" required>
                <button type="submit">Access Documentation</button>
            </form>
            <div class="credits">
                <strong>🔑 Default Credentials:</strong><br>
                Username: <code>admin</code><br>
                Password: <code>savypass123</code>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/apidocs/redirect')
def apidocs_redirect():
    """Redirection vers Swagger UI après login"""
    if not session.get('swagger_authenticated'):
        return redirect(url_for('swagger_login'))
    return redirect('/apidocs/')

# =========================================================
# PROTECTION DES ROUTES SWAGGER AVEC AUTH
# =========================================================

# Modifier la route de swagger pour utiliser l'authentification
@app.route('/apidocs/', defaults={'path': ''})
@app.route('/apidocs/<path:path>')
@auth.login_required
def protected_apidocs(path):
    """Route protégée pour Swagger UI"""
    # Rediriger vers le vrai endpoint Swagger
    return redirect(f'/flasgger_ui/{path}' if path else '/flasgger_ui/')

# Ajouter une route pour la spécification
@app.route('/swagger_spec')
@auth.login_required
def protected_swagger_spec():
    """Route protégée pour la spécification Swagger"""
    return redirect('/apispec.json')    
# =========================================================
# Set up logging
# =========================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VALID_PASSKEYS = ["12345", "pass123"]

# SAVY Brand Color
SAVY_PINK = "#d63384"
SAVY_GRADIENT = f"linear-gradient(45deg, {SAVY_PINK}, #a02070)"

# =========================================================
# CONVERSATION STORAGE
# =========================================================

# In-memory storage for conversations (in production, use a database)
conversations = {}
conversation_folders = {
    "Today": [],
    "Yesterday": [],
    "Previous 7 Days": [],
    "Older": []
}

def get_conversation_id():
    """Generate a unique conversation ID"""
    return str(uuid.uuid4())[:8]

def save_conversation(conversation_id, messages, answers, history, phase, completed):
    """Save conversation to storage"""
    conversations[conversation_id] = {
        "id": conversation_id,
        "messages": messages,
        "answers": answers,
        "history": history,
        "phase": phase,
        "completed": completed,
        "last_updated": datetime.now().isoformat(),
        "title": generate_conversation_title(messages, answers),
        "folder": categorize_conversation()
    }
    return conversation_id

def get_conversation(conversation_id):
    """Get conversation from storage"""
    return conversations.get(conversation_id)

def get_all_conversations():
    """Get all conversations organized by folder"""
    organized = {
        "Today": [],
        "Yesterday": [],
        "Previous 7 Days": [],
        "Older": []
    }
    
    for conv_id, conv in conversations.items():
        folder = conv.get("folder", "Older")
        if folder in organized:
            organized[folder].append(conv)
        else:
            organized["Older"].append(conv)
    
    # Sort each folder by last_updated (newest first)
    for folder in organized:
        organized[folder].sort(key=lambda x: x.get("last_updated", ""), reverse=True)
    
    return organized

def generate_conversation_title(messages, answers=None):
    """Generate a unique title for the conversation using sequential numbering"""
    conv_count = len(conversations)
    title = f"Inquiry #{conv_count + 1}"
    
    if answers:
        for ref, answer in answers.items():
            question = QUESTION_MAP.get(str(ref))
            if question:
                title_text = question.get("title", "")
                if callable(title_text):
                    try:
                        title_text = title_text({})
                    except:
                        title_text = "Question"
                
                if title_text and "How much do you earn" in title_text:
                    answer_str = str(answer).replace('\n', ' ').strip()
                    if "Under" in answer_str:
                        return f"Inquiry #{conv_count + 1} - Income: Under £14k"
                    elif "Between" in answer_str:
                        return f"Inquiry #{conv_count + 1} - Income: £14k-£50k"
                    elif "Over" in answer_str:
                        return f"Inquiry #{conv_count + 1} - Income: Over £50k"
                elif title_text and "travel for work" in title_text.lower():
                    answer_str = str(answer).replace('\n', ' ').strip()
                    return f"Inquiry #{conv_count + 1} - Travel: {answer_str}"
                elif title_text and "work journeys" in title_text.lower():
                    answer_str = str(answer).replace('\n', ' ').strip()
                    if len(answer_str) > 20:
                        return f"Inquiry #{conv_count + 1} - Work Journeys"
                    else:
                        return f"Inquiry #{conv_count + 1} - {answer_str}"
                elif title_text and "miles" in title_text.lower():
                    return f"Inquiry #{conv_count + 1} - Mileage: {str(answer).strip()} miles"
                elif title_text and "earn more than" in title_text.lower():
                    answer_str = str(answer).replace('\n', ' ').strip()
                    return f"Inquiry #{conv_count + 1} - Past Income: {answer_str}"
                elif title_text:
                    clean_title = title_text.replace('\n', ' ').strip()
                    if len(clean_title) > 30:
                        return f"Inquiry #{conv_count + 1} - {clean_title[:27]}..."
                    else:
                        return f"Inquiry #{conv_count + 1} - {clean_title}"
    
    if messages:
        for msg in messages:
            if msg.get("role") == "assistant":
                content = msg.get("content", "").replace('\n', ' ').strip()
                if "welcome" not in content.lower() and "good morning" not in content.lower():
                    if "?" in content:
                        question_text = content.split("?")[0].strip()
                        if len(question_text) > 10:
                            if len(question_text) > 30:
                                return f"Inquiry #{conv_count + 1} - {question_text[:27]}..."
                            return f"Inquiry #{conv_count + 1} - {question_text}"
                    break
    
    return title

def categorize_conversation():
    """Categorize conversation into folders based on date"""
    now = datetime.now()
    conv_date = datetime.now()
    
    if conv_date.date() == now.date():
        return "Today"
    elif conv_date.date() == (now - timedelta(days=1)).date():
        return "Yesterday"
    elif (now - conv_date).days <= 7:
        return "Previous 7 Days"
    else:
        return "Older"

# =========================================================
# SAVY API INTEGRATION
# =========================================================

SAVY_API_BASE_URL = os.environ.get("SAVY_API_BASE_URL", "https://api.savyapp.dev")
SAVY_TOKEN = os.environ.get("SAVY_TOKEN")
SAVY_USER_ID = os.environ.get("SAVY_USER_ID")

def get_savy_headers():
    """Get headers for Savy API requests"""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    if SAVY_TOKEN:
        headers["Authorization"] = f"Bearer {SAVY_TOKEN}"
    else:
        logger.warning("No Savy token found in environment")
    return headers

def make_savy_request(endpoint, method="GET", data=None, params=None):
    """Make a request to the Savy API"""
    url = f"{SAVY_API_BASE_URL}/{endpoint.lstrip('/')}"
    headers = get_savy_headers()
    
    logger.info(f"📡 Making {method} request to: {url}")
    if data:
        logger.info(f"📦 Request data: {json.dumps(data, indent=2)[:200]}...")
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, params=params, timeout=30)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=30)
        elif method.upper() == "PATCH":
            response = requests.patch(url, headers=headers, json=data, timeout=30)
        elif method.upper() == "PUT":
            response = requests.put(url, headers=headers, json=data, timeout=30)
        elif method.upper() == "DELETE":
            response = requests.delete(url, headers=headers, timeout=30)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        logger.info(f"📥 Response status: {response.status_code}")
        
        if response.status_code == 401:
            logger.error("Authentication failed. Token may be expired.")
            return {"error": "Authentication failed", "status": 401}
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Savy API error: {e}")
        if hasattr(e, 'response') and e.response:
            logger.error(f"Response: {e.response.text[:500]}")
            try:
                return e.response.json()
            except:
                return {"error": str(e), "status": e.response.status_code if hasattr(e.response, 'status_code') else None}
        return {"error": str(e)}

# =========================================================
# SAVY API - AUTHENTICATION (Step 1)
# =========================================================

def authenticate_savy_user(email, password):
    """
    Step 1: Authenticate user and get token + user ID
    POST /api/v1/auth/email/login
    """
    try:
        logger.info("🔐 Authenticating user with Savy API...")
        
        login_data = {
            "email": email,
            "password": password
        }
        
        response = make_savy_request("api/v1/auth/email/login", "POST", login_data)
        
        if response and not response.get("error"):
            token = response.get("token") or response.get("accessToken") or response.get("access_token")
            user_id = response.get("userId") or response.get("user") and response.get("user").get("id") or response.get("id")
            
            if token:
                env_path = os.path.join(os.getcwd(), ".env")
                env_vars = {}
                
                if os.path.exists(env_path):
                    with open(env_path, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip() and "=" in line:
                                key, value = line.split("=", 1)
                                env_vars[key.strip()] = value.strip().strip('"').strip("'")
                
                env_vars["SAVY_TOKEN"] = token
                if user_id:
                    env_vars["SAVY_USER_ID"] = str(user_id)
                
                with open(env_path, "w", encoding="utf-8") as f:
                    for key, value in env_vars.items():
                        f.write(f'{key}="{value}"\n')
                
                os.environ["SAVY_TOKEN"] = token
                if user_id:
                    os.environ["SAVY_USER_ID"] = str(user_id)
                
                global SAVY_TOKEN, SAVY_USER_ID
                SAVY_TOKEN = token
                SAVY_USER_ID = str(user_id) if user_id else None
                
                logger.info(f"✅ Authentication successful! Token saved. User ID: {user_id}")
                
                return {
                    "success": True,
                    "token": token,
                    "user_id": user_id,
                    "data": response
                }
            else:
                logger.error(f"❌ No token in response: {response}")
                return {
                    "success": False,
                    "error": "No token received"
                }
        else:
            logger.error(f"❌ Authentication failed: {response}")
            return {
                "success": False,
                "error": response
            }
            
    except Exception as e:
        logger.error(f"❌ Error authenticating user: {e}")
        return {
            "success": False,
            "error": str(e)
        }

# =========================================================
# SAVY API - REFUND ESTIMATION
# =========================================================

def initiate_refund_estimation():
    """
    Initiate a refund estimation with empty body
    POST /api/v1/refund-estimations
    """
    try:
        logger.info("🔄 Initiating refund estimation with Savy API...")
        
        response = make_savy_request("api/v1/refund-estimations", "POST", {})
        
        if response and not response.get("error"):
            estimation_id = response.get("id") or response.get("estimationId") or response.get("_id")
            logger.info(f"✅ Refund estimation initiated successfully! ID: {estimation_id}")
            
            if estimation_id:
                session["refund_estimation_id"] = estimation_id
                session.modified = True
            
            return {
                "success": True,
                "data": response,
                "estimation_id": estimation_id
            }
        else:
            logger.error(f"❌ Failed to initiate refund estimation: {response}")
            return {
                "success": False,
                "error": response
            }
            
    except Exception as e:
        logger.error(f"❌ Error initiating refund estimation: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def update_refund_estimation(estimation_id, answer_data):
    """
    Update the refund estimation in real-time with client answers
    PATCH /api/v1/refund-estimations/{id}
    """
    try:
        if not estimation_id:
            logger.warning("No estimation ID available to update")
            return {"success": False, "error": "No estimation ID"}
        
        logger.info(f"🔄 Updating refund estimation {estimation_id} with answer data...")
        
        response = make_savy_request(f"api/v1/refund-estimations/{estimation_id}", "PATCH", answer_data)
        
        if response and not response.get("error"):
            logger.info(f"✅ Refund estimation {estimation_id} updated successfully")
            return {
                "success": True,
                "data": response,
                "estimation_id": estimation_id
            }
        else:
            logger.error(f"❌ Failed to update refund estimation: {response}")
            return {
                "success": False,
                "error": response
            }
            
    except Exception as e:
        logger.error(f"❌ Error updating refund estimation: {e}")
        return {
            "success": False,
            "error": str(e)
        }

# =========================================================
# SAVY API - TAX ESTIMATION (Steps 2-3)
# =========================================================

def initiate_tax_estimation():
    """
    Step 2: Initiate a tax estimation with user ID and start date
    POST /api/v1/estimations
    Body: { "userId": "user_id", "startDate": "2024-01-01" }
    """
    try:
        logger.info("🔄 Initiating tax estimation with Savy API...")
        
        user_id = SAVY_USER_ID or session.get("savy_user_id")
        
        if not user_id:
            logger.error("❌ No user ID available for estimation")
            return {
                "success": False,
                "error": "No user ID available. Please authenticate first."
            }
        
        estimation_data = {
            "userId": user_id,
            "startDate": datetime.now().strftime("%Y-%m-%d")
        }
        
        logger.info(f"📦 Estimation data: {json.dumps(estimation_data, indent=2)}")
        
        response = make_savy_request("api/v1/estimations", "POST", estimation_data)
        
        if response and not response.get("error"):
            estimation_id = response.get("id") or response.get("estimationId") or response.get("_id")
            logger.info(f"✅ Tax estimation initiated successfully! ID: {estimation_id}")
            
            if estimation_id:
                session["tax_estimation_id"] = estimation_id
                session.modified = True
            
            return {
                "success": True,
                "data": response,
                "estimation_id": estimation_id
            }
        else:
            logger.error(f"❌ Failed to initiate tax estimation: {response}")
            return {
                "success": False,
                "error": response
            }
            
    except Exception as e:
        logger.error(f"❌ Error initiating tax estimation: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def update_tax_estimation(estimation_id, answer_data):
    """
    Step 3: Update the tax estimation in real-time with client answers
    PATCH /api/v1/estimations/{id}
    """
    try:
        if not estimation_id:
            logger.warning("No estimation ID available to update")
            return {"success": False, "error": "No estimation ID"}
        
        logger.info(f"🔄 Updating tax estimation {estimation_id} with answer data...")
        
        response = make_savy_request(f"api/v1/estimations/{estimation_id}", "PATCH", answer_data)
        
        if response and not response.get("error"):
            logger.info(f"✅ Tax estimation {estimation_id} updated successfully")
            return {
                "success": True,
                "data": response,
                "estimation_id": estimation_id
            }
        else:
            logger.error(f"❌ Failed to update tax estimation: {response}")
            return {
                "success": False,
                "error": response
            }
            
    except Exception as e:
        logger.error(f"❌ Error updating tax estimation: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def get_tax_estimation(estimation_id):
    """
    Get a specific tax estimation by ID
    GET /api/v1/estimations/{id}
    """
    try:
        if not estimation_id:
            return {"success": False, "error": "No estimation ID"}
        
        logger.info(f"📊 Getting tax estimation {estimation_id}...")
        
        response = make_savy_request(f"api/v1/estimations/{estimation_id}", "GET")
        
        if response and not response.get("error"):
            return {
                "success": True,
                "data": response
            }
        else:
            logger.error(f"❌ Failed to get tax estimation: {response}")
            return {
                "success": False,
                "error": response
            }
            
    except Exception as e:
        logger.error(f"❌ Error getting tax estimation: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def get_all_tax_estimations():
    """
    Get all tax estimations for the current user
    GET /api/v1/estimations
    """
    try:
        logger.info("📊 Getting all tax estimations...")
        
        response = make_savy_request("api/v1/estimations", "GET")
        
        if response and not response.get("error"):
            return {
                "success": True,
                "data": response
            }
        else:
            logger.error(f"❌ Failed to get tax estimations: {response}")
            return {
                "success": False,
                "error": response
            }
            
    except Exception as e:
        logger.error(f"❌ Error getting tax estimations: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def delete_tax_estimation(estimation_id):
    """
    Delete a tax estimation
    DELETE /api/v1/estimations/{id}
    """
    try:
        if not estimation_id:
            return {"success": False, "error": "No estimation ID"}
        
        logger.info(f"🗑️ Deleting tax estimation {estimation_id}...")
        
        response = make_savy_request(f"api/v1/estimations/{estimation_id}", "DELETE")
        
        if response and not response.get("error"):
            logger.info(f"✅ Tax estimation {estimation_id} deleted successfully")
            return {
                "success": True,
                "data": response
            }
        else:
            logger.error(f"❌ Failed to delete tax estimation: {response}")
            return {
                "success": False,
                "error": response
            }
            
    except Exception as e:
        logger.error(f"❌ Error deleting tax estimation: {e}")
        return {
            "success": False,
            "error": str(e)
        }

# =========================================================
# LOAD QUESTIONS
# =========================================================

def get_questions_list():
    """Returns the questions exactly as defined in the TypeScript code"""
    return [
        {
            "ref": "1",
            "progress": 5,
            "title": "How much do you earn a year?",
            "type": "radiov2",
            "field_name": "income",
            "name": "q_1",
            "options": ["Under\n£14k", "Between\n£14k & £50k", "Over\n£50k"],
            "required": True,
            "infoTitle": "Why we need to know",
            "info": "The amount you can save depends on which tax band you're in.",
            "value": "",
            "handlerNext": {
                "Under\n£14k": {
                    "action": "navigate_to_screen",
                    "ref": "/estimation-wizard/start-refund/StartRefund",
                    "params": {"edit_response": True}
                },
                "Between\n£14k & £50k": {
                    "action": "open_question",
                    "ref": "2"
                },
                "Over\n£50k": {
                    "action": "open_question",
                    "ref": "2"
                }
            },
            "xhrParams": lambda q: {
                "income": 1 if q["value"] == "Under\n£14k" else (2 if q["value"] == "Between\n£14k & £50k" else 3),
                "status": "Completed" if q["value"] == "Under\n£14k" else "In progress"
            }
        },
        {
            "ref": "2",
            "progress": 15,
            "title": "Do you travel for work in your current job?",
            "type": "radiov2",
            "field_name": "travel_for_work",
            "name": "q_2",
            "options": ["Yes", "No"],
            "required": True,
            "infoTitle": "Commuting doesn't count",
            "info": "Travelling for work does not include driving to the same place each time, like an office or other permanent place of work",
            "value": "",
            "handlerNext": {
                "No": {
                    "action": "navigate_to_screen",
                    "ref": "/estimation-wizard/start-refund/StartRefund",
                    "params": {"edit_response": True}
                },
                "Yes": {
                    "action": "open_question",
                    "ref": "3"
                }
            },
            "xhrParams": lambda q: {
                "status": "Completed" if q["value"] == "No" else None,
                "travel_for_work": False if q["value"] == "No" else True
            }
        },
        {
            "ref": "3",
            "progress": 18,
            "title": "How do you make your work journeys?",
            "type": "radiov2",
            "field_name": "howDoYouMakeYourWorkJourneys",
            "name": "q_3",
            "options": ["My\nvehicle", "Company\nvehicle", "Train"],
            "required": True,
            "infoTitle": "",
            "info": "",
            "value": "",
            "handlerNext": {
                "My\nvehicle": {"action": "open_question", "ref": "4"},
                "Company\nvehicle": {"action": "open_question", "ref": "6"},
                "Train": {"action": "open_question", "ref": "6"}
            },
            "xhrParams": lambda q: {
                "howDoYouMakeYourWorkJourneys": "my_vehicle" if q["value"] == "My\nvehicle" else ("company_vehicle" if q["value"] == "Company\nvehicle" else "train"),
                "ownCar": 1 if q["value"] == "My\nvehicle" else 0,
                "mileage": 0 if q["value"] != "My\nvehicle" else None,
                "mileageRate": 0 if q["value"] != "My\nvehicle" else None
            }
        },
        {
            "ref": "4",
            "progress": 20,
            "title": "How many miles do you drive a year?",
            "type": "numeric",
            "field_name": "mileage",
            "name": "q_4",
            "required": True,
            "subTitle": "Miles per year",
            "infoTitle": "Estimate your mileage",
            "info": "Don't worry this doesn't have to be exact right now.",
            "placeholder": "Ex - 8,000",
            "value": "",
            "xhrParams": lambda q: {"mileage": float(q["value"].replace(",", ""))}
        },
        {
            "ref": "5",
            "progress": 25,
            "title": "How does your employer pay your mileage expenses?",
            "type": "radio",
            "field_name": "mileageType",
            "name": "q_5",
            "options": ["Mileage rate", "Fuel card", "No expenses"],
            "required": True,
            "infoTitle": "Mileage expenses",
            "info": "Many employers pay some expenses for your work mileage. Please select the option that applies to you.",
            "value": "",
            "proposal": {
                "Mileage rate": [
                    {
                        "ref": "50",
                        "title": "",
                        "subTitle": "Rate",
                        "type": "numeric",
                        "name": "q_51",
                        "required": True,
                        "value": "",
                        "placeholder": "Ex - 25p"
                    }
                ]
            },
            "handlerNext": {
                "Mileage rate": {"action": "open_question", "ref": "8"},
                "Fuel card": {"action": "open_question", "ref": "8"},
                "No expenses": {"action": "open_question", "ref": "6"}
            },
            "xhrParams": lambda q: {
                "mileageType": 3 if q["value"] == "No expenses" else (2 if q["value"] == "Fuel card" else 1),
                "mileageRate": 0 if q["value"] != "Mileage rate" else (
                    float(q.get("proposal", {}).get("Mileage rate", [{}])[0].get("value", "0").replace(",", "")) / 100
                    if float(q.get("proposal", {}).get("Mileage rate", [{}])[0].get("value", "0").replace(",", "")) > 1
                    else float(q.get("proposal", {}).get("Mileage rate", [{}])[0].get("value", "0").replace(",", ""))
                )
            }
        },
        {
            "ref": "6",
            "progress": 30,
            "title": "What type of work journeys do you make?",
            "type": "radio",
            "field_name": "workJourneyType",
            "name": "q_6",
            "options": [
                "I travel to multiple places as part of my job",
                "I travel to the same place of work each time"
            ],
            "required": True,
            "value": "",
            "handlerNext": {
                "I travel to multiple places as part of my job": {"action": "open_question", "ref": "8"},
                "I travel to the same place of work each time": {"action": "open_question", "ref": "7"}
            },
            "xhrParams": lambda q: {
                "workJourneyType": "same_place" if q["value"] == "I travel to the same place of work each time" else "multiple_places"
            }
        },
        {
            "ref": "7",
            "progress": 35,
            "title": "Is this a temporary workplace?",
            "type": "radiov2",
            "field_name": "isWorkplaceTemporary",
            "name": "q_7",
            "options": ["Yes", "No"],
            "required": True,
            "infoTitle": "What is a temporary workplace?",
            "info": "This is a temporary place that is different from the main place that you do your job, and you will be working at for less than 2 years.",
            "value": "",
            "handlerNext": {
                "No": {
                    "action": "navigate_to_screen",
                    "ref": "/estimation-wizard/start-refund/StartRefund",
                    "params": {"edit_response": True}
                },
                "Yes": {"action": "open_question", "ref": "8"}
            },
            "xhrParams": lambda q: {"isWorkplaceTemporary": q["value"] == "Yes"}
        },
        {
            "ref": "8",
            "progress": 40,
            "title": "Do you buy food and drink when travelling for work?",
            "type": "radiov2",
            "field_name": "foodAndDrink",
            "name": "q_8",
            "options": ["Yes", "No"],
            "required": True,
            "value": "",
            "dynamiqyeHandlerNext": lambda q, data: {
                "action": "to_save_and_finish" if q["value"] == "No" and float(data.get("annualSaving", 0)) > 200
                else ("navigate_to_screen" if q["value"] == "No"
                else "open_question"),
                "ref": "13" if q["value"] == "No" and float(data.get("annualSaving", 0)) > 200
                else ("/estimation-wizard/start-refund/StartRefund" if q["value"] == "No"
                else "9"),
                "params": {"edit_response": True} if q["value"] == "No" and float(data.get("annualSaving", 0)) <= 200 else None
            },
            "xhrParams": lambda q: {
                "foodAndDrink": q["value"] == "Yes",
                "daysPerWeek": 0 if q["value"] == "Yes" else None,
                "spendPerDay": 0 if q["value"] == "Yes" else None,
                "reimbursedPerDay": 0 if q["value"] == "Yes" else None
            }
        },
        {
            "ref": "9",
            "progress": 60,
            "title": "How many days do you travel a week on average?",
            "type": "counter",
            "field_name": "daysPerWeek",
            "name": "q_9",
            "required": True,
            "subTitle": "Days per week",
            "infoTitle": "Estimate your travel days",
            "info": "This may not be the same number every week, so you can estimate the average number of days a week.",
            "value": "",
            "xhrParams": lambda q: {"daysPerWeek": int(q["value"])}
        },
        {
            "ref": "10",
            "progress": 70,
            "title": "How much do you spend on food and drink per day on average?",
            "type": "price",
            "field_name": "spendPerDay",
            "name": "q_10",
            "required": True,
            "subTitle": "Spend per day",
            "infoTitle": "Estimate your spend",
            "info": "It might not be the same every day, just give us an average for now.",
            "placeholder": "Ex - £10",
            "value": "",
            "xhrParams": lambda q: {"spendPerDay": float(q["value"].replace(",", ""))}
        },
        {
            "ref": "11",
            "progress": 80,
            "title": "Does your employer pay any expenses for your food and drink?",
            "type": "radio",
            "field_name": "foodExpensesCover",
            "options": [
                "No, I pay for it and don't get anything back from my employer",
                "Yes, I pay for it but can claim some of it back from my employer",
                "Yes, I pay for it but can claim all of it back from my employer",
                "Yes, I have a company credit card"
            ],
            "name": "q_11",
            "required": True,
            "value": "",
            "dynamiqyeHandlerNext": lambda q, data: {
                "action": "to_save_and_finish" if q["value"] in [
                    "No, I pay for it and don't get anything back from my employer",
                    "Yes, I pay for it but can claim all of it back from my employer",
                    "Yes, I have a company credit card"
                ] and float(data.get("annualSaving", 0)) > 200
                else ("navigate_to_screen" if q["value"] in [
                    "No, I pay for it and don't get anything back from my employer",
                    "Yes, I pay for it but can claim all of it back from my employer",
                    "Yes, I have a company credit card"
                ]
                else "open_question"),
                "ref": "13" if q["value"] in [
                    "No, I pay for it and don't get anything back from my employer",
                    "Yes, I pay for it but can claim all of it back from my employer",
                    "Yes, I have a company credit card"
                ] and float(data.get("annualSaving", 0)) > 200
                else ("/estimation-wizard/start-refund/StartRefund" if q["value"] in [
                    "No, I pay for it and don't get anything back from my employer",
                    "Yes, I pay for it but can claim all of it back from my employer",
                    "Yes, I have a company credit card"
                ]
                else "12"),
                "params": {"edit_response": True} if q["value"] in [
                    "No, I pay for it and don't get anything back from my employer",
                    "Yes, I pay for it but can claim all of it back from my employer",
                    "Yes, I have a company credit card"
                ] and float(data.get("annualSaving", 0)) <= 200 else None
            },
            "xhrParams": lambda q, estimation=None: {
                "foodExpensesCover": {
                    "No, I pay for it and don't get anything back from my employer": "no_reimbursement",
                    "Yes, I pay for it but can claim some of it back from my employer": "partial_reimbursement",
                    "Yes, I pay for it but can claim all of it back from my employer": "full_reimbursement",
                    "Yes, I have a company credit card": "company_card"
                }.get(q["value"]),
                "reimbursedPerDay": float(estimation.get("spendPerDay", 0)) if estimation and q["value"] in [
                    "Yes, I pay for it but can claim all of it back from my employer",
                    "Yes, I have a company credit card"
                ] else None
            }
        },
        {
            "ref": "12",
            "progress": 98,
            "title": lambda data: f"How much of the £{data.get('spendPerDay', 0)} does your employer pay for your food and drink?",
            "type": "price",
            "field_name": "reimbursedPerDay",
            "name": "q_12",
            "required": True,
            "subTitle": "Spend per day",
            "placeholder": "Ex - £5",
            "infoTitle": "Estimate your spend",
            "info": "It might not be the same every day, just give us an average for now.",
            "value": "",
            "xhrParams": lambda q: {"reimbursedPerDay": float(q["value"].replace(",", ""))}
        },
        {
            "ref": "13",
            "progress": 99,
            "title": "Did you earn more than £14,000 in any of the last 4 tax years?",
            "type": "radiov2",
            "field_name": "earnedMoreThan14kInLast4TaxYears",
            "name": "q_23",
            "options": ["Yes", "No"],
            "required": True,
            "infoTitle": "Did you earn more money in past tax years?",
            "info": "You could qualify for a tax refund if you earned more than £14,000 in any of the last four tax years.",
            "value": "",
            "handlerNext": {
                "No": {"action": "to_save_and_finish_with_error"},
                "Yes": {"action": "open_question", "ref": "14"}
            },
            "xhrParams": lambda q: {"status": "Completed"} if q["value"] == "No" else None
        },
        {
            "ref": "14",
            "progress": 100,
            "title": "Do you have any other sources of income?",
            "type": "radiov2",
            "field_name": "otherIncome",
            "name": "q_14",
            "options": ["Yes", "No"],
            "required": True,
            "value": ""
        },
        {
            "ref": "15",
            "progress": 100,
            "title": "How much do you spend on commuting per month?",
            "type": "price",
            "field_name": "commutingSpend",
            "name": "q_15",
            "required": True,
            "subTitle": "Spend per month",
            "placeholder": "Ex - £50",
            "value": ""
        }
    ]

# Build question map
QUESTIONS = get_questions_list()
QUESTION_MAP = {str(q["ref"]): q for q in QUESTIONS}

# Phase configuration - Refund vs Savings
PHASE_1_QUESTIONS = ["1", "2", "3", "4", "5", "6", "7", "8"]  # Refund Assessment
PHASE_2_QUESTIONS = ["9", "10", "11", "12", "13", "14", "15"]  # Savings Assessment
PHASE_NAMES = {
    1: "🔍 Refund Assessment",
    2: "💰 Savings Assessment"
}

# =========================================================
# SESSION MANAGEMENT
# =========================================================

def init_session():
    """Initialize session with validation and defaults"""
    try:
        defaults = {
            "messages": [],
            "answers": {},
            "current_ref": "1",
            "passkey_verified": False,
            "waiting_for_answer": False,
            "completed": False,
            "history": [],
            "pending_proposal": None,
            "phase": 1,
            "phase_transition_shown": False,
            "awaiting_greeting": False,
            "awaiting_ok": False,
            "last_activity": datetime.now().isoformat(),
            "error_count": 0,
            "estimation_data": {},
            "sidebar_open": True,
            "savy_estimation_id": None,
            "refund_estimation_id": None,
            "tax_estimation_id": None,
            "estimation_initiated": False,
            "tax_estimation_initiated": False,
            "savy_authenticated": False,
            "savy_user_id": None,
            "conversation_id": None
        }
        
        for key, default_value in defaults.items():
            if key not in session:
                session[key] = default_value
        
        if not session.get("conversation_id"):
            session["conversation_id"] = get_conversation_id()
        
        session.modified = True
        
    except Exception as e:
        logger.error(f"Error in init_session: {e}")
        session.clear()
        init_session()

def calculate_annual_saving(answers):
    """Calculate annual saving based on answers - replicates the estimation logic"""
    try:
        days_per_week = float(answers.get("9", 0)) if answers.get("9") else 0
        spend_per_day = float(answers.get("10", 0)) if answers.get("10") else 0
        reimbursed_per_day = float(answers.get("12", 0)) if answers.get("12") else 0
        
        weeks_per_year = 48
        annual_saving = (spend_per_day - reimbursed_per_day) * days_per_week * weeks_per_year
        
        return annual_saving
    except:
        return 0

# =========================================================
# DYNAMIC HANDLER EVALUATION
# =========================================================

def evaluate_dynamic_handler(question, answer, all_answers):
    """Evaluate dynamiqyeHandlerNext function if it exists"""
    if "dynamiqyeHandlerNext" in question:
        try:
            estimation_data = session.get("estimation_data", {})
            estimation_data["annualSaving"] = calculate_annual_saving(all_answers)
            session["estimation_data"] = estimation_data
            
            q_obj = {
                "value": answer,
                "ref": question["ref"],
                "name": question.get("name", ""),
                "field_name": question.get("field_name", "")
            }
            
            handler = question["dynamiqyeHandlerNext"]
            if callable(handler):
                sig = inspect.signature(handler)
                if len(sig.parameters) == 1:
                    result = handler(q_obj)
                else:
                    result = handler(q_obj, estimation_data)
                
                if result.get("action") == "open_question":
                    return {
                        "status": "success",
                        "next_ref": str(result.get("ref")),
                        "completed": False
                    }
                elif result.get("action") == "navigate_to_screen":
                    if "/estimation-wizard/start-refund/StartRefund" in str(result.get("ref", "")):
                        return {"status": "completed"}
                    return {"status": "completed"}
                elif result.get("action") == "to_save_and_finish":
                    return {"status": "completed"}
                elif result.get("action") == "to_save_and_finish_with_error":
                    return {"status": "completed"}
        except Exception as e:
            logger.error(f"Error in dynamic handler for {question['ref']}: {e}")
    
    return None

def process_handler_next(current_ref, answer):
    """Process next question using StateMachineEngine"""
    try:
        result = state_engine.get_next_question_ref(current_ref, answer)
        
        if result.get("status") == "success" and result.get("next_ref"):
            return {"status": "success", "next_ref": result["next_ref"], "completed": False}
        elif result.get("status") == "completed":
            return {"status": "completed"}
        
        question = get_question(current_ref)
        if not question:
            return {"status": "completed"}
        
        all_answers = session.get("answers", {})
        
        dynamic_result = evaluate_dynamic_handler(question, answer, all_answers)
        if dynamic_result:
            return dynamic_result
        
        if "handlerNext" in question:
            clean_answer = str(answer).replace('\n', ' ').strip()
            
            handler = None
            for key, value in question["handlerNext"].items():
                clean_key = str(key).replace('\n', ' ').strip()
                if clean_key == clean_answer:
                    handler = value
                    break
            
            if not handler:
                for key, value in question["handlerNext"].items():
                    if clean_answer in str(key).replace('\n', ' '):
                        handler = value
                        break
            
            if handler:
                action = handler.get("action")
                
                if action == "navigate_to_screen":
                    return {"status": "completed"}
                
                elif action == "open_question":
                    next_ref = str(handler.get("ref"))
                    return {"status": "success", "next_ref": next_ref, "completed": False}
                
                elif action in ["to_save_and_finish", "to_save_and_finish_with_error"]:
                    return {"status": "completed"}
        
        return {"status": "completed"}
            
    except Exception as e:
        logger.error(f"Error in process_handler_next: {e}")
        return {"status": "completed"}

def get_next_question_in_phase(current_ref):
    """Get next question using StateMachineEngine to follow the flow diagram"""
    try:
        current_answer = session.get("answers", {}).get(current_ref)
        
        if current_answer is None:
            return {"status": "success", "next_ref": current_ref, "completed": False}
        
        result = state_engine.get_next_question_ref(current_ref, current_answer)
        
        if result.get("status") == "success" and result.get("next_ref"):
            return {"status": "success", "next_ref": result["next_ref"], "completed": False}
        elif result.get("status") == "completed":
            return {"status": "completed"}
        else:
            return {"status": "completed"}
        
    except Exception as e:
        logger.error(f"Error in get_next_question_in_phase: {e}")
        return {"status": "completed"}

# =========================================================
# HELPER FUNCTIONS
# =========================================================

def get_question(ref):
    """Safely get question by reference"""
    try:
        question = QUESTION_MAP.get(str(ref))
        if question and callable(question.get("title")):
            question = question.copy()
            question["title"] = question["title"](session.get("answers", {}))
        return question
    except Exception as e:
        logger.error(f"Error getting question {ref}: {e}")
        return None

def clean_number(value):
    """Safely clean number inputs"""
    if value is None:
        return None
    try:
        cleaned = re.sub(r'[£,€$]', '', str(value))
        cleaned = re.sub(r'[^\d.]', '', cleaned)
        if cleaned == "":
            return None
        return cleaned
    except Exception as e:
        logger.error(f"Error cleaning number {value}: {e}")
        return None

def get_question_text(question):
    """Get formatted question text with error handling"""
    if not question:
        return "I'm sorry, there was an error loading the question. Please try again."
    
    try:
        text = question.get("title", "")
        if callable(text):
            text = text(session.get("answers", {}))
        
        if question.get("subTitle"):
            text = f"{text}\n\n📊 **{question['subTitle']}**"
        
        if question.get("infoTitle") and question.get("info"):
            text = f"{text}\n\nℹ️ **{question['infoTitle']}**\n{question['info']}"
        
        if question.get("placeholder"):
            text = f"{text}\n\n💡 *Example: {question['placeholder']}*"
        
        return text
    except Exception as e:
        logger.error(f"Error formatting question text: {e}")
        return str(question.get("title", "Please answer the following question:"))

def get_options(question):
    """Safely get options for a question"""
    if not question:
        return None
    
    try:
        if question.get("type") in ['radiov2', 'radio', 'single_choice']:
            options = question.get("options", [])
            return [str(opt).replace('\n', ' ') for opt in options]
        return None
    except Exception as e:
        logger.error(f"Error getting options: {e}")
        return None

def get_question_type(question):
    """Safely get question type"""
    if not question:
        return "text"
    
    try:
        q_type = question.get("type", "text")
        if q_type in ['radiov2', 'radio', 'single_choice']:
            return "choice"
        elif q_type in ['numeric', 'number', 'price', 'counter']:
            return "numeric"
        else:
            return "text"
    except Exception as e:
        logger.error(f"Error getting question type: {e}")
        return "text"

def handle_proposal(current_ref, answer):
    """Handle proposal questions"""
    try:
        question = get_question(current_ref)
        if not question or "proposal" not in question:
            return None
        
        proposal = question.get("proposal", {})
        clean_answer = str(answer).replace('\n', ' ').strip()
        
        for key, proposal_questions in proposal.items():
            clean_key = str(key).replace('\n', ' ').strip()
            if clean_key == clean_answer or clean_answer in clean_key:
                session["pending_proposal"] = {
                    "original_ref": current_ref,
                    "answer": answer,
                    "questions": proposal_questions,
                    "current_index": 0
                }
                session.modified = True
                return proposal_questions
        
        return None
    except Exception as e:
        logger.error(f"Error in handle_proposal: {e}")
        return None

def add_message(role, content, options=None, input_type=None):
    """Safely add a message to chat history"""
    try:
        if "messages" not in session:
            session["messages"] = []
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        if options:
            message["options"] = options
        if input_type:
            message["input_type"] = input_type
        
        session["messages"].append(message)
        session.modified = True
        
        save_conversation(
            session.get("conversation_id"),
            session.get("messages", []),
            session.get("answers", {}),
            session.get("history", []),
            session.get("phase", 1),
            session.get("completed", False)
        )
        
        if len(session["messages"]) > 100:
            session["messages"] = session["messages"][-100:]
            
    except Exception as e:
        logger.error(f"Error adding message: {e}")

def process_next_question():
    """Process and send the next question"""
    try:
        if session.get("completed"):
            return
        
        if session.get("pending_proposal"):
            proposal_data = session["pending_proposal"]
            proposal_questions = proposal_data.get("questions", [])
            current_index = proposal_data.get("current_index", 0)
            
            if current_index < len(proposal_questions):
                prop_q = proposal_questions[current_index]
                question_text = get_question_text(prop_q)
                options = get_options(prop_q)
                input_type = get_question_type(prop_q)
                
                add_message("assistant", question_text, options, input_type)
                session["waiting_for_answer"] = True
                session.modified = True
                return
        
        current_ref = session.get("current_ref")
        if not current_ref:
            session["current_ref"] = "1"
            current_ref = "1"
        
        question = get_question(current_ref)
        
        if not question:
            complete_assessment()
            return
        
        question_text = get_question_text(question)
        options = get_options(question)
        input_type = get_question_type(question)
        
        add_message("assistant", question_text, options, input_type)
        session["waiting_for_answer"] = True
        session.modified = True
        
    except Exception as e:
        logger.error(f"Error in process_next_question: {e}")
        add_message("assistant", "I'm sorry, there was an error. Please try again.")
        session["error_count"] = session.get("error_count", 0) + 1

def show_phase_transition():
    """Show transition message between phases"""
    try:
        if session.get("phase") == 2 and not session.get("phase_transition_shown"):
            transition_msg = "✅ **Thank you for completing the Refund Assessment!**\n\n"
            transition_msg += "Now let's move to the next step: **💰 Savings Assessment**\n"
            transition_msg += "Please answer the following questions about your travel and expenses to calculate your potential tax savings.\n"
            
            add_message("assistant", transition_msg)
            session["phase_transition_shown"] = True
            session.modified = True
            return True
        return False
    except Exception as e:
        logger.error(f"Error in show_phase_transition: {e}")
        return False

def run_xhr_params(question, answer, current_ref):
    """Safely run xhrParams function"""
    try:
        if "xhrParams" in question and callable(question["xhrParams"]):
            q_obj = {"value": answer, "ref": current_ref}
            
            if session.get("pending_proposal"):
                q_obj["proposal"] = {answer: session["pending_proposal"].get("questions", [])}
            
            sig = inspect.signature(question["xhrParams"])
            estimation_data = session.get("estimation_data", {})
            
            if len(sig.parameters) == 1:
                xhr_result = question["xhrParams"](q_obj)
            else:
                xhr_result = question["xhrParams"](q_obj, estimation_data)
            
            if xhr_result:
                session["estimation_data"].update(xhr_result)
                session.modified = True
    except Exception as e:
        logger.error(f"Error in xhrParams for {current_ref}: {e}")

def send_to_savy(answers, phase, phase_name, ai_summary=None):
    """Send assessment data to Savy API - using the correct v1 endpoint"""
    try:
        savy_data = {
            "phase": phase,
            "phase_name": phase_name,
            "answers": answers,
            "completed_at": datetime.now().isoformat(),
            "user_answers": {}
        }
        
        for ref, answer in answers.items():
            question = get_question(ref)
            if question:
                title = question.get("title", ref)
                if callable(title):
                    title = title(answers)
                savy_data["user_answers"][ref] = {
                    "question": title,
                    "answer": answer,
                    "type": question.get("type", "text")
                }
        
        if ai_summary:
            savy_data["ai_summary"] = ai_summary
        
        logger.info("📤 Sending assessment data to Savy API...")
        response = make_savy_request("api/v1/refund-estimations", "POST", savy_data)
        
        if response and not response.get("error"):
            logger.info("✅ Assessment data saved to Savy successfully")
            session["savy_estimation_id"] = response.get("id") or response.get("estimationId")
            session.modified = True
            return True
        else:
            logger.warning(f"⚠️ Could not save to Savy: {response}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error sending to Savy: {e}")
        return False

def complete_assessment():
    """Complete assessment and show results with clear AI integration"""
    try:
        session["completed"] = True
        session["waiting_for_answer"] = False
        
        answers = session.get("answers", {})
        phase = session.get("phase", 1)
        phase_name = PHASE_NAMES.get(phase, "Assessment")
        
        logger.info(f"\n{'='*70}")
        logger.info(f"📊 COMPLETING ASSESSMENT - {phase_name}")
        logger.info(f"{'='*70}")
        logger.info(f"Answers count: {len(answers)}")
        logger.info(f"Phase: {phase}")
        
        plain_summary = f"{phase_name} Summary:\n\n"
        for ref, answer in answers.items():
            question = get_question(ref)
            if question:
                title = question.get("title", ref)
                if callable(title):
                    title = title(answers)
                plain_summary += f"{title}\n→ {answer}\n\n"
        
        use_ai = os.environ.get("USE_AI", "").lower() in ["1", "true", "yes"]
        provider = os.environ.get("AI_PROVIDER", "gemini").lower()
        
        logger.info(f"USE_AI env var: {os.environ.get('USE_AI')}")
        logger.info(f"USE_AI parsed: {use_ai}")
        logger.info(f"Provider: {provider}")
        
        chatgpt_creds = ai_client.chatgpt_key or ai_client.openai_key
        google_creds = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_API_TOKEN")
        
        logger.info(f"ChatGPT creds: {bool(chatgpt_creds)}")
        logger.info(f"Google creds: {bool(google_creds)}")
        
        provider_enabled = (provider in ["openai", "chatgpt"] and chatgpt_creds) or \
                           (provider in ["gemini", "google"] and google_creds)
        
        logger.info(f"Provider enabled: {provider_enabled}")
        
        thinking_message = "🤖 **AI Assistant is analyzing your responses...**\n\n*This may take a moment while I generate your personalized tax assessment.*"
        add_message("assistant", thinking_message)
        
        ai_summary = None
        if use_ai and provider_enabled:
            try:
                logger.info(f"\n{'='*70}")
                logger.info(f"🤖 GENERATING AI SUMMARY")
                logger.info(f"{'='*70}")
                logger.info(f"Phase: {phase_name}")
                logger.info(f"Provider: {provider.upper()}")
                logger.info(f"{'='*70}\n")
                
                system_prompt = f"You are a {phase_name} assessment specialist. Provide a concise, professional summary of the user's {phase_name.lower()} in 2-3 sentences based on their responses."
                
                logger.info(f"📝 Summary Input:\n{plain_summary}\n")
                logger.info(f"🔄 Calling ai_client.generate()...")
                
                time.sleep(0.8)
                
                ai_summary = ai_client.generate(
                    prompt=plain_summary,
                    system_prompt=system_prompt,
                    max_tokens=500,
                    temperature=0.7
                )
                
                logger.info(f"AI response length: {len(ai_summary) if ai_summary else 0} chars")
                logger.info(f"AI response empty: {not ai_summary}")
                
                if ai_summary:
                    logger.info(f"{'='*70}")
                    logger.info(f"✅ AI SUMMARY GENERATED SUCCESSFULLY")
                    logger.info(f"{'='*70}\n")
                    logger.info(f"🎯 AI SUMMARY:\n{ai_summary}\n")
                    logger.info(f"{'='*70}\n")
                else:
                    logger.warning("⚠️  AI summary was empty")
                    
            except Exception as e:
                logger.error(f"❌ AI summary failed: {e}", exc_info=True)
                ai_summary = None
        else:
            logger.warning(f"⚠️  Skipping AI summary: use_ai={use_ai}, provider_enabled={provider_enabled}")
        
        if session["messages"] and "AI Assistant is analyzing your responses" in session["messages"][-1].get("content", ""):
            session["messages"].pop()
        
        if not ai_summary:
            logger.info("📝 Generating fallback summary from answers...")
            fallback_parts = []
            for ref, answer in answers.items():
                question = get_question(ref)
                if question:
                    title = question.get("title", ref)
                    if callable(title):
                        title = title(answers)
                    clean_answer = str(answer).replace('\n', ' ')
                    fallback_parts.append(f"• {title}: {clean_answer}")
            
            if fallback_parts:
                ai_summary = "📝 **Assessment Summary**\n\nBased on your responses:\n\n"
                for part in fallback_parts[:10]:
                    ai_summary += f"{part}\n"
                if len(fallback_parts) > 10:
                    ai_summary += f"\n• ... and {len(fallback_parts) - 10} more responses"
                ai_summary += "\n\nA tax specialist will review your information and contact you soon."
            else:
                ai_summary = "Thank you for completing the tax assessment. Your responses have been recorded and will be reviewed by our tax specialists."
        
        send_to_savy(answers, phase, phase_name, ai_summary)
        
        tax_estimation_id = session.get("tax_estimation_id")
        if tax_estimation_id and session.get("tax_estimation_initiated"):
            try:
                final_data = {
                    "answers": answers,
                    "completed_at": datetime.now().isoformat(),
                    "phase": phase,
                    "total_questions": len(session.get("history", [])),
                    "estimation_data": session.get("estimation_data", {}),
                    "ai_summary": ai_summary,
                    "status": "completed"
                }
                update_tax_estimation(tax_estimation_id, final_data)
                logger.info(f"✅ Tax estimation {tax_estimation_id} updated with final data")
            except Exception as e:
                logger.error(f"Error updating tax estimation with final data: {e}")
        
        final_message = f"🎉 **{phase_name} Complete!** 🎉\n\n"
        final_message += "=" * 50 + "\n\n"
        final_message += "📊 **Summary of Your Responses:**\n\n"
        
        for ref, answer in answers.items():
            question = get_question(ref)
            if question:
                title = question.get("title", ref)
                if callable(title):
                    title = title(answers)
                final_message += f"• **{title}**\n"
                final_message += f"  → {answer}\n\n"
        
        if ai_summary:
            final_message += "=" * 50 + "\n\n"
            final_message += "🤖 **AI-Powered Assessment:**\n\n"
            final_message += f"✨ *Based on your responses, our AI has generated the following personalized analysis:* ✨\n\n"
            final_message += f"{ai_summary}\n\n"
            final_message += "---\n\n"
            final_message += "💡 *This assessment helps our tax specialists better understand your situation.*\n\n"
        else:
            final_message += "=" * 50 + "\n\n"
            final_message += "📝 **Assessment Note:**\n\n"
            final_message += "Your responses have been recorded and will be reviewed by our tax team.\n\n"
        
        final_message += "=" * 50 + "\n\n"
        final_message += "📞 **Next Steps:**\n\n"
        final_message += "A tax specialist will review your information and contact you soon.\n\n"
        final_message += "Thank you for using the Tax Assistant Bot! 🙏\n\n"
        final_message += "Click 'Start New Assessment' below to begin again."
        
        add_message("assistant", final_message)
        session.modified = True
        
        save_conversation(
            session.get("conversation_id"),
            session.get("messages", []),
            session.get("answers", {}),
            session.get("history", []),
            session.get("phase", 1),
            True
        )
        
        logger.info(f"✅ Assessment complete and message added to session")
        logger.info(f"{'='*70}\n")
        
    except Exception as e:
        logger.error(f"Error in complete_assessment: {e}", exc_info=True)
        add_message("assistant", "Thank you for completing the assessment!")

def format_answer_for_display(question, answer):
    """Format answer nicely for sidebar display"""
    if not question:
        return str(answer)
    
    formatted = str(answer).replace('\n', ' ')
    
    if question.get("type") in ["price", "numeric"]:
        try:
            num = float(answer)
            if question.get("type") == "price":
                formatted = f"£{num:,.2f}"
        except:
            pass
    
    return formatted

# =========================================================
# FLASK ROUTES
# =========================================================

def safe_route(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in route {f.__name__}: {e}")
            return jsonify({"status": "error", "message": "An unexpected error occurred."}), 500
    return decorated_function

@app.before_request
def before_request():
    try:
        init_session()
        
        allowed_routes = ["passkey_page", "verify_passkey", "static", "favicon", "toggle_sidebar", "edit_answer", "login_page", "auth_email_login", "get_conversations", "load_conversation", "delete_conversation", "new_conversation", "start_new_assessment", "swagger", "swagger-ui", "swagger_spec", "api_docs"]
        if request.endpoint in allowed_routes:
            return
        
        if not session.get("savy_authenticated") and not SAVY_USER_ID:
            return redirect(url_for("login_page"))
        
        if not session.get("passkey_verified"):
            return redirect(url_for("passkey_page"))
            
    except Exception as e:
        logger.error(f"Error in before_request: {e}")
        return redirect(url_for("login_page"))

@app.route("/")
@safe_route
def index():
    """Redirect to chat or API documentation"""
    if not session.get("savy_authenticated") and not SAVY_USER_ID:
        return redirect(url_for("login_page"))
    if not session.get("passkey_verified"):
        return redirect(url_for("passkey_page"))
    return redirect(url_for("chat"))

@app.route("/api/docs")
def api_docs():
    """Redirect to Swagger UI"""
    return redirect("/apidocs/")

# =========================================================
# START NEW ASSESSMENT - Redirects to passkey page
# =========================================================

@app.route("/start_new_assessment", methods=["GET"])
@safe_route
def start_new_assessment():
    """Clear session and redirect to passkey page"""
    session.clear()
    init_session()
    return redirect(url_for("passkey_page"))

# =========================================================
# CONVERSATION MANAGEMENT ROUTES
# =========================================================

# Ajouter cette documentation pour la route GET /api/conversations
@app.route("/api/conversations", methods=["GET"])
@safe_route
@swag_from({
    'tags': ['Conversations'],
    'summary': 'Get all conversations organized by folder',
    'description': 'Retrieves all conversations for the current user, organized into folders (Today, Yesterday, Previous 7 Days, Older).',
    'responses': {
        200: {
            'description': 'Successful operation',
            'schema': {
                'type': 'object',
                'properties': {
                    'success': {'type': 'boolean', 'example': True},
                    'conversations': {
                        'type': 'object',
                        'properties': {
                            'Today': {
                                'type': 'array',
                                'items': {
                                    'type': 'object',
                                    'properties': {
                                        'id': {'type': 'string'},
                                        'title': {'type': 'string'},
                                        'messages': {'type': 'array'},
                                        'answers': {'type': 'object'},
                                        'history': {'type': 'array'},
                                        'phase': {'type': 'integer'},
                                        'completed': {'type': 'boolean'},
                                        'last_updated': {'type': 'string'}
                                    }
                                }
                            },
                            'Yesterday': {'type': 'array'},
                            'Previous 7 Days': {'type': 'array'},
                            'Older': {'type': 'array'}
                        }
                    }
                }
            }
        },
        401: {
            'description': 'Authentication required'
        }
    }
})
def get_conversations():
    """Get all conversations organized by folder"""
    organized = get_all_conversations()
    return jsonify({"success": True, "conversations": organized})

@app.route("/api/conversation/<conversation_id>", methods=["GET"])
@safe_route
@swag_from({
    'tags': ['Conversations'],
    'summary': 'Get a specific conversation by ID',
    'parameters': [
        {
            'name': 'conversation_id',
            'in': 'path',
            'type': 'string',
            'required': True,
            'description': 'The ID of the conversation to retrieve'
        }
    ],
    'responses': {
        200: {
            'description': 'Successful operation',
            'schema': {
                'type': 'object',
                'properties': {
                    'success': {'type': 'boolean'},
                    'conversation': {'type': 'object'}
                }
            }
        },
        404: {
            'description': 'Conversation not found'
        }
    }
})
def load_conversation(conversation_id):
    """Load a specific conversation"""
    conv = get_conversation(conversation_id)
    if conv:
        session["messages"] = conv.get("messages", [])
        session["answers"] = conv.get("answers", {})
        session["history"] = conv.get("history", [])
        session["phase"] = conv.get("phase", 1)
        session["completed"] = conv.get("completed", False)
        session["conversation_id"] = conversation_id
        session["waiting_for_answer"] = False
        session.modified = True
        return jsonify({"success": True, "conversation": conv})
    return jsonify({"success": False, "error": "Conversation not found"}), 404

@app.route("/api/conversation/<conversation_id>", methods=["DELETE"])
@safe_route
@swag_from({
    'tags': ['Conversations'],
    'summary': 'Delete a conversation by ID',
    'parameters': [
        {
            'name': 'conversation_id',
            'in': 'path',
            'type': 'string',
            'required': True,
            'description': 'The ID of the conversation to delete'
        }
    ],
    'responses': {
        200: {
            'description': 'Conversation deleted successfully',
            'schema': {
                'type': 'object',
                'properties': {
                    'success': {'type': 'boolean'}
                }
            }
        },
        404: {
            'description': 'Conversation not found'
        }
    }
})
def delete_conversation(conversation_id):
    """Delete a conversation"""
    if conversation_id in conversations:
        del conversations[conversation_id]
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Conversation not found"}), 404

@app.route("/api/conversation/new", methods=["POST"])
@safe_route
@swag_from({
    'tags': ['Conversations'],
    'summary': 'Create a new conversation',
    'description': 'Creates a new conversation with a unique ID and initializes the greeting flow.',
    'responses': {
        200: {
            'description': 'Conversation created successfully',
            'schema': {
                'type': 'object',
                'properties': {
                    'success': {'type': 'boolean'},
                    'conversation_id': {'type': 'string'}
                }
            }
        }
    }
})
def new_conversation():
    """Create a new conversation"""
    session["messages"] = []
    session["answers"] = {}
    session["history"] = []
    session["phase"] = 1
    session["completed"] = False
    session["current_ref"] = "1"
    session["waiting_for_answer"] = False
    session["phase_transition_shown"] = False
    session["awaiting_greeting"] = True
    session["awaiting_ok"] = False
    session["conversation_id"] = get_conversation_id()
    session.modified = True
    
    return jsonify({"success": True, "conversation_id": session["conversation_id"]})

# =========================================================
# AUTHENTICATION ROUTES
# =========================================================

@app.route("/login", methods=["GET", "POST"])
@safe_route
def login_page():
    """Login page for Savy API authentication"""
    if session.get("savy_authenticated"):
        return redirect(url_for("passkey_page"))
    
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        
        if not email or not password:
            return render_template_string("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Login - Savy Tax Assistant</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    * { box-sizing: border-box; }
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                        background: #f5f5f5;
                        margin: 0;
                        padding: 20px;
                        min-height: 100vh;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    }
                    .container {
                        background: white;
                        max-width: 400px;
                        width: 100%;
                        padding: 40px;
                        border-radius: 24px;
                        box-shadow: 0 20px 60px rgba(0,0,0,0.1);
                        text-align: center;
                    }
                    h1 { color: #1a1a2e; margin-bottom: 10px; }
                    .subtitle { color: #666; margin-bottom: 30px; }
                    input {
                        width: 100%;
                        padding: 14px;
                        border: 2px solid #e0e0e0;
                        border-radius: 12px;
                        font-size: 1em;
                        margin-bottom: 15px;
                        transition: border-color 0.3s ease;
                    }
                    input:focus {
                        outline: none;
                        border-color: #d63384;
                    }
                    button {
                        width: 100%;
                        padding: 14px;
                        background: linear-gradient(45deg, #d63384, #a02070);
                        color: white;
                        border: none;
                        border-radius: 12px;
                        font-size: 1.1em;
                        cursor: pointer;
                        font-weight: 600;
                        transition: transform 0.2s ease, box-shadow 0.2s ease;
                    }
                    button:hover {
                        transform: translateY(-2px);
                        box-shadow: 0 10px 20px rgba(214, 51, 132, 0.3);
                    }
                    .error {
                        background: #fee;
                        padding: 12px;
                        border-radius: 12px;
                        color: #c33;
                        margin-bottom: 20px;
                        font-size: 0.9em;
                    }
                    .pink-accent { color: #d63384; font-weight: 600; }
                    .savy-logo { font-size: 2.5em; font-weight: 700; color: #1a1a2e; margin-bottom: 5px; }
                    .savy-logo span { color: #d63384; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="savy-logo">SAV<span>Y</span></div>
                    <p class="subtitle">Sign in to access your tax assessment</p>
                    <div class="error">Please provide both email and password</div>
                    <form method="POST">
                        <input type="email" name="email" placeholder="Email address" required>
                        <input type="password" name="password" placeholder="Password" required>
                        <button type="submit">Sign In</button>
                    </form>
                </div>
            </body>
            </html>
            """)
        
        result = authenticate_savy_user(email, password)
        
        if result.get("success"):
            session["savy_authenticated"] = True
            session["savy_user_id"] = result.get("user_id")
            session.modified = True
            
            return redirect(url_for("passkey_page"))
        else:
            return render_template_string("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Login - Savy Tax Assistant</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    * { box-sizing: border-box; }
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                        background: #f5f5f5;
                        margin: 0;
                        padding: 20px;
                        min-height: 100vh;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    }
                    .container {
                        background: white;
                        max-width: 400px;
                        width: 100%;
                        padding: 40px;
                        border-radius: 24px;
                        box-shadow: 0 20px 60px rgba(0,0,0,0.1);
                        text-align: center;
                    }
                    h1 { color: #1a1a2e; margin-bottom: 10px; }
                    .subtitle { color: #666; margin-bottom: 30px; }
                    input {
                        width: 100%;
                        padding: 14px;
                        border: 2px solid #e0e0e0;
                        border-radius: 12px;
                        font-size: 1em;
                        margin-bottom: 15px;
                        transition: border-color 0.3s ease;
                    }
                    input:focus {
                        outline: none;
                        border-color: #d63384;
                    }
                    button {
                        width: 100%;
                        padding: 14px;
                        background: linear-gradient(45deg, #d63384, #a02070);
                        color: white;
                        border: none;
                        border-radius: 12px;
                        font-size: 1.1em;
                        cursor: pointer;
                        font-weight: 600;
                        transition: transform 0.2s ease, box-shadow 0.2s ease;
                    }
                    button:hover {
                        transform: translateY(-2px);
                        box-shadow: 0 10px 20px rgba(214, 51, 132, 0.3);
                    }
                    .error {
                        background: #fee;
                        padding: 12px;
                        border-radius: 12px;
                        color: #c33;
                        margin-bottom: 20px;
                        font-size: 0.9em;
                    }
                    .pink-accent { color: #d63384; font-weight: 600; }
                    .savy-logo { font-size: 2.5em; font-weight: 700; color: #1a1a2e; margin-bottom: 5px; }
                    .savy-logo span { color: #d63384; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="savy-logo">SAV<span>Y</span></div>
                    <p class="subtitle">Sign in to access your tax assessment</p>
                    <div class="error">Invalid email or password. Please try again.</div>
                    <form method="POST">
                        <input type="email" name="email" placeholder="Email address" required>
                        <input type="password" name="password" placeholder="Password" required>
                        <button type="submit">Sign In</button>
                    </form>
                </div>
            </body>
            </html>
            """)
    
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login - Savy Tax Assistant</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                background: #f5f5f5;
                margin: 0;
                padding: 20px;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .container {
                background: white;
                max-width: 400px;
                width: 100%;
                padding: 40px;
                border-radius: 24px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.1);
                text-align: center;
            }
            h1 { color: #1a1a2e; margin-bottom: 10px; }
            .subtitle { color: #666; margin-bottom: 30px; }
            input {
                width: 100%;
                padding: 14px;
                border: 2px solid #e0e0e0;
                border-radius: 12px;
                font-size: 1em;
                margin-bottom: 15px;
                transition: border-color 0.3s ease;
            }
            input:focus {
                outline: none;
                border-color: #d63384;
            }
            button {
                width: 100%;
                padding: 14px;
                background: linear-gradient(45deg, #d63384, #a02070);
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 1.1em;
                cursor: pointer;
                font-weight: 600;
                transition: transform 0.2s ease, box-shadow 0.2s ease;
            }
            button:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(214, 51, 132, 0.3);
            }
            .pink-accent { color: #d63384; font-weight: 600; }
            .savy-logo { font-size: 2.5em; font-weight: 700; color: #1a1a2e; margin-bottom: 5px; }
            .savy-logo span { color: #d63384; }
            .demo-credits {
                margin-top: 20px;
                padding: 15px;
                background: #f8f8fa;
                border-radius: 12px;
                font-size: 0.85em;
                color: #666;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="savy-logo">SAV<span>Y</span></div>
            <p class="subtitle">Sign in to access your tax assessment</p>
            <form method="POST">
                <input type="email" name="email" placeholder="Email address" required>
                <input type="password" name="password" placeholder="Password" required>
                <button type="submit">Sign In</button>
            </form>
            <div class="demo-credits">
                <strong>Demo Credentials:</strong><br>
                Email: demo@savyapp.dev<br>
                Password: demopass123
            </div>
        </div>
    </body>
    </html>
    """)

@app.route("/api/auth/email/login", methods=["POST"])
@safe_route
@swag_from({
    'tags': ['Authentication'],
    'summary': 'Authenticate user with email and password',
    'description': 'Authenticates a user and returns a JWT token for subsequent API calls.',
    'parameters': [
        {
            'name': 'body',
            'in': 'body',
            'required': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'email': {'type': 'string', 'description': 'User email address'},
                    'password': {'type': 'string', 'description': 'User password'}
                },
                'required': ['email', 'password']
            }
        }
    ],
    'responses': {
        200: {
            'description': 'Authentication successful',
            'schema': {
                'type': 'object',
                'properties': {
                    'success': {'type': 'boolean'},
                    'message': {'type': 'string'},
                    'token': {'type': 'string'},
                    'user_id': {'type': 'string'},
                    'data': {'type': 'object'}
                }
            }
        },
        400: {
            'description': 'Invalid request'
        },
        401: {
            'description': 'Authentication failed'
        }
    }
})
def auth_email_login():
    """
    Authenticate user with email and password
    POST /api/auth/email/login
    Body: { "email": "user@example.com", "password": "password" }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        email = data.get("email")
        password = data.get("password")
        
        if not email or not password:
            return jsonify({"error": "Email and password required"}), 400
        
        result = authenticate_savy_user(email, password)
        
        if result.get("success"):
            session["savy_authenticated"] = True
            session["savy_user_id"] = result.get("user_id")
            session.modified = True
            
            return jsonify({
                "success": True,
                "message": "Authentication successful",
                "token": result.get("token"),
                "user_id": result.get("user_id"),
                "data": result.get("data")
            })
        else:
            return jsonify({
                "success": False,
                "error": result.get("error", "Authentication failed")
            }), 401
            
    except Exception as e:
        logger.error(f"Error in auth_email_login: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/passkey")
@safe_route
def passkey_page():
    if session.get("passkey_verified"):
        return redirect(url_for("chat"))
    
    error_message = session.pop("passkey_error", None)
    
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Passkey Required - Tax Bot</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: white;
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
        h1 { color: #000; margin-bottom: 10px; }
        .subtitle { color: #000; margin-bottom: 30px; }
        .error { background: #fee; padding: 12px; border-radius: 12px; color: #c33; margin-bottom: 20px; }
        input { width: 100%; padding: 14px; border: 2px solid #e0e0e0; border-radius: 12px; font-size: 1em; margin-bottom: 20px; color: #000; }
        input:focus { outline: none; border-color: #d63384; }
        input::placeholder { color: #999; }
        button { width: 100%; padding: 14px; background: linear-gradient(45deg, #d63384, #a02070); color: white; border: none; border-radius: 12px; font-size: 1.1em; cursor: pointer; font-weight: 600; }
        button:hover { transform: translateY(-2px); box-shadow: 0 10px 20px rgba(214, 51, 132, 0.3); }
        .pink-accent { color: #d63384; font-weight: 600; }
        .logo-container-passkey { margin-bottom: 20px; }
        .savy-logo-passkey { width: 120px; height: auto; }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo-container-passkey"><svg class="savy-logo-passkey" viewBox="0 0 120 40" xmlns="http://www.w3.org/2000/svg"><text x="0" y="28" font-family="Arial, sans-serif" font-size="28" font-weight="bold" fill="#000000">SAVY</text><circle cx="45" cy="8" r="5" fill="#d63384"/></svg></div>
        <p class="subtitle">Find out how much you can save in just <span class="pink-accent">1m</span></p>
        {% if error_message %}
            <div class="error">{{ error_message }}</div>
        {% endif %}
        <form method="POST" action="/verify_passkey">
            <input type="password" name="passkey" placeholder="Enter passkey" required autofocus>
            <button type="submit">Start</button>
        </form>
    </div>
</body>
</html>
""", error_message=error_message)

@app.route("/verify_passkey", methods=["POST"])
@safe_route
def verify_passkey():
    passkey = request.form.get("passkey", "").strip()
    
    if passkey in VALID_PASSKEYS:
        session["passkey_verified"] = True
        session.modified = True
        return redirect(url_for("chat"))
    else:
        session["passkey_error"] = "Invalid passkey. Please try again."
        return redirect(url_for("passkey_page"))

@app.route("/toggle_sidebar", methods=["POST"])
@safe_route
def toggle_sidebar():
    session["sidebar_open"] = not session.get("sidebar_open", True)
    session.modified = True
    return jsonify({"sidebar_open": session["sidebar_open"]})

@app.route("/edit_answer", methods=["POST"])
@safe_route
def edit_answer():
    data = request.get_json()
    ref = data.get("ref")
    
    if not ref:
        return jsonify({"status": "error", "message": "No reference provided"})
    
    history = session.get("history", [])
    if ref not in history:
        return jsonify({"status": "error", "message": "Answer not found"})
    
    try:
        ref_index = history.index(ref)
        
        answers_to_remove = history[ref_index:]
        for removed_ref in answers_to_remove:
            if removed_ref in session["answers"]:
                del session["answers"][removed_ref]
            proposal_keys = [k for k in session["answers"].keys() if k.startswith(f"proposal_{removed_ref}")]
            for key in proposal_keys:
                del session["answers"][key]
        
        if "estimation_data" in session:
            session["estimation_data"] = {}
        
        session["history"] = history[:ref_index]
        
        if ref in PHASE_1_QUESTIONS:
            session["phase"] = 1
            session["phase_transition_shown"] = False
        elif ref in PHASE_2_QUESTIONS:
            session["phase"] = 2
        
        session["current_ref"] = ref
        session["waiting_for_answer"] = False
        session["pending_proposal"] = None
        session["completed"] = False
        
        msg_index_to_keep = -1
        
        question_obj = get_question(ref)
        if question_obj:
            title = question_obj.get("title", "")
            if callable(title):
                title = title(session.get("answers", {}))
            
            for i, msg in enumerate(session["messages"]):
                if msg.get("role") == "assistant" and title and title in msg.get("content", ""):
                    msg_index_to_keep = i
                    break
        
        if msg_index_to_keep == -1:
            for i, msg in enumerate(session["messages"]):
                if msg.get("role") == "assistant" and ref in msg.get("content", ""):
                    msg_index_to_keep = i
                    break
        
        if msg_index_to_keep == -1:
            for i in range(len(session["messages"]) - 1, -1, -1):
                msg = session["messages"][i]
                if msg.get("role") == "user":
                    if i > 0 and i < len(session["messages"]):
                        msg_index_to_keep = i - 1
                        break
        
        if msg_index_to_keep >= 0:
            session["messages"] = session["messages"][:msg_index_to_keep]
        
        session.modified = True
        
        question = get_question(ref)
        if question:
            question_text = get_question_text(question)
            options = get_options(question)
            input_type = get_question_type(question)
            
            edit_message = f"✏️ **Editing your answer to:**\n\n{question_text}"
            add_message("assistant", edit_message, options, input_type)
            session["waiting_for_answer"] = True
            session.modified = True
            
            return jsonify({"status": "success", "current_ref": ref, "message": "You can now edit your answer and continue"})
        
        return jsonify({"status": "error", "message": "Question not found"})
        
    except Exception as e:
        logger.error(f"Error in edit_answer: {e}")
        return jsonify({"status": "error", "message": str(e)})

# =========================================================
# CHAT ROUTE
# =========================================================

@app.route("/chat")
@safe_route
def chat():
    if not session.get("passkey_verified"):
        return redirect(url_for("passkey_page"))
    
    if not session.get("savy_authenticated") and not SAVY_USER_ID:
        return redirect(url_for("login_page"))
    
    if not session.get("estimation_initiated") and not session.get("completed"):
        try:
            logger.info("🔄 Initiating refund estimation on chat start...")
            result = initiate_refund_estimation()
            if result.get("success"):
                session["estimation_initiated"] = True
                logger.info(f"✅ Refund estimation initiated with ID: {session.get('refund_estimation_id')}")
            else:
                logger.warning(f"⚠️ Failed to initiate refund estimation: {result.get('error')}")
        except Exception as e:
            logger.error(f"Error initiating refund estimation: {e}")
    
    if not session.get("tax_estimation_initiated") and not session.get("completed"):
        try:
            logger.info("🔄 Initiating tax estimation on chat start...")
            result = initiate_tax_estimation()
            if result.get("success"):
                session["tax_estimation_initiated"] = True
                logger.info(f"✅ Tax estimation initiated with ID: {session.get('tax_estimation_id')}")
            else:
                logger.warning(f"⚠️ Failed to initiate tax estimation: {result.get('error')}")
        except Exception as e:
            logger.error(f"Error initiating tax estimation: {e}")
    
    if not session.get("messages") and not session.get("completed"):
        session["awaiting_greeting"] = True
        session["awaiting_ok"] = False
    
    answers_list = []
    for ref in session.get("history", []):
        if ref in session["answers"]:
            question = get_question(ref)
            if question:
                title = question.get("title", ref)
                if callable(title):
                    title = title(session.get("answers", {}))
                answers_list.append({
                    "ref": ref,
                    "title": title[:50] + "..." if len(title) > 50 else title,
                    "answer": format_answer_for_display(question, session["answers"][ref])
                })
    
    all_conversations = get_all_conversations()
    
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
    <title>SAVY - Tax Assistant</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; 
            background: #f5f5f5; 
            height: 100vh; 
            overflow: hidden;
        }
        
        .app-container {
            display: flex;
            height: 100vh;
            width: 100%;
        }
        
        .sidebar {
            width: 260px;
            background: white;
            border-right: 1px solid #e0e0e0;
            display: flex;
            flex-direction: column;
            box-shadow: 2px 0 12px rgba(0,0,0,0.04);
            z-index: 10;
            overflow-y: auto;
            transition: width 0.3s ease;
            flex-shrink: 0;
        }
        
        .sidebar-logo {
            padding: 20px 16px 16px 16px;
            text-align: center;
            border-bottom: 1px solid #f0f0f0;
            background: white;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 12px;
        }
        
        .savy-logo-sidebar {
            height: 32px;
            width: auto;
        }
        
        .new-chat-btn {
            background: #d63384;
            color: white;
            border: none;
            border-radius: 20px;
            padding: 8px 20px;
            font-size: 0.8em;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.25s ease;
            white-space: nowrap;
            width: 100%;
            max-width: 180px;
        }
        
        .new-chat-btn:hover {
            background: #b02a6e;
            transform: scale(1.02);
        }
        
        .sidebar-nav {
            padding: 12px 12px;
            border-bottom: 1px solid #f0f0f0;
            display: flex;
            justify-content: center;
        }
        
        .nav-item {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            color: #555;
            font-size: 0.85em;
            font-weight: 500;
            justify-content: center;
            width: 100%;
            max-width: 180px;
        }
        
        .nav-item:hover {
            background: #f5f5f7;
        }
        
        .nav-item.active {
            background: #f0f0f4;
            color: #d63384;
        }
        
        .nav-icon {
            font-size: 1em;
            width: 20px;
            text-align: center;
        }
        
        .sidebar-recent {
            flex: 1;
            overflow-y: auto;
            padding: 8px 12px;
        }
        
        .recent-label {
            font-size: 0.65em;
            text-transform: uppercase;
            color: #999;
            font-weight: 600;
            letter-spacing: 0.5px;
            padding: 12px 8px 6px 8px;
        }
        
        .conversation-item {
            padding: 8px 12px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            font-size: 0.82em;
            color: #444;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 8px;
        }
        
        .conversation-item:hover {
            background: #f5f5f7;
        }
        
        .conversation-item.active {
            background: #f0f0f4;
            color: #d63384;
        }
        
        .conversation-title {
            flex: 1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .conversation-delete {
            opacity: 0;
            color: #ccc;
            cursor: pointer;
            font-size: 0.8em;
            padding: 0 4px;
            transition: all 0.2s ease;
        }
        
        .conversation-item:hover .conversation-delete {
            opacity: 1;
        }
        
        .conversation-delete:hover {
            color: #d63384;
        }
        
        .answers-list {
            flex: 1;
            overflow-y: auto;
            padding: 12px 16px;
        }
        
        .answer-item {
            background: #f8f8fa;
            border-radius: 10px;
            padding: 12px 14px;
            margin-bottom: 10px;
            cursor: pointer;
            transition: all 0.25s ease;
            border: 1.5px solid #e8e8ec;
        }
        
        .answer-item:hover {
            background: #f0f0f4;
            transform: translateX(-3px);
            border-color: #d63384;
            box-shadow: 0 4px 12px rgba(214, 51, 132, 0.1);
        }
        
        .answer-question {
            font-size: 0.75em;
            font-weight: 700;
            color: #555;
            margin-bottom: 4px;
        }
        
        .answer-value {
            font-size: 1em;
            color: #d63384;
            font-weight: 600;
            word-break: break-word;
            line-height: 1.3;
        }
        
        .answer-number {
            display: inline-block;
            background: #d63384;
            color: white;
            font-size: 0.6em;
            font-weight: 700;
            padding: 1px 8px;
            border-radius: 10px;
            margin-right: 6px;
        }
        
        .edit-icon {
            float: right;
            color: #ccc;
            font-size: 0.75em;
            cursor: pointer;
            transition: color 0.2s ease;
            opacity: 0;
            padding: 1px 3px;
        }
        
        .answer-item:hover .edit-icon {
            opacity: 1;
        }
        
        .edit-icon:hover {
            color: #d63384;
        }
        
        .no-answers {
            text-align: center;
            color: #bbb;
            padding: 30px 16px;
            font-size: 0.85em;
            line-height: 1.6;
        }
        
        .no-answers-icon {
            font-size: 2.2em;
            margin-bottom: 10px;
            opacity: 0.5;
            display: block;
        }
        
        .chat-container {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: #fafafa;
            position: relative;
            min-width: 0;
        }
        
        .messages-container { 
            flex: 1; 
            overflow-y: auto; 
            padding: 16px 28px 12px 28px;
            background: #fafafa;
            display: flex;
            flex-direction: column;
        }
        
        .message { 
            margin-bottom: 14px; 
            display: flex; 
            animation: messageSlideIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
            opacity: 0;
            transform: translateY(10px) scale(0.98);
            flex-shrink: 0;
        }
        @keyframes messageSlideIn { 
            from { 
                opacity: 0; 
                transform: translateY(10px) scale(0.98);
            } 
            to { 
                opacity: 1; 
                transform: translateY(0) scale(1);
            } 
        }
        
        .message.user { 
            justify-content: flex-end; 
        }
        .message.assistant { 
            justify-content: flex-start; 
        }
        
        .message-avatar {
            width: 34px;
            height: 34px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            margin-top: 2px;
            font-size: 15px;
            font-weight: 600;
        }
        
        .message.assistant .message-avatar {
            background: linear-gradient(135deg, #d63384, #b02a6e);
            color: white;
            margin-right: 12px;
        }
        
        .message.user .message-avatar {
            background: #e8e8ec;
            color: #666;
            margin-left: 12px;
            order: 1;
        }
        
        .message-content-wrapper {
            max-width: 80%;
            display: flex;
            flex-direction: column;
            min-width: 0;
        }
        
        .message.user .message-content-wrapper {
            align-items: flex-end;
        }
        
        .message-content { 
            padding: 12px 18px; 
            border-radius: 18px; 
            line-height: 1.6; 
            white-space: pre-wrap; 
            word-wrap: break-word;
            font-size: 0.92em;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            max-width: 100%;
            width: 100%;
        }
        
        .message.user .message-content { 
            background: linear-gradient(135deg, #d63384, #b02a6e);
            color: white; 
            border-bottom-right-radius: 4px;
            font-weight: 500;
            font-size: 0.9em;
        }
        
        .message.assistant .message-content { 
            background: white; 
            color: #333; 
            border-bottom-left-radius: 4px;
            border: 1px solid #eee;
            font-size: 0.9em;
        }
        
        .message-timestamp {
            font-size: 0.6em;
            color: #bbb;
            margin-top: 4px;
            padding: 0 4px;
        }
        
        .message.user .message-timestamp {
            text-align: right;
        }
        
        .options-container { 
            margin-top: 12px; 
            display: flex; 
            flex-wrap: wrap;
            gap: 8px; 
            padding: 4px 0;
            width: 100%;
        }
        
        .option-btn { 
            background: white; 
            border: 2px solid #e0e0e0; 
            padding: 8px 16px; 
            border-radius: 24px; 
            cursor: pointer; 
            transition: all 0.25s ease; 
            font-size: 0.85em; 
            color: #444;
            font-weight: 600;
            white-space: normal;
            word-break: break-word;
            flex: 0 1 auto;
            max-width: 100%;
            text-align: center;
            line-height: 1.4;
        }
        
        .option-btn:hover { 
            border-color: #d63384; 
            color: #d63384;
            transform: translateY(-2px);
            box-shadow: 0 3px 12px rgba(214, 51, 132, 0.15);
            background: #fff;
        }
        
        .option-btn:active {
            transform: scale(0.95);
        }
        
        .option-btn.selected { 
            background: #d63384; 
            color: white; 
            border-color: #d63384;
            box-shadow: 0 2px 10px rgba(214, 51, 132, 0.2);
        }
        
        .message-content .options-container {
            margin-top: 12px;
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            padding: 4px 0;
            width: 100%;
        }
        
        .message-content .options-container .option-btn {
            background: white;
            border: 2px solid #e0e0e0;
            padding: 8px 16px;
            border-radius: 24px;
            cursor: pointer;
            transition: all 0.25s ease;
            font-size: 0.85em;
            color: #444;
            font-weight: 600;
            white-space: normal;
            word-break: break-word;
            flex: 0 1 auto;
            max-width: 100%;
            text-align: center;
            line-height: 1.4;
        }
        
        .message-content .options-container .option-btn:hover {
            border-color: #d63384;
            color: #d63384;
            transform: translateY(-2px);
            box-shadow: 0 3px 12px rgba(214, 51, 132, 0.15);
        }
        
        .message-content .options-container .option-btn.selected {
            background: #d63384;
            color: white;
            border-color: #d63384;
            box-shadow: 0 2px 10px rgba(214, 51, 132, 0.2);
        }
        
        .input-container { 
            background: white; 
            border-top: 1px solid #eee; 
            padding: 14px 24px; 
            display: flex; 
            gap: 12px; 
            box-shadow: 0 -2px 8px rgba(0,0,0,0.02);
            flex-shrink: 0;
        }
        
        .input-container input { 
            flex: 1; 
            padding: 10px 18px; 
            border: 2px solid #e8e8ec; 
            border-radius: 24px; 
            font-size: 0.9em; 
            outline: none; 
            transition: all 0.25s ease;
            background: #f8f8fa;
        }
        
        .input-container input:focus { 
            border-color: #d63384; 
            background: white;
            box-shadow: 0 0 0 3px rgba(214, 51, 132, 0.06);
        }
        
        .input-container input::placeholder {
            color: #bbb;
            font-weight: 400;
            font-size: 0.9em;
        }
        
        .input-container button { 
            background: linear-gradient(135deg, #d63384, #b02a6e);
            color: white; 
            border: none; 
            padding: 10px 26px; 
            border-radius: 24px; 
            cursor: pointer; 
            font-size: 0.88em; 
            font-weight: 700; 
            transition: all 0.25s ease;
            white-space: nowrap;
            box-shadow: 0 2px 8px rgba(214, 51, 132, 0.15);
            letter-spacing: 0.3px;
        }
        
        .input-container button:hover { 
            transform: translateY(-2px);
            box-shadow: 0 4px 16px rgba(214, 51, 132, 0.25);
        }
        
        .input-container button:active {
            transform: scale(0.96);
        }
        
        .input-container button:disabled { 
            opacity: 0.5; 
            cursor: not-allowed; 
            transform: none !important;
            box-shadow: none !important;
        }
        
        .restart-btn { 
            background: white; 
            color: #666; 
            border: 2px solid #e8e8ec; 
            margin-top: 0;
            width: 100%;
            box-shadow: none !important;
            background: #f8f8fa;
            font-weight: 600;
            font-size: 0.88em;
        }
        
        .restart-btn:hover { 
            background: white; 
            color: #d63384; 
            border-color: #d63384;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(214, 51, 132, 0.08) !important;
        }
        
        .ai-thinking {
            display: inline-flex;
            align-items: center;
            gap: 10px;
            padding: 10px 18px;
            background: white;
            border-radius: 20px;
            border-bottom-left-radius: 4px;
            border: 1px solid #eee;
        }
        
        .ai-spinner {
            width: 18px;
            height: 18px;
            border: 2.5px solid #f0f0f0;
            border-top: 2.5px solid #d63384;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .ai-thinking-text {
            font-size: 0.85em;
            color: #d63384;
            font-weight: 600;
        }
        .ai-pulse {
            animation: subtlePulse 1.4s ease-in-out infinite;
        }
        @keyframes subtlePulse {
            0%, 100% { opacity: 0.6; }
            50% { opacity: 1; }
        }
        
        .typing-indicator {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 10px 16px;
            background: white;
            border-radius: 18px;
            border-bottom-left-radius: 4px;
            border: 1px solid #eee;
        }
        .typing-dot {
            width: 8px;
            height: 8px;
            background: #d63384;
            border-radius: 50%;
            animation: typingPulse 1.4s infinite ease-in-out;
        }
        .typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .typing-dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes typingPulse {
            0%, 60%, 100% { transform: scale(0.5); opacity: 0.3; }
            30% { transform: scale(1); opacity: 1; }
        }
        
        .answers-list::-webkit-scrollbar,
        .messages-container::-webkit-scrollbar,
        .sidebar-recent::-webkit-scrollbar {
            width: 4px;
        }
        .answers-list::-webkit-scrollbar-track,
        .messages-container::-webkit-scrollbar-track,
        .sidebar-recent::-webkit-scrollbar-track {
            background: transparent;
        }
        .answers-list::-webkit-scrollbar-thumb,
        .messages-container::-webkit-scrollbar-thumb,
        .sidebar-recent::-webkit-scrollbar-thumb {
            background: #ddd;
            border-radius: 4px;
        }
        .answers-list::-webkit-scrollbar-thumb:hover,
        .messages-container::-webkit-scrollbar-thumb:hover,
        .sidebar-recent::-webkit-scrollbar-thumb:hover {
            background: #d63384;
        }
        
        .chat-progress {
            padding: 4px 20px 8px 20px;
            text-align: center;
            font-size: 0.65em;
            color: #aaa;
            letter-spacing: 0.3px;
            font-weight: 500;
            flex-shrink: 0;
        }
        
        .chat-progress-bar {
            height: 3px;
            background: #eee;
            border-radius: 4px;
            margin-top: 4px;
            overflow: hidden;
        }
        
        .chat-progress-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, #d63384, #b02a6e);
            border-radius: 4px;
            transition: width 0.5s ease;
            width: 0%;
        }
        
        @media (max-width: 768px) { 
            .message-content-wrapper { max-width: 85%; } 
            .input-container { padding: 10px 14px; }
            .sidebar { width: 200px; }
            .savy-logo-sidebar { height: 24px; }
            .messages-container { padding: 12px 14px 10px 14px; }
            .sidebar-logo { padding: 12px 12px; }
            .message-content { font-size: 0.88em; padding: 10px 16px; }
            .option-btn { padding: 6px 14px; font-size: 0.8em; }
            .answer-item { padding: 10px 12px; }
            .answer-value { font-size: 0.9em; }
            .input-container input { padding: 8px 14px; font-size: 0.85em; }
            .input-container button { padding: 8px 18px; font-size: 0.82em; }
            .message-avatar { width: 28px; height: 28px; font-size: 12px; }
            .conversation-item { font-size: 0.75em; padding: 6px 10px; }
            .nav-item { font-size: 0.75em; padding: 6px 10px; }
            .new-chat-btn { font-size: 0.65em; padding: 4px 10px; }
        }
    </style>
</head>
<body>
    <div class="app-container">
        <div class="sidebar" id="sidebar">
            <div class="sidebar-logo">
                <svg class="savy-logo-sidebar" viewBox="0 0 200 60" xmlns="http://www.w3.org/2000/svg">
                    <text x="50%" y="42" text-anchor="middle" font-family="Arial, sans-serif" font-size="42" font-weight="bold" fill="#1a1a2e">SAVY</text>
                    <circle cx="50%" cy="12" r="7" fill="#d63384"/>
                </svg>
                <button class="new-chat-btn" onclick="window.location.href='/start_new_assessment'">+ New Chat</button>
            </div>
            
            <div class="sidebar-nav">
                <div class="nav-item active">
                    <span class="nav-icon">💬</span>
                    <span>Chat</span>
                </div>
            </div>
            
            <div class="sidebar-recent" id="sidebar-recent">
                <div class="recent-label">📁 Recent</div>
                <div id="conversation-list">
                    <!-- Conversations will be loaded here -->
                </div>
            </div>
            
            <div style="border-top: 1px solid #f0f0f0; padding: 12px 16px;">
                <div style="display: flex; align-items: center; gap: 10px; font-size: 0.75em; color: #999;">
                    <span>👤</span>
                    <span>User</span>
                </div>
            </div>
        </div>
        
        <div class="chat-container">
            <div class="messages-container" id="messages-container">
                <!-- No automatic greeting message - it will appear after user says Hello -->
                {% for message in messages %}
                    <div class="message {{ message.role }}" style="animation: messageSlideIn 0.3s ease-out forwards;">
                        <div class="message-avatar">
                            {% if message.role == 'assistant' %}🤖{% else %}👤{% endif %}
                        </div>
                        <div class="message-content-wrapper">
                            <div class="message-content">
                                {{ message.content | replace('\\n', '<br>') | safe }}
                                {% if message.options and message.options|length > 0 %}
                                    <div class="options-container">
                                        {% for option in message.options %}
                                            <button class="option-btn" onclick="sendMessage('{{ option | replace("'", "\\'") | replace("\\n", " ") }}')">
                                                {{ option | replace('\\n', ' ') }}
                                            </button>
                                        {% endfor %}
                                    </div>
                                {% endif %}
                            </div>
                            <div class="message-timestamp">
                                {% if message.timestamp %}
                                    {{ message.timestamp | replace('T', ' ') | truncate(16, True, '') }}
                                {% endif %}
                            </div>
                        </div>
                    </div>
                {% endfor %}
            </div>
            
            <div class="input-container" style="{% if completed %}border-top: none;{% endif %}">
                <input type="text" id="message-input" placeholder="Type your answer here..." autocomplete="off" {% if completed %}disabled{% endif %}>
                <button onclick="sendMessage()" id="send-btn" {% if completed %}disabled{% endif %}>Send →</button>
            </div>
            
            {% if completed %}
                <div class="input-container" style="border-top: none; padding-top: 0;">
                    <button onclick="window.location.href='/start_new_assessment'" class="restart-btn">🔄 Start New Assessment</button>
                </div>
            {% endif %}
        </div>
    </div>
    
    <script>
        const messagesContainer = document.getElementById('messages-container');
        const messageInput = document.getElementById('message-input');
        const sendBtn = document.getElementById('send-btn');
        let isWaitingForResponse = false;
        
        function scrollToBottom() { 
            messagesContainer.scrollTop = messagesContainer.scrollHeight; 
        }
        
        function autoScroll() {
            messagesContainer.scrollTo({
                top: messagesContainer.scrollHeight,
                behavior: 'smooth'
            });
        }
        
        // Slower typing effect - increased delay between characters
        function typeMessage(element, text, speed = 25) {
            return new Promise((resolve) => {
                let index = 0;
                element.innerHTML = '';
                
                const parts = text.split(/(<[^>]*>)/g);
                let currentText = '';
                
                function typeNext() {
                    if (index >= parts.length) {
                        resolve();
                        return;
                    }
                    
                    const part = parts[index];
                    
                    if (part.startsWith('<') && part.endsWith('>')) {
                        currentText += part;
                        element.innerHTML = currentText;
                        index++;
                        autoScroll();
                        setTimeout(typeNext, 10);
                        return;
                    }
                    
                    if (part.length > 0) {
                        let charIndex = 0;
                        const textPart = part;
                        
                        function typeChar() {
                            if (charIndex < textPart.length) {
                                currentText += textPart[charIndex];
                                element.innerHTML = currentText;
                                charIndex++;
                                autoScroll();
                                // Slower: 25-40ms per character with variation
                                const delay = 25 + Math.random() * 15;
                                setTimeout(typeChar, delay);
                            } else {
                                index++;
                                setTimeout(typeNext, 10);
                            }
                        }
                        typeChar();
                    } else {
                        index++;
                        setTimeout(typeNext, 10);
                    }
                }
                
                typeNext();
            });
        }
        
        function loadConversations() {
            fetch('/api/conversations')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        renderConversations(data.conversations);
                    }
                })
                .catch(error => console.error('Error loading conversations:', error));
        }
        
        function renderConversations(conversations) {
            const container = document.getElementById('conversation-list');
            let html = '';
            
            const folderOrder = ['Today', 'Yesterday', 'Previous 7 Days', 'Older'];
            
            for (const folder of folderOrder) {
                const convs = conversations[folder] || [];
                if (convs.length > 0) {
                    html += `<div class="recent-label">${folder}</div>`;
                    for (const conv of convs) {
                        const isActive = conv.id === '{{ conversation_id }}';
                        const title = conv.title || 'New Conversation';
                        html += `
                            <div class="conversation-item ${isActive ? 'active' : ''}" onclick="loadConversation('${conv.id}')">
                                <span class="conversation-title">${title}</span>
                                <span class="conversation-delete" onclick="event.stopPropagation(); deleteConversation('${conv.id}')">✕</span>
                            </div>
                        `;
                    }
                }
            }
            
            if (!html) {
                html = `<div style="text-align: center; color: #bbb; padding: 20px; font-size: 0.8em;">No conversations yet</div>`;
            }
            
            container.innerHTML = html;
        }
        
        function loadConversation(conversationId) {
            fetch(`/api/conversation/${conversationId}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        window.location.reload();
                    }
                })
                .catch(error => console.error('Error loading conversation:', error));
        }
        
        function deleteConversation(conversationId) {
            if (confirm('Delete this conversation?')) {
                fetch(`/api/conversation/${conversationId}`, { method: 'DELETE' })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            loadConversations();
                            const currentConv = '{{ conversation_id }}';
                            if (currentConv === conversationId) {
                                window.location.href = '/chat';
                            }
                        }
                    })
                    .catch(error => console.error('Error deleting conversation:', error));
            }
        }
        
        function editAnswer(ref) {
            if (confirm('Edit this answer? This will reset all answers after this question.')) {
                fetch('/edit_answer', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ref: ref })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        window.location.reload();
                    } else {
                        alert('Could not edit answer. Please try again.');
                    }
                });
            }
        }
        
        async function sendMessage(predefinedAnswer = null) {
            if (isWaitingForResponse) return;
            
            let answer = predefinedAnswer || messageInput.value.trim();
            if (!answer && !predefinedAnswer) return;
            
            answer = answer.replace(/\\n/g, ' ').trim();
            
            const userMsg = document.createElement('div');
            userMsg.className = 'message user';
            userMsg.innerHTML = `
                <div class="message-content-wrapper">
                    <div class="message-content">${answer.replace(/\\n/g, '<br>')}</div>
                    <div class="message-timestamp">${new Date().toLocaleTimeString()}</div>
                </div>
                <div class="message-avatar">👤</div>
            `;
            messagesContainer.appendChild(userMsg);
            
            if (!predefinedAnswer) messageInput.value = '';
            autoScroll();
            
            showAIThinkingIndicator();
            
            isWaitingForResponse = true;
            setInputEnabled(false);
            
            try {
                const response = await fetch('/send_message', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({answer: answer})
                });
                const data = await response.json();
                
                removeAIThinkingIndicator();
                setInputEnabled(true);
                
                if (data.messages && data.messages.length > 0) {
                    for (let i = 0; i < data.messages.length; i++) {
                        const msg = data.messages[i];
                        
                        const msgDiv = document.createElement('div');
                        msgDiv.className = `message ${msg.role}`;
                        
                        const contentWrapper = document.createElement('div');
                        contentWrapper.className = 'message-content-wrapper';
                        
                        const contentDiv = document.createElement('div');
                        contentDiv.className = 'message-content';
                        contentDiv.id = `msg-content-${Date.now()}-${i}`;
                        
                        const timestamp = document.createElement('div');
                        timestamp.className = 'message-timestamp';
                        timestamp.textContent = new Date().toLocaleTimeString();
                        
                        contentWrapper.appendChild(contentDiv);
                        contentWrapper.appendChild(timestamp);
                        
                        const avatar = document.createElement('div');
                        avatar.className = 'message-avatar';
                        avatar.textContent = msg.role === 'assistant' ? '🤖' : '👤';
                        
                        msgDiv.appendChild(avatar);
                        msgDiv.appendChild(contentWrapper);
                        messagesContainer.appendChild(msgDiv);
                        autoScroll();
                        
                        if (msg.role === 'assistant') {
                            // Show typing indicator
                            const typingDiv = document.createElement('div');
                            typingDiv.className = 'typing-indicator';
                            typingDiv.innerHTML = `
                                <span class="typing-dot"></span>
                                <span class="typing-dot"></span>
                                <span class="typing-dot"></span>
                            `;
                            contentDiv.appendChild(typingDiv);
                            autoScroll();
                            
                            // Longer pause before typing starts
                            await new Promise(resolve => setTimeout(resolve, 500 + Math.random() * 300));
                            
                            // Type the message - slower speed
                            contentDiv.innerHTML = '';
                            const fullText = msg.content;
                            await typeMessage(contentDiv, fullText, 25);
                            
                            if (msg.options && msg.options.length > 0) {
                                const optionsContainer = document.createElement('div');
                                optionsContainer.className = 'options-container';
                                msg.options.forEach(option => {
                                    const btn = document.createElement('button');
                                    btn.className = 'option-btn';
                                    btn.textContent = option.replace(/\\n/g, ' ');
                                    btn.onclick = () => sendMessage(option);
                                    optionsContainer.appendChild(btn);
                                });
                                contentDiv.appendChild(optionsContainer);
                            }
                        } else {
                            contentDiv.innerHTML = msg.content.replace(/\\n/g, '<br>');
                            if (msg.options && msg.options.length > 0) {
                                const optionsContainer = document.createElement('div');
                                optionsContainer.className = 'options-container';
                                msg.options.forEach(option => {
                                    const btn = document.createElement('button');
                                    btn.className = 'option-btn';
                                    btn.textContent = option.replace(/\\n/g, ' ');
                                    btn.onclick = () => sendMessage(option);
                                    optionsContainer.appendChild(btn);
                                });
                                contentDiv.appendChild(optionsContainer);
                            }
                        }
                        
                        autoScroll();
                    }
                }
                
                if (data.status === 'completed' || data.status === 'phase_complete') {
                    if (data.status === 'completed') {
                        showAIProcessingMessage();
                        await new Promise(resolve => setTimeout(resolve, 1200));
                        removeAIProcessingMessage();
                    }
                    setTimeout(() => window.location.reload(), 1000);
                }
            } catch (error) { 
                console.error('Error:', error); 
                removeAIThinkingIndicator();
                setInputEnabled(true); 
                const msgDiv = document.createElement('div');
                msgDiv.className = 'message assistant';
                msgDiv.innerHTML = `
                    <div class="message-avatar">🤖</div>
                    <div class="message-content-wrapper">
                        <div class="message-content">Sorry, there was an error. Please try again.</div>
                        <div class="message-timestamp">${new Date().toLocaleTimeString()}</div>
                    </div>
                `;
                messagesContainer.appendChild(msgDiv);
                autoScroll();
            } finally {
                isWaitingForResponse = false;
            }
        }
        
        function showAIThinkingIndicator() {
            const indicatorDiv = document.createElement('div');
            indicatorDiv.id = 'ai-thinking-indicator';
            indicatorDiv.className = 'message assistant';
            indicatorDiv.innerHTML = `
                <div class="message-avatar">🤖</div>
                <div class="message-content-wrapper">
                    <div class="message-content">
                        <div class="ai-thinking">
                            <div class="ai-spinner"></div>
                            <div class="ai-thinking-text ai-pulse">AI is analyzing...</div>
                        </div>
                    </div>
                </div>
            `;
            messagesContainer.appendChild(indicatorDiv);
            autoScroll();
        }
        
        function removeAIThinkingIndicator() {
            const indicator = document.getElementById('ai-thinking-indicator');
            if (indicator) indicator.remove();
        }
        
        function showAIProcessingMessage() {
            const msgDiv = document.createElement('div');
            msgDiv.id = 'ai-processing-msg';
            msgDiv.className = 'message assistant';
            msgDiv.innerHTML = `
                <div class="message-avatar">🤖</div>
                <div class="message-content-wrapper">
                    <div class="message-content">
                        <div class="ai-thinking" style="background: #f8f0f5; border-color: #d63384;">
                            <div class="ai-spinner"></div>
                            <div class="ai-thinking-text" style="color: #d63384;">✨ Generating your summary...</div>
                        </div>
                    </div>
                </div>
            `;
            messagesContainer.appendChild(msgDiv);
            autoScroll();
        }
        
        function removeAIProcessingMessage() {
            const msg = document.getElementById('ai-processing-msg');
            if (msg) msg.remove();
        }
        
        function setInputEnabled(enabled) {
            messageInput.disabled = !enabled;
            sendBtn.disabled = !enabled;
            if (enabled) messageInput.focus();
        }
        
        const observer = new MutationObserver(function(mutations) {
            autoScroll();
        });
        observer.observe(messagesContainer, { childList: true, subtree: true });
        
        messageInput.addEventListener('keypress', function(e) { 
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage(); 
            }
        });
        
        setTimeout(() => messageInput.focus(), 300);
        
        loadConversations();
    </script>
</body>
</html>
""", messages=session["messages"], 
         awaiting_greeting=session.get("awaiting_greeting", False),
         waiting_for_answer=session.get("waiting_for_answer", False),
         completed=session.get("completed", False),
         phase=session.get("phase", 1),
         phase_names=PHASE_NAMES,
         sidebar_open=session.get("sidebar_open", True),
         answers_list=answers_list,
         history=session.get("history", []),
         conversation_id=session.get("conversation_id"))

# =========================================================
# SEND MESSAGE ROUTE
# =========================================================

@app.route("/send_message", methods=["POST"])
@safe_route
@swag_from({
    'tags': ['Chat'],
    'summary': 'Send a message to the chat bot',
    'description': 'Processes user input and returns the bot response with typing animation',
    'parameters': [
        {
            'name': 'body',
            'in': 'body',
            'required': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'answer': {
                        'type': 'string',
                        'description': 'The user message',
                        'example': 'Hello'
                    }
                },
                'required': ['answer']
            }
        }
    ],
    'responses': {
        200: {
            'description': 'Message processed successfully',
            'schema': {
                'type': 'object',
                'properties': {
                    'status': {
                        'type': 'string',
                        'enum': ['success', 'completed', 'phase_complete', 'error']
                    },
                    'messages': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'role': {
                                    'type': 'string',
                                    'enum': ['user', 'assistant']
                                },
                                'content': {
                                    'type': 'string'
                                },
                                'options': {
                                    'type': 'array',
                                    'items': {
                                        'type': 'string'
                                    }
                                },
                                'timestamp': {
                                    'type': 'string'
                                }
                            }
                        }
                    }
                }
            },
            'examples': {
                'application/json': {
                    'status': 'success',
                    'messages': [
                        {
                            'role': 'assistant',
                            'content': '🌅 **Good morning!** Welcome to the Tax Assessment Bot!',
                            'options': None,
                            'timestamp': '2024-01-01T10:00:05'
                        }
                    ]
                }
            }
        },
        400: {
            'description': 'Invalid request',
            'schema': {
                'type': 'object',
                'properties': {
                    'status': {
                        'type': 'string',
                        'example': 'error'
                    },
                    'message': {
                        'type': 'string',
                        'example': 'Please provide an answer'
                    }
                }
            }
        }
    }
})
def send_message():
    if session.get("completed"):
        return jsonify({"status": "completed"})
    
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Invalid request"})
    
    answer = data.get("answer", "").strip()
    if not answer:
        return jsonify({"status": "error", "message": "Please provide an answer"})
    
    # Check if user is in the initial greeting flow
    if session.get("awaiting_greeting"):
        normalized_answer = answer.lower().replace("!", "").strip()
        if normalized_answer in ["hello", "hi", "hey", "hello there", "hi there", "hey there"]:
            welcome_msg = "🌅 **Good morning!**\n\n"
            welcome_msg += "Welcome to the **Tax Assessment Bot**! We'll help you determine your eligibility for tax refunds and identify tax-saving opportunities.\n\n"
            welcome_msg += "**📋 Phase 1: Refund Assessment** (5-10 questions)\n"
            welcome_msg += "First, we'll check if you're eligible for a tax refund based on your income and employment.\n\n"
            welcome_msg += "**💰 Phase 2: Savings Assessment** (5-10 questions)\n"
            welcome_msg += "Then, we'll calculate potential tax savings based on your travel and business expenses.\n\n"
            welcome_msg += "When you're ready, type **OK** to continue."
            add_message("assistant", welcome_msg)
            session["awaiting_greeting"] = False
            session["awaiting_ok"] = True
            return jsonify({"status": "success", "messages": session["messages"][-1:]})
        add_message("assistant", "Please say **Hello** or **Hi** to begin the assessment.")
        return jsonify({"status": "error", "messages": [session["messages"][-1]]})
    
    if session.get("awaiting_ok"):
        normalized_answer = answer.lower().replace("!", "").strip()
        if normalized_answer in ["ok", "okay", "sure", "ready", "yes"]:
            session["awaiting_ok"] = False
            process_next_question()
            return jsonify({"status": "success", "messages": session["messages"][-1:]})
        add_message("assistant", "Please type **OK** when you're ready to continue.")
        return jsonify({"status": "error", "messages": [session["messages"][-1]]})
    
    if not session.get("waiting_for_answer"):
        return jsonify({"status": "error", "message": "Not waiting for answer"})
    
    # Handle proposal flow
    if session.get("pending_proposal"):
        proposal_data = session["pending_proposal"]
        prop_index = proposal_data.get("current_index", 0)
        prop_questions = proposal_data.get("questions", [])
        
        if prop_index < len(prop_questions):
            prop_q = prop_questions[prop_index]
            answer_key = f"proposal_{proposal_data['original_ref']}_{prop_index}"
            
            if prop_q.get("type") in ["numeric", "number", "price", "counter"]:
                answer = clean_number(answer)
                if answer is None:
                    add_message("assistant", "Please enter a valid number.")
                    return jsonify({"status": "error", "messages": [session["messages"][-1]]})
            
            prop_q["value"] = answer
            session["answers"][answer_key] = answer
            proposal_data["current_index"] = prop_index + 1
            session["pending_proposal"] = proposal_data
            
            if prop_index + 1 >= len(prop_questions):
                session["pending_proposal"] = None
                session["waiting_for_answer"] = False
                
                original_ref = proposal_data["original_ref"]
                original_question = get_question(original_ref)
                if original_question and "proposal" in original_question:
                    original_question["proposal"][proposal_data["answer"]] = prop_questions
                
                result = process_handler_next(original_ref, proposal_data["answer"])
                
                if result.get("status") == "completed":
                    complete_assessment()
                    return jsonify({"status": "completed", "messages": session["messages"][-1:]})
                elif result.get("status") == "phase_complete":
                    session["phase"] = 2
                    session["current_ref"] = PHASE_2_QUESTIONS[0]
                    session["phase_transition_shown"] = False
                    show_phase_transition()
                    process_next_question()
                    return jsonify({"status": "phase_complete", "messages": session["messages"][-2:]})
                elif result.get("next_ref"):
                    session["current_ref"] = result["next_ref"]
                    process_next_question()
                else:
                    complete_assessment()
                    return jsonify({"status": "completed", "messages": session["messages"][-1:]})
            else:
                session["waiting_for_answer"] = False
                process_next_question()
            
            return jsonify({"status": "success", "messages": session["messages"][-1:]})
    
    # Regular question flow
    current_ref = session.get("current_ref")
    if not current_ref:
        session["current_ref"] = "1"
        current_ref = "1"
    
    question = get_question(current_ref)
    if not question:
        complete_assessment()
        return jsonify({"status": "completed"})
    
    if question.get("type") in ["numeric", "number", "price", "counter"]:
        answer = clean_number(answer)
        if answer is None:
            add_message("assistant", "Please enter a valid number (e.g., 5000 or £5,000).")
            return jsonify({"status": "error", "messages": session["messages"][-1:]})
    
    proposal_questions = handle_proposal(current_ref, answer)
    if proposal_questions:
        session["answers"][current_ref] = answer
        if current_ref not in session["history"]:
            session["history"].append(current_ref)
        session["waiting_for_answer"] = False
        process_next_question()
        return jsonify({"status": "success", "messages": session["messages"][-1:]})
    
    result = process_handler_next(current_ref, answer)
    
    session["answers"][current_ref] = answer
    if current_ref not in session["history"]:
        session["history"].append(current_ref)
    session["waiting_for_answer"] = False
    
    run_xhr_params(question, answer, current_ref)
    
    refund_estimation_id = session.get("refund_estimation_id")
    if refund_estimation_id and session.get("estimation_initiated"):
        try:
            question_obj = get_question(current_ref)
            answer_data = {
                "answers": session.get("answers", {}),
                "last_answered": current_ref,
                "current_phase": session.get("phase", 1),
                "progress": {
                    "answered": len(session.get("history", [])),
                    "total": 15
                },
                "timestamp": datetime.now().isoformat()
            }
            
            if question_obj:
                title = question_obj.get("title", current_ref)
                if callable(title):
                    title = title(session.get("answers", {}))
                answer_data["last_answer"] = {
                    "question": title,
                    "answer": session["answers"][current_ref],
                    "ref": current_ref
                }
            
            update_refund_estimation(refund_estimation_id, answer_data)
        except Exception as e:
            logger.error(f"Error updating refund estimation in real-time: {e}")
    
    tax_estimation_id = session.get("tax_estimation_id")
    if tax_estimation_id and session.get("tax_estimation_initiated"):
        try:
            question_obj = get_question(current_ref)
            answer_data = {
                "answers": session.get("answers", {}),
                "last_answered": current_ref,
                "current_phase": session.get("phase", 1),
                "progress": {
                    "answered": len(session.get("history", [])),
                    "total": 15
                },
                "timestamp": datetime.now().isoformat()
            }
            
            if question_obj:
                title = question_obj.get("title", current_ref)
                if callable(title):
                    title = title(session.get("answers", {}))
                answer_data["last_answer"] = {
                    "question": title,
                    "answer": session["answers"][current_ref],
                    "ref": current_ref
                }
            
            update_tax_estimation(tax_estimation_id, answer_data)
        except Exception as e:
            logger.error(f"Error updating tax estimation in real-time: {e}")
    
    if result.get("status") == "completed":
        complete_assessment()
        return jsonify({"status": "completed", "messages": session["messages"][-1:]})
    
    elif result.get("status") == "phase_complete":
        session["phase"] = 2
        session["current_ref"] = PHASE_2_QUESTIONS[0]
        session["phase_transition_shown"] = False
        show_phase_transition()
        process_next_question()
        return jsonify({"status": "phase_complete", "messages": session["messages"][-2:]})
    
    elif result.get("next_ref"):
        session["current_ref"] = result["next_ref"]
        process_next_question()
        return jsonify({"status": "success", "messages": session["messages"][-1:]})
    
    else:
        complete_assessment()
        return jsonify({"status": "completed", "messages": session["messages"][-1:]})

# =========================================================
# SAVY API ROUTES - REFUND ESTIMATION
# =========================================================

@app.route("/api/savy/initiate-refund", methods=["POST"])
@safe_route
@swag_from({
    'tags': ['Estimations'],
    'summary': 'Initiate a refund estimation',
    'description': 'Creates a new refund estimation with empty body.',
    'responses': {
        200: {
            'description': 'Refund estimation initiated',
            'schema': {
                'type': 'object',
                'properties': {
                    'success': {'type': 'boolean'},
                    'message': {'type': 'string'},
                    'estimation_id': {'type': 'string'},
                    'data': {'type': 'object'}
                }
            }
        },
        500: {
            'description': 'Internal server error'
        }
    }
})
def initiate_refund():
    try:
        result = initiate_refund_estimation()
        if result.get("success"):
            return jsonify({
                "success": True,
                "message": "Refund estimation initiated successfully",
                "estimation_id": result.get("estimation_id"),
                "data": result.get("data")
            })
        else:
            return jsonify({
                "success": False,
                "error": result.get("error", "Failed to initiate refund estimation")
            }), 500
    except Exception as e:
        logger.error(f"Error in initiate_refund: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/savy/update-refund", methods=["POST"])
@safe_route
@swag_from({
    'tags': ['Estimations'],
    'summary': 'Update refund estimation in real-time',
    'description': 'Updates the refund estimation with client answers in real-time.',
    'parameters': [
        {
            'name': 'body',
            'in': 'body',
            'required': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'estimation_id': {'type': 'string', 'description': 'The estimation ID'},
                    'answers': {'type': 'object', 'description': 'User answers'},
                    'last_answered': {'type': 'string', 'description': 'Last answered question ref'},
                    'current_phase': {'type': 'integer', 'description': 'Current phase number'},
                    'progress': {'type': 'object', 'description': 'Progress information'}
                }
            }
        }
    ],
    'responses': {
        200: {
            'description': 'Estimation updated successfully'
        },
        400: {
            'description': 'Invalid request'
        }
    }
})
def update_refund():
    try:
        data = request.get_json() or {}
        estimation_id = data.get("estimation_id") or session.get("refund_estimation_id")
        
        if not estimation_id:
            return jsonify({"error": "No estimation ID provided"}), 400
        
        answer_data = {
            "answers": session.get("answers", {}),
            "last_answered": session.get("current_ref"),
            "current_phase": session.get("phase", 1),
            "progress": {
                "answered": len(session.get("history", [])),
                "total": 15
            },
            "timestamp": datetime.now().isoformat()
        }
        
        current_ref = session.get("current_ref")
        if current_ref and current_ref in session.get("answers", {}):
            question = get_question(current_ref)
            if question:
                title = question.get("title", current_ref)
                if callable(title):
                    title = title(session.get("answers", {}))
                answer_data["last_answer"] = {
                    "question": title,
                    "answer": session["answers"][current_ref],
                    "ref": current_ref
                }
        
        result = update_refund_estimation(estimation_id, answer_data)
        
        if result.get("success"):
            return jsonify({"success": True, "data": result.get("data")})
        else:
            return jsonify({"success": False, "error": result.get("error")}), 500
    except Exception as e:
        logger.error(f"Error in update_refund: {e}")
        return jsonify({"error": str(e)}), 500

# =========================================================
# SAVY API ROUTES - TAX ESTIMATION
# =========================================================

@app.route("/api/savy/initiate-estimation", methods=["POST"])
@safe_route
@swag_from({
    'tags': ['Estimations'],
    'summary': 'Initiate a tax estimation',
    'description': 'Creates a new tax estimation with user ID and start date.',
    'parameters': [
        {
            'name': 'body',
            'in': 'body',
            'required': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'userId': {'type': 'string', 'description': 'User ID'},
                    'startDate': {'type': 'string', 'description': 'Start date (YYYY-MM-DD)'}
                },
                'required': ['userId', 'startDate']
            }
        }
    ],
    'responses': {
        200: {
            'description': 'Estimation initiated successfully'
        },
        401: {
            'description': 'Authentication required'
        }
    }
})
def initiate_estimation():
    try:
        if not session.get("savy_authenticated") and not SAVY_USER_ID:
            return jsonify({
                "success": False,
                "error": "User not authenticated. Please login first."
            }), 401
        
        result = initiate_tax_estimation()
        
        if result.get("success"):
            return jsonify({
                "success": True,
                "message": "Tax estimation initiated successfully",
                "estimation_id": result.get("estimation_id"),
                "data": result.get("data")
            })
        else:
            return jsonify({
                "success": False,
                "error": result.get("error", "Failed to initiate tax estimation")
            }), 500
    except Exception as e:
        logger.error(f"Error in initiate_estimation: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/savy/update-estimation", methods=["POST"])
@safe_route
@swag_from({
    'tags': ['Estimations'],
    'summary': 'Update tax estimation in real-time',
    'description': 'Updates the tax estimation with client answers in real-time.',
    'parameters': [
        {
            'name': 'body',
            'in': 'body',
            'required': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'estimation_id': {'type': 'string', 'description': 'The estimation ID'},
                    'answers': {'type': 'object', 'description': 'User answers'},
                    'last_answered': {'type': 'string', 'description': 'Last answered question ref'}
                }
            }
        }
    ],
    'responses': {
        200: {
            'description': 'Estimation updated successfully'
        }
    }
})
def update_estimation():
    try:
        data = request.get_json() or {}
        estimation_id = data.get("estimation_id") or session.get("tax_estimation_id")
        
        if not estimation_id:
            return jsonify({"error": "No estimation ID provided"}), 400
        
        answer_data = {
            "answers": session.get("answers", {}),
            "last_answered": session.get("current_ref"),
            "current_phase": session.get("phase", 1),
            "progress": {
                "answered": len(session.get("history", [])),
                "total": 15
            },
            "timestamp": datetime.now().isoformat()
        }
        
        current_ref = session.get("current_ref")
        if current_ref and current_ref in session.get("answers", {}):
            question = get_question(current_ref)
            if question:
                title = question.get("title", current_ref)
                if callable(title):
                    title = title(session.get("answers", {}))
                answer_data["last_answer"] = {
                    "question": title,
                    "answer": session["answers"][current_ref],
                    "ref": current_ref
                }
        
        result = update_tax_estimation(estimation_id, answer_data)
        
        if result.get("success"):
            return jsonify({"success": True, "data": result.get("data")})
        else:
            return jsonify({"success": False, "error": result.get("error")}), 500
    except Exception as e:
        logger.error(f"Error in update_estimation: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/savy/get-estimation/<estimation_id>", methods=["GET"])
@safe_route
@swag_from({
    'tags': ['Estimations'],
    'summary': 'Get a specific tax estimation by ID',
    'parameters': [
        {
            'name': 'estimation_id',
            'in': 'path',
            'type': 'string',
            'required': True,
            'description': 'The estimation ID'
        }
    ],
    'responses': {
        200: {
            'description': 'Estimation retrieved successfully'
        },
        404: {
            'description': 'Estimation not found'
        }
    }
})
def get_estimation(estimation_id):
    try:
        result = get_tax_estimation(estimation_id)
        
        if result.get("success"):
            return jsonify({"success": True, "data": result.get("data")})
        else:
            return jsonify({"success": False, "error": result.get("error")}), 404
    except Exception as e:
        logger.error(f"Error in get_estimation: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/savy/get-all-estimations", methods=["GET"])
@safe_route
@swag_from({
    'tags': ['Estimations'],
    'summary': 'Get all tax estimations for the current user',
    'responses': {
        200: {
            'description': 'Estimations retrieved successfully'
        },
        400: {
            'description': 'Error retrieving estimations'
        }
    }
})
def get_all_estimations():
    try:
        result = get_all_tax_estimations()
        
        if result.get("success"):
            return jsonify({"success": True, "data": result.get("data")})
        else:
            return jsonify({"success": False, "error": result.get("error")}), 400
    except Exception as e:
        logger.error(f"Error in get_all_estimations: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/savy/delete-estimation/<estimation_id>", methods=["DELETE"])
@safe_route
@swag_from({
    'tags': ['Estimations'],
    'summary': 'Delete a tax estimation by ID',
    'parameters': [
        {
            'name': 'estimation_id',
            'in': 'path',
            'type': 'string',
            'required': True,
            'description': 'The estimation ID to delete'
        }
    ],
    'responses': {
        200: {
            'description': 'Estimation deleted successfully'
        },
        400: {
            'description': 'Error deleting estimation'
        }
    }
})
def delete_estimation(estimation_id):
    try:
        result = delete_tax_estimation(estimation_id)
        
        if result.get("success"):
            return jsonify({"success": True, "data": result.get("data")})
        else:
            return jsonify({"success": False, "error": result.get("error")}), 400
    except Exception as e:
        logger.error(f"Error in delete_estimation: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/restart_chat", methods=["POST"])
@safe_route
def restart_chat():
    session.clear()
    init_session()
    return jsonify({"status": "success"})

if __name__ == "__main__":
    app.run(debug=True, threaded=True)

    