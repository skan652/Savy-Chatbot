from flask import Flask, request, redirect, url_for, jsonify, session
from flask import render_template_string
import json
import re
import logging
from datetime import datetime
from functools import wraps
import inspect
import os
import time
import requests

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

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VALID_PASSKEYS = ["12345", "pass123"]

# SAVY Brand Color
SAVY_PINK = "#d63384"
SAVY_GRADIENT = f"linear-gradient(45deg, {SAVY_PINK}, #a02070)"

# =========================================================
# SAVY API INTEGRATION
# =========================================================

SAVY_API_BASE_URL = os.environ.get("SAVY_API_BASE_URL", "https://api.savyapp.dev")
SAVY_TOKEN = os.environ.get("SAVY_TOKEN")

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
# SAVY API - STEP 2: INITIATE REFUND ESTIMATION
# =========================================================

def initiate_refund_estimation():
    """
    Step 2: Initiate a refund estimation with empty body
    POST /api/v1/refund-estimations
    """
    try:
        logger.info("🔄 Initiating refund estimation with Savy API...")
        
        # Make POST request with empty body
        response = make_savy_request("api/v1/refund-estimations", "POST", {})
        
        if response and not response.get("error"):
            estimation_id = response.get("id") or response.get("estimationId") or response.get("_id")
            logger.info(f"✅ Refund estimation initiated successfully! ID: {estimation_id}")
            
            # Store the estimation ID in session
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

# =========================================================
# SAVY API - STEP 3: UPDATE REFUND ESTIMATION REAL-TIME
# =========================================================

def update_refund_estimation(estimation_id, answer_data):
    """
    Step 3: Update the refund estimation in real-time with client answers
    PATCH /api/v1/refund-estimations/{id}
    """
    try:
        if not estimation_id:
            logger.warning("No estimation ID available to update")
            return {"success": False, "error": "No estimation ID"}
        
        logger.info(f"🔄 Updating refund estimation {estimation_id} with answer data...")
        
        # Make PATCH request with the answer data
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
            "last_activity": datetime.now().isoformat(),
            "error_count": 0,
            "estimation_data": {},
            "sidebar_open": True,
            "savy_estimation_id": None,
            "refund_estimation_id": None,
            "estimation_initiated": False
        }
        
        for key, default_value in defaults.items():
            if key not in session:
                session[key] = default_value
        
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
        # First try the state engine from response.json (the flow diagram)
        result = state_engine.get_next_question_ref(current_ref, answer)
        
        if result.get("status") == "success" and result.get("next_ref"):
            return {"status": "success", "next_ref": result["next_ref"], "completed": False}
        elif result.get("status") == "completed":
            return {"status": "completed"}
        
        # Fallback: use the legacy handlerNext logic for backward compatibility
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
        # Use the state machine to determine the next question
        # First, get the most recent answer
        current_answer = session.get("answers", {}).get(current_ref)
        
        if current_answer is None:
            # If no answer yet, just move to next question
            return {"status": "success", "next_ref": current_ref, "completed": False}
        
        # Use the state engine to get next question based on current answer
        result = state_engine.get_next_question_ref(current_ref, current_answer)
        
        if result.get("status") == "success" and result.get("next_ref"):
            return {"status": "success", "next_ref": result["next_ref"], "completed": False}
        elif result.get("status") == "completed":
            return {"status": "completed"}
        else:
            # If no explicit handler, we're at the end
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
            transition_msg += "---\n\n"
            transition_msg += "Now let's move to the next step: **💰 Savings Assessment**\n"
            transition_msg += "Please answer the following questions about your travel and expenses to calculate your potential tax savings.\n"
            transition_msg += "\n---\n"
            
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
        # Prepare data for Savy API
        savy_data = {
            "phase": phase,
            "phase_name": phase_name,
            "answers": answers,
            "completed_at": datetime.now().isoformat(),
            "user_answers": {}
        }
        
        # Format answers for Savy
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
        
        # Send to Savy API - CORRECT ENDPOINT
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
        
        # Build plain text summary for AI and display
        plain_summary = f"{phase_name} Summary:\n\n"
        for ref, answer in answers.items():
            question = get_question(ref)
            if question:
                title = question.get("title", ref)
                if callable(title):
                    title = title(answers)
                plain_summary += f"{title}\n→ {answer}\n\n"
        
        # Try to get AI summary with clear logging
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
        
        # Add a "AI is thinking" message that will be shown in the UI
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
                
                # Simulate a small delay to make AI processing visible
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
        
        # Remove the thinking message from messages list
        if session["messages"] and "AI Assistant is analyzing your responses" in session["messages"][-1].get("content", ""):
            session["messages"].pop()
        
        # Send data to Savy API
        send_to_savy(answers, phase, phase_name, ai_summary)
        
        # Build final message
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
            final_message += f"> {ai_summary}\n\n"
            final_message += "---\n\n"
            final_message += "💡 *This AI-generated summary helps our tax specialists better understand your situation.*\n\n"
        else:
            logger.warning("❌ No AI summary to add to final message")
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
        
        logger.info(f"✅ Assessment complete and message added to session")
        logger.info(f"{'='*70}\n")
        
    except Exception as e:
        logger.error(f"Error in complete_assessment: {e}", exc_info=True)
        add_message("assistant", "Thank you for completing the assessment!")

def format_answer_for_display(question, answer):
    """Format answer nicely for sidebar display"""
    if not question:
        return str(answer)
    
    # Clean up the answer for display
    formatted = str(answer).replace('\n', ' ')
    
    # For numeric questions, add currency symbol if needed
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
        
        allowed_routes = ["passkey_page", "verify_passkey", "static", "favicon", "toggle_sidebar", "edit_answer"]
        if request.endpoint in allowed_routes:
            return
        
        if not session.get("passkey_verified"):
            return redirect(url_for("passkey_page"))
            
    except Exception as e:
        logger.error(f"Error in before_request: {e}")
        return redirect(url_for("passkey_page"))

@app.route("/")
@safe_route
def index():
    if not session.get("passkey_verified"):
        return redirect(url_for("passkey_page"))
    return redirect(url_for("chat"))

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

# =========================================================
# FIXED EDIT_ANSWER ROUTE - Properly resets the conversation
# =========================================================
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
        # Find the index of the question to edit
        ref_index = history.index(ref)
        
        # Remove all answers from this point forward (including the one being edited)
        answers_to_remove = history[ref_index:]  # Include the edited question itself
        for removed_ref in answers_to_remove:
            if removed_ref in session["answers"]:
                del session["answers"][removed_ref]
            # Remove any proposal answers
            proposal_keys = [k for k in session["answers"].keys() if k.startswith(f"proposal_{removed_ref}")]
            for key in proposal_keys:
                del session["answers"][key]
        
        # Also remove any estimation data that might affect future calculations
        if "estimation_data" in session:
            session["estimation_data"] = {}
        
        # Trim history - keep only answers before this question
        session["history"] = history[:ref_index]
        
        # Reset phase if needed - if editing a Phase 1 question, go back to Phase 1
        if ref in PHASE_1_QUESTIONS:
            session["phase"] = 1
            session["phase_transition_shown"] = False
        elif ref in PHASE_2_QUESTIONS:
            session["phase"] = 2
        
        # Set current question to the one being edited
        session["current_ref"] = ref
        session["waiting_for_answer"] = False
        session["pending_proposal"] = None
        session["completed"] = False  # Ensure not in completed state
        
        # Find and remove messages from this point forward
        msg_index_to_keep = -1
        
        # Try to find the message containing this exact question
        question_obj = get_question(ref)
        if question_obj:
            title = question_obj.get("title", "")
            if callable(title):
                title = title(session.get("answers", {}))
            
            for i, msg in enumerate(session["messages"]):
                if msg.get("role") == "assistant" and title and title in msg.get("content", ""):
                    msg_index_to_keep = i
                    break
        
        # If not found, try to find by answer reference
        if msg_index_to_keep == -1:
            for i, msg in enumerate(session["messages"]):
                if msg.get("role") == "assistant" and ref in msg.get("content", ""):
                    msg_index_to_keep = i
                    break
        
        # If still not found, keep messages up to the answer
        if msg_index_to_keep == -1:
            # Find the last user message before this question
            for i in range(len(session["messages"]) - 1, -1, -1):
                msg = session["messages"][i]
                if msg.get("role") == "user":
                    if i > 0 and i < len(session["messages"]):
                        msg_index_to_keep = i - 1
                        break
        
        if msg_index_to_keep >= 0:
            session["messages"] = session["messages"][:msg_index_to_keep]
        
        session.modified = True
        
        # Now show the question again with an edit indicator
        question = get_question(ref)
        if question:
            question_text = get_question_text(question)
            options = get_options(question)
            input_type = get_question_type(question)
            
            # Add an edit indicator and re-ask the question
            edit_message = f"✏️ **Editing your answer to:**\n\n{question_text}"
            add_message("assistant", edit_message, options, input_type)
            session["waiting_for_answer"] = True
            session.modified = True
            
            return jsonify({"status": "success", "current_ref": ref, "message": "You can now edit your answer and continue"})
        
        return jsonify({"status": "error", "message": "Question not found"})
        
    except Exception as e:
        logger.error(f"Error in edit_answer: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route("/chat")
@safe_route
def chat():
    if not session.get("passkey_verified"):
        return redirect(url_for("passkey_page"))
    
    # Initialize refund estimation when chat starts (Step 2)
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
    
    if not session["messages"] and not session["completed"]:
        welcome_msg = "🌅 **Good morning!**\n\n"
        welcome_msg += "Welcome to the **Tax Assessment Bot**! We'll help you determine your eligibility for tax refunds and identify tax-saving opportunities.\n\n"
        welcome_msg += "**📋 Phase 1: Refund Assessment** (5-10 questions)\n"
        welcome_msg += "First, we'll check if you're eligible for a tax refund based on your income and employment.\n\n"
        welcome_msg += "**💰 Phase 2: Savings Assessment** (5-10 questions)\n"
        welcome_msg += "Then, we'll calculate potential tax savings based on your travel and business expenses.\n\n"
        welcome_msg += "Let's get started! 🚀"
        add_message("assistant", welcome_msg)
        process_next_question()
    
    # Prepare answers for sidebar
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
    
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Tax Assistant Bot</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; 
            background: #f5f5f5; 
            height: 100vh; 
            overflow: hidden;
        }
        
        /* Main layout with sidebar */
        .app-container {
            display: flex;
            height: 100vh;
            width: 100%;
        }
        
        /* Sidebar styles - NO TOP BAR, logo moved here and centered */
        .sidebar {
            width: 280px;
            background: white;
            border-right: 1px solid #e0e0e0;
            display: flex;
            flex-direction: column;
            box-shadow: 2px 0 8px rgba(0,0,0,0.05);
            z-index: 10;
            overflow-y: auto;
        }
        
        /* Logo section in sidebar - CENTERED */
        .sidebar-logo {
            padding: 32px 20px;
            text-align: center;
            border-bottom: 1px solid #e0e0e0;
            background: white;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        
        .savy-logo-sidebar {
            width: 160px;
            height: auto;
            display: block;
        }
        
        /* Sidebar header with answers title - CENTERED */
        .sidebar-header {
            padding: 16px 20px;
            background: #d63384;
            color: white;
            text-align: center;
        }
        
        .sidebar-header h3 {
            font-size: 0.95em;
            font-weight: 600;
            margin-bottom: 4px;
        }
        
        .sidebar-header p {
            font-size: 0.7em;
            opacity: 0.85;
        }
        
        .answers-list {
            flex: 1;
            overflow-y: auto;
            padding: 12px;
        }
        
        /* Optimized answer items - more compact */
        .answer-item {
            background: #f7f7f8;
            border-radius: 8px;
            padding: 10px 12px;
            margin-bottom: 10px;
            cursor: pointer;
            transition: all 0.2s;
            border: 1px solid #e0e0e0;
        }
        
        .answer-item:hover {
            background: #f0f0f0;
            transform: translateX(-2px);
            border-color: #d63384;
        }
        
        .answer-question {
            font-size: 0.75em;
            font-weight: 600;
            color: #555;
            margin-bottom: 4px;
            letter-spacing: -0.2px;
        }
        
        .answer-value {
            font-size: 0.85em;
            color: #d63384;
            font-weight: 500;
            word-break: break-word;
        }
        
        .edit-icon {
            float: right;
            color: #bbb;
            font-size: 0.7em;
            cursor: pointer;
        }
        
        .edit-icon:hover {
            color: #d63384;
        }
        
        .no-answers {
            text-align: center;
            color: #999;
            padding: 20px;
            font-size: 0.8em;
        }
        
        /* Chat container - full height, no top bar */
        .chat-container {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: white;
            position: relative;
        }
        
        /* No chat header - removed completely */
        
        .messages-container { 
            flex: 1; 
            overflow-y: auto; 
            padding: 20px 24px; 
            background: white;
        }
        
        /* Slower, more deliberate animation for message transitions */
        .message { 
            margin-bottom: 20px; 
            display: flex; 
            animation: slowFadeInUp 0.8s cubic-bezier(0.2, 0.9, 0.4, 1.1) forwards;
            opacity: 0;
        }
        @keyframes slowFadeInUp { 
            from { 
                opacity: 0; 
                transform: translateY(30px); 
            } 
            to { 
                opacity: 1; 
                transform: translateY(0); 
            } 
        }
        
        .message.user { justify-content: flex-end; }
        
        /* Optimized message content font sizes */
        .message-content { 
            max-width: 75%; 
            padding: 10px 16px; 
            border-radius: 18px; 
            line-height: 1.45; 
            white-space: pre-wrap; 
            word-wrap: break-word;
            border: 1px solid #e0e0e0;
            font-size: 0.9em;
        }
        .message.user .message-content { 
            background: white; 
            color: #333; 
            border-bottom-right-radius: 4px;
            border-color: #d63384;
        }
        .message.assistant .message-content { 
            background: #f5f5f5; 
            color: #333; 
            border-bottom-left-radius: 4px; 
            border-color: #e0e0e0;
        }
        
        .options-container { 
            margin-top: 10px; 
            display: flex; 
            flex-wrap: wrap; 
            gap: 8px; 
        }
        .option-btn { 
            background: white; 
            border: 1.5px solid #d63384; 
            padding: 6px 14px; 
            border-radius: 20px; 
            cursor: pointer; 
            transition: all 0.2s; 
            font-size: 0.8em; 
            color: #d63384;
            font-weight: 500;
        }
        .option-btn:hover { 
            background: #d63384; 
            color: white; 
            transform: translateY(-1px); 
        }
        .option-btn.selected { 
            background: #d63384; 
            color: white; 
            border-color: #d63384; 
        }
        
        .input-container { 
            background: white; 
            border-top: 1px solid #e0e0e0; 
            padding: 16px 20px; 
            display: flex; 
            gap: 12px; 
        }
        .input-container input { 
            flex: 1; 
            padding: 10px 16px; 
            border: 1.5px solid #e0e0e0; 
            border-radius: 24px; 
            font-size: 0.9em; 
            outline: none; 
        }
        .input-container input:focus { 
            border-color: #d63384; 
        }
        .input-container button { 
            background: white; 
            color: #d63384; 
            border: 1.5px solid #d63384; 
            padding: 10px 20px; 
            border-radius: 24px; 
            cursor: pointer; 
            font-size: 0.9em; 
            font-weight: 600; 
            transition: all 0.2s;
        }
        .input-container button:hover { 
            background: #d63384; 
            color: white; 
            transform: translateY(-1px); 
        }
        .input-container button:disabled { 
            opacity: 0.5; 
            cursor: not-allowed; 
            transform: none; 
        }
        
        .restart-btn { 
            background: white; 
            color: #666; 
            border: 1.5px solid #e0e0e0; 
            margin-top: 0;
            width: 100%;
        }
        .restart-btn:hover { 
            background: #f5f5f5; 
            color: #333; 
            border-color: #d63384;
            transform: translateY(-1px); 
        }
        
        /* AI Thinking / Processing Indicator */
        .ai-thinking {
            display: inline-flex;
            align-items: center;
            gap: 10px;
            padding: 8px 16px;
            background: white;
            border-radius: 20px;
            border-bottom-left-radius: 4px;
            border: 1px solid #e0e0e0;
        }
        .ai-spinner {
            width: 16px;
            height: 16px;
            border: 2px solid #f0f0f0;
            border-top: 2px solid #d63384;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .ai-thinking-text {
            font-size: 0.8em;
            color: #d63384;
            font-weight: 500;
        }
        .ai-pulse {
            animation: subtlePulse 1.2s ease-in-out infinite;
        }
        @keyframes subtlePulse {
            0%, 100% { opacity: 0.6; }
            50% { opacity: 1; }
        }
        
        /* Typing indicator */
        .typing-indicator {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 8px 14px;
            background: #f5f5f5;
            border-radius: 18px;
            border-bottom-left-radius: 4px;
            border: 1px solid #e0e0e0;
        }
        .typing-dot {
            width: 7px;
            height: 7px;
            background: #d63384;
            border-radius: 50%;
            animation: typingPulse 1.2s infinite ease-in-out;
        }
        .typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .typing-dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes typingPulse {
            0%, 60%, 100% { transform: scale(0.6); opacity: 0.4; }
            30% { transform: scale(1); opacity: 1; }
        }
        
        /* Scrollbar styling */
        .answers-list::-webkit-scrollbar,
        .messages-container::-webkit-scrollbar {
            width: 5px;
        }
        .answers-list::-webkit-scrollbar-track,
        .messages-container::-webkit-scrollbar-track {
            background: #f1f1f1;
        }
        .answers-list::-webkit-scrollbar-thumb,
        .messages-container::-webkit-scrollbar-thumb {
            background: #ccc;
            border-radius: 3px;
        }
        .answers-list::-webkit-scrollbar-thumb:hover,
        .messages-container::-webkit-scrollbar-thumb:hover {
            background: #d63384;
        }
        
        @media (max-width: 768px) { 
            .message-content { max-width: 85%; } 
            .input-container { padding: 12px 16px; }
            .sidebar { width: 260px; }
            .savy-logo-sidebar { width: 130px; }
            .messages-container { padding: 16px; }
            .sidebar-logo { padding: 24px 20px; }
        }
    </style>
</head>
<body>
    <div class="app-container">
        <!-- Sidebar - with centered logo and centered answers header -->
        <div class="sidebar" id="sidebar">
            <!-- SAVY Logo - CENTERED -->
            <div class="sidebar-logo">
                <svg class="savy-logo-sidebar" viewBox="0 0 200 60" xmlns="http://www.w3.org/2000/svg">
                    <text x="50%" y="42" text-anchor="middle" font-family="Arial, sans-serif" font-size="42" font-weight="bold" fill="#1a1a2e">SAVY</text>
                    <circle cx="50%" cy="12" r="7" fill="#d63384"/>
                </svg>
            </div>
            
            <!-- Your Answers header - CENTERED -->
            <div class="sidebar-header">
                <h3>📋 Your Answers</h3>
                <p>Click any answer to edit</p>
            </div>
            <div class="answers-list" id="answers-list">
                {% if answers_list %}
                    {% for answer in answers_list %}
                        <div class="answer-item" onclick="editAnswer('{{ answer.ref }}')">
                            <div class="answer-question">
                                {{ answer.title }}
                                <span class="edit-icon">✏️</span>
                            </div>
                            <div class="answer-value">{{ answer.answer }}</div>
                        </div>
                    {% endfor %}
                {% else %}
                    <div class="no-answers">No answers yet. Start answering questions to see them here.</div>
                {% endif %}
            </div>
        </div>
        
        <!-- Chat Container - No top bar -->
        <div class="chat-container">
            <div class="messages-container" id="messages-container">
                {% for message in messages %}
                    <div class="message {{ message.role }}" style="animation: slowFadeInUp 0.6s ease-out forwards;">
                        <div class="message-content">
                            {{ message.content | replace('\\n', '<br>') | safe }}
                            {% if message.options %}
                                <div class="options-container">
                                    {% for option in message.options %}
                                        {% set display_option = ('✓ Yes' if option == 'Yes' else '✗ No' if option == 'No' else option) %}
                                        <button class="option-btn" onclick="sendMessage('{{ option | replace("'", "\\'") | replace("\\n", " ") }}')">
                                            {{ display_option | replace('\\n', ' ') }}
                                        </button>
                                    {% endfor %}
                                </div>
                            {% endif %}
                        </div>
                    </div>
                {% endfor %}
            </div>
            
            <div class="input-container">
                <input type="text" id="message-input" placeholder="Type your answer here..." autocomplete="off">
                <button onclick="sendMessage()" id="send-btn">Send</button>
            </div>
            
            {% if completed %}
                <div class="input-container" style="border-top: none; padding-top: 0;">
                    <button onclick="restartChat()" class="restart-btn">🔄 Start New Assessment</button>
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
        scrollToBottom();
        
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
            
            addMessageToUI('user', answer);
            if (!predefinedAnswer) messageInput.value = '';
            
            // Show AI thinking indicator for assistant responses (makes AI integration obvious)
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
                
                // Remove AI thinking indicator
                removeAIThinkingIndicator();
                
                setInputEnabled(true);
                
                if (data.messages && data.messages.length > 0) {
                    // Add each message with a noticeable delay to show AI processing
                    for (let i = 0; i < data.messages.length; i++) {
                        const msg = data.messages[i];
                        
                        // Show typing indicator before each assistant message
                        if (msg.role === 'assistant') {
                            showTypingIndicator();
                            await new Promise(resolve => setTimeout(resolve, 800));
                            removeTypingIndicator();
                        }
                        
                        await new Promise(resolve => setTimeout(resolve, 300));
                        addMessageToUI(msg.role, msg.content, msg.options);
                        scrollToBottom();
                    }
                }
                
                if (data.status === 'completed' || data.status === 'phase_complete') {
                    // Show a special AI summary processing message
                    if (data.status === 'completed') {
                        showAIProcessingMessage();
                        await new Promise(resolve => setTimeout(resolve, 2000));
                        removeAIProcessingMessage();
                    }
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    // Refresh page to update sidebar after a delay
                    setTimeout(() => window.location.reload(), 800);
                }
            } catch (error) { 
                console.error('Error:', error); 
                removeAIThinkingIndicator();
                removeTypingIndicator();
                setInputEnabled(true); 
                addMessageToUI('assistant', 'Sorry, there was an error. Please try again.'); 
            } finally {
                isWaitingForResponse = false;
            }
        }
        
        function showAIThinkingIndicator() {
            const indicatorDiv = document.createElement('div');
            indicatorDiv.id = 'ai-thinking-indicator';
            indicatorDiv.className = 'message assistant';
            indicatorDiv.innerHTML = `
                <div class="message-content">
                    <div class="ai-thinking">
                        <div class="ai-spinner"></div>
                        <div class="ai-thinking-text ai-pulse">🤖 AI is analyzing your response...</div>
                    </div>
                </div>
            `;
            messagesContainer.appendChild(indicatorDiv);
            scrollToBottom();
        }
        
        function removeAIThinkingIndicator() {
            const indicator = document.getElementById('ai-thinking-indicator');
            if (indicator) indicator.remove();
        }
        
        function showTypingIndicator() {
            const indicatorDiv = document.createElement('div');
            indicatorDiv.id = 'typing-indicator';
            indicatorDiv.className = 'message assistant';
            indicatorDiv.innerHTML = `
                <div class="message-content">
                    <div class="typing-indicator">
                        <span class="typing-dot"></span>
                        <span class="typing-dot"></span>
                        <span class="typing-dot"></span>
                    </div>
                </div>
            `;
            messagesContainer.appendChild(indicatorDiv);
            scrollToBottom();
        }
        
        function removeTypingIndicator() {
            const indicator = document.getElementById('typing-indicator');
            if (indicator) indicator.remove();
        }
        
        function showAIProcessingMessage() {
            const msgDiv = document.createElement('div');
            msgDiv.id = 'ai-processing-msg';
            msgDiv.className = 'message assistant';
            msgDiv.innerHTML = `
                <div class="message-content">
                    <div class="ai-thinking" style="background: white; border-left-color: #d63384;">
                        <div class="ai-spinner"></div>
                        <div class="ai-thinking-text" style="color: #d63384;">✨ Generating your personalized AI tax summary... ✨</div>
                    </div>
                </div>
            `;
            messagesContainer.appendChild(msgDiv);
            scrollToBottom();
        }
        
        function removeAIProcessingMessage() {
            const msg = document.getElementById('ai-processing-msg');
            if (msg) msg.remove();
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
                    let displayText = option.replace(/\\n/g, ' ');
                    if (displayText === 'Yes') {
                        displayText = '✓ Yes';
                    } else if (displayText === 'No') {
                        displayText = '✗ No';
                    }
                    btn.textContent = displayText;
                    btn.onclick = () => {
                        optionsDiv.querySelectorAll('.option-btn').forEach(b => b.classList.remove('selected'));
                        btn.classList.add('selected');
                        sendMessage(option);
                    };
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
            if (enabled) messageInput.focus();
        }
        
        function restartChat() { 
            fetch('/restart_chat', {method: 'POST'}).then(() => window.location.reload()); 
        }
        
        messageInput.addEventListener('keypress', function(e) { if (e.key === 'Enter') sendMessage(); });
        messageInput.focus();
    </script>
</body>
</html>
""", messages=session["messages"], 
         waiting_for_answer=session["waiting_for_answer"],
         completed=session["completed"],
         phase=session.get("phase", 1),
         sidebar_open=session.get("sidebar_open", True),
         answers_list=answers_list)

@app.route("/send_message", methods=["POST"])
@safe_route
def send_message():
    if session.get("completed"):
        return jsonify({"status": "completed"})
    
    if not session.get("waiting_for_answer"):
        return jsonify({"status": "error", "message": "Not waiting for answer"})
    
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Invalid request"})
    
    answer = data.get("answer", "").strip()
    if not answer:
        return jsonify({"status": "error", "message": "Please provide an answer"})
    
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
        # Only add to history if not already there (not editing)
        if current_ref not in session["history"]:
            session["history"].append(current_ref)
        session["waiting_for_answer"] = False
        process_next_question()
        return jsonify({"status": "success", "messages": session["messages"][-1:]})
    
    result = process_handler_next(current_ref, answer)
    
    # Save answer - if editing, overwrite existing
    session["answers"][current_ref] = answer
    # Only add to history if not already there (not editing)
    if current_ref not in session["history"]:
        session["history"].append(current_ref)
    session["waiting_for_answer"] = False
    
    run_xhr_params(question, answer, current_ref)
    
    # =========================================================
    # STEP 3: UPDATE REFUND ESTIMATION IN REAL-TIME
    # =========================================================
    estimation_id = session.get("refund_estimation_id")
    if estimation_id and session.get("estimation_initiated"):
        try:
            # Prepare answer data for the API
            question_obj = get_question(current_ref)
            answer_data = {
                "answers": session.get("answers", {}),
                "last_answered": current_ref,
                "current_phase": session.get("phase", 1),
                "progress": {
                    "answered": len(session.get("history", [])),
                    "total": 15  # Total number of questions
                },
                "timestamp": datetime.now().isoformat()
            }
            
            # Include the specific answer
            if question_obj:
                title = question_obj.get("title", current_ref)
                if callable(title):
                    title = title(session.get("answers", {}))
                answer_data["last_answer"] = {
                    "question": title,
                    "answer": session["answers"][current_ref],
                    "ref": current_ref
                }
            
            # Update the estimation in real-time
            update_refund_estimation(estimation_id, answer_data)
        except Exception as e:
            logger.error(f"Error updating estimation in real-time: {e}")
    
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
    
    return jsonify({"status": "success", "messages": session["messages"][-1:]})

# =========================================================
# SAVY API ROUTES
# =========================================================

@app.route("/api/savy/estimate", methods=["POST"])
@safe_route
def savy_estimate():
    """Send estimation data to Savy API"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        logger.info(f"📊 Sending estimation data to Savy")
        
        result = make_savy_request("api/estimations", "POST", data)
        
        if result and not result.get("error"):
            return jsonify({"success": True, "data": result})
        else:
            return jsonify({"success": False, "error": result}), 400
            
    except Exception as e:
        logger.error(f"Error in savy_estimate: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/savy/user", methods=["GET"])
@safe_route
def savy_get_user():
    """Get user info from Savy API"""
    try:
        result = make_savy_request("api/users/me", "GET")
        
        if result and not result.get("error"):
            return jsonify({"success": True, "data": result})
        else:
            return jsonify({"success": False, "error": result}), 401
            
    except Exception as e:
        logger.error(f"Error in savy_get_user: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/savy/validate", methods=["GET"])
@safe_route
def savy_validate_token():
    """Validate the Savy token"""
    try:
        result = make_savy_request("api/users/me", "GET")
        
        if result and not result.get("error"):
            return jsonify({"valid": True, "user": result})
        else:
            return jsonify({"valid": False, "error": result})
            
    except Exception as e:
        logger.error(f"Error validating token: {e}")
        return jsonify({"valid": False, "error": str(e)})

# =========================================================
# STEP 2: INITIATE REFUND ESTIMATION ROUTE
# =========================================================

@app.route("/api/savy/initiate-refund", methods=["POST"])
@safe_route
def initiate_refund():
    """
    Initiate a refund estimation with empty body
    POST /api/v1/refund-estimations
    """
    try:
        logger.info("🔄 Initiating refund estimation via API route...")
        
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

# =========================================================
# STEP 3: UPDATE ESTIMATION ROUTE
# =========================================================

@app.route("/api/savy/update-estimation", methods=["POST"])
@safe_route
def update_estimation():
    """Update the refund estimation with current answers"""
    try:
        data = request.get_json() or {}
        estimation_id = data.get("estimation_id") or session.get("refund_estimation_id")
        
        if not estimation_id:
            return jsonify({"error": "No estimation ID provided"}), 400
        
        # Prepare answer data
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
        
        # Include the last answer if available
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
        logger.error(f"Error in update_estimation: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/restart_chat", methods=["POST"])
@safe_route
def restart_chat():
    session.clear()
    init_session()
    return jsonify({"status": "success"})

if __name__ == "__main__":
    app.run(debug=True, threaded=True)

