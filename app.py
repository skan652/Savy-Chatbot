from flask import Flask, request, redirect, url_for, jsonify, session
from flask import render_template_string
import json
import re
import logging
from datetime import datetime
from functools import wraps
import inspect
import os

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

ai_client = AIClient()

app = Flask(__name__)
app.secret_key = "savy-chatbot-secret-key"
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 3600

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VALID_PASSKEYS = ["12345", "pass123"]

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

# Phase configuration
PHASE_1_QUESTIONS = ["1", "2", "3", "4", "5", "6", "7", "8"]
PHASE_2_QUESTIONS = ["9", "10", "11", "12", "13", "14", "15"]

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
            "sidebar_open": True
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
    """Process handlerNext with priority for dynamiqyeHandlerNext"""
    try:
        question = get_question(current_ref)
        if not question:
            return get_next_question_in_phase(current_ref)
        
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
                    if get_question(next_ref) or next_ref in PHASE_1_QUESTIONS + PHASE_2_QUESTIONS:
                        return {"status": "success", "next_ref": next_ref, "completed": False}
                    return get_next_question_in_phase(current_ref)
                
                elif action in ["to_save_and_finish", "to_save_and_finish_with_error"]:
                    return {"status": "completed"}
        
        return get_next_question_in_phase(current_ref)
            
    except Exception as e:
        logger.error(f"Error in process_handler_next: {e}")
        return get_next_question_in_phase(current_ref)

def get_next_question_in_phase(current_ref):
    """Safely get next question in current phase"""
    try:
        if session.get("phase") == 1:
            if current_ref in PHASE_1_QUESTIONS:
                current_index = PHASE_1_QUESTIONS.index(current_ref)
                if current_index + 1 < len(PHASE_1_QUESTIONS):
                    next_ref = PHASE_1_QUESTIONS[current_index + 1]
                    return {"status": "success", "next_ref": next_ref, "completed": False}
                else:
                    return {"status": "phase_complete"}
            else:
                for ref in PHASE_1_QUESTIONS:
                    if ref not in session.get("history", []):
                        return {"status": "success", "next_ref": ref, "completed": False}
                return {"status": "phase_complete"}
        else:
            if current_ref in PHASE_2_QUESTIONS:
                current_index = PHASE_2_QUESTIONS.index(current_ref)
                if current_index + 1 < len(PHASE_2_QUESTIONS):
                    next_ref = PHASE_2_QUESTIONS[current_index + 1]
                    return {"status": "success", "next_ref": next_ref, "completed": False}
                else:
                    return {"status": "completed"}
            else:
                return {"status": "success", "next_ref": PHASE_2_QUESTIONS[0], "completed": False}
                
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
            transition_msg = "✅ **Thank you for completing the tax refunds section!**\n\n"
            transition_msg += "Now let's move to the next step: **Tax Savings Assessment**.\n"
            transition_msg += "Please answer the following questions about your travel and expenses.\n"
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

def complete_assessment():
    """Complete assessment and show results"""
    try:
        session["completed"] = True
        session["waiting_for_answer"] = False
        
        answers = session.get("answers", {})
        
        # Build plain text summary for AI and display
        plain_summary = "Assessment Summary:\n\n"
        for ref, answer in answers.items():
            question = get_question(ref)
            if question:
                title = question.get("title", ref)
                if callable(title):
                    title = title(answers)
                plain_summary += f"{title}\n→ {answer}\n\n"
        
        # Try to get AI summary
        use_ai = os.environ.get("USE_AI", "").lower() in ["1", "true", "yes"]
        provider = os.environ.get("AI_PROVIDER", "gemini").lower()
        
        chatgpt_creds = ai_client.chatgpt_key or ai_client.openai_key
        google_creds = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_API_TOKEN")
        
        provider_enabled = (provider in ["openai", "chatgpt"] and chatgpt_creds) or \
                           (provider in ["gemini", "google"] and google_creds)
        
        ai_summary = ""
        if use_ai and provider_enabled:
            try:
                logger.info(f"Generating AI summary with provider: {provider}")
                system_prompt = "You are a tax assessment assistant. Provide a concise, professional summary of the taxpayer's assessment in 2-3 sentences."
                ai_summary = ai_client.generate(
                    prompt=plain_summary,
                    system_prompt=system_prompt,
                    max_tokens=500,
                    temperature=0.7
                )
                if ai_summary:
                    logger.info("AI summary generated successfully")
            except Exception as e:
                logger.error(f"AI summary failed: {e}")
        
        # Build final message
        final_message = "🎉 **Assessment Complete!** 🎉\n\n"
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
            final_message += "🤖 **AI Assessment:**\n\n"
            final_message += ai_summary + "\n\n"
        
        final_message += "=" * 50 + "\n\n"
        final_message += "📞 **Next Steps:**\n\n"
        final_message += "A tax specialist will review your information and contact you soon.\n\n"
        final_message += "Thank you for using the Tax Assistant Bot! 🙏\n\n"
        final_message += "Click 'Start New Assessment' below to begin again."
        
        add_message("assistant", final_message)
        session.modified = True
        
    except Exception as e:
        logger.error(f"Error in complete_assessment: {e}")
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
        h1 { color: #333; margin-bottom: 10px; }
        .subtitle { color: #666; margin-bottom: 30px; }
        .error { background: #fee; padding: 12px; border-radius: 12px; color: #c33; margin-bottom: 20px; }
        input { width: 100%; padding: 14px; border: 2px solid #e0e0e0; border-radius: 12px; font-size: 1em; margin-bottom: 20px; }
        input:focus { outline: none; border-color: #667eea; }
        button { width: 100%; padding: 14px; background: linear-gradient(45deg, #667eea, #764ba2); color: white; border: none; border-radius: 12px; font-size: 1.1em; cursor: pointer; }
        button:hover { transform: translateY(-2px); }
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
    
    if ref and ref in session.get("history", []):
        # Remove this answer and all subsequent answers
        history = session["history"]
        if ref in history:
            ref_index = history.index(ref)
            # Remove answers from this point forward
            answers_to_remove = history[ref_index:]
            for removed_ref in answers_to_remove:
                if removed_ref in session["answers"]:
                    del session["answers"][removed_ref]
            
            # Update history
            session["history"] = history[:ref_index]
            
            # Set current question to the edited one
            session["current_ref"] = ref
            session["waiting_for_answer"] = False
            
            # Clear messages from this point forward
            # Find the message index for this question
            msg_index = -1
            for i, msg in enumerate(session["messages"]):
                if msg.get("role") == "assistant" and ref in msg.get("content", ""):
                    msg_index = i
                    break
            
            if msg_index >= 0:
                session["messages"] = session["messages"][:msg_index]
            
            session.modified = True
            
            # Process next question (the edited one)
            process_next_question()
            
            return jsonify({"status": "success", "current_ref": ref})
    
    return jsonify({"status": "error", "message": "Could not edit answer"})

@app.route("/chat")
@safe_route
def chat():
    if not session.get("passkey_verified"):
        return redirect(url_for("passkey_page"))
    
    if not session["messages"] and not session["completed"]:
        welcome_msg = "🌅 **Good morning!**\n\n"
        welcome_msg += "Please answer a few questions to determine how eligible you are for a tax refund and tax savings.\n\n"
        welcome_msg += "Let's start with the **Tax Refunds Assessment**."
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
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
            height: 100vh; 
            overflow: hidden;
        }
        
        /* Main layout with sidebar */
        .app-container {
            display: flex;
            height: 100vh;
            width: 100%;
        }
        
        /* Sidebar styles */
        .sidebar {
            width: 280px;
            background: white;
            border-right: 1px solid #e0e0e0;
            display: flex;
            flex-direction: column;
            transition: transform 0.3s ease;
            box-shadow: 2px 0 8px rgba(0,0,0,0.05);
            z-index: 10;
        }
        
        .sidebar.closed {
            transform: translateX(-280px);
            position: absolute;
        }
        
        .sidebar-header {
            padding: 20px;
            border-bottom: 1px solid #e0e0e0;
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
        }
        
        .sidebar-header h3 {
            font-size: 1.1em;
            font-weight: 500;
            margin-bottom: 5px;
        }
        
        .sidebar-header p {
            font-size: 0.8em;
            opacity: 0.9;
        }
        
        .answers-list {
            flex: 1;
            overflow-y: auto;
            padding: 15px;
        }
        
        .answer-item {
            background: #f7f7f8;
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 12px;
            cursor: pointer;
            transition: all 0.2s;
            border: 1px solid #e0e0e0;
        }
        
        .answer-item:hover {
            background: #e8e8ea;
            transform: translateX(-2px);
            border-color: #667eea;
        }
        
        .answer-question {
            font-size: 0.85em;
            font-weight: 500;
            color: #333;
            margin-bottom: 6px;
        }
        
        .answer-value {
            font-size: 0.9em;
            color: #667eea;
            font-weight: 500;
        }
        
        .edit-icon {
            float: right;
            color: #999;
            font-size: 0.8em;
            cursor: pointer;
        }
        
        .edit-icon:hover {
            color: #667eea;
        }
        
        .no-answers {
            text-align: center;
            color: #999;
            padding: 20px;
            font-size: 0.9em;
        }
        
        /* Chat container styles */
        .chat-container {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: #f7f7f8;
            position: relative;
        }
        
        .toggle-sidebar-btn {
            position: absolute;
            left: 20px;
            top: 20px;
            background: white;
            border: none;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            cursor: pointer;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            z-index: 20;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2em;
            transition: all 0.2s;
        }
        
        .toggle-sidebar-btn:hover {
            transform: scale(1.05);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        
        .chat-header {
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            padding: 20px;
            text-align: center;
            margin-left: 60px;
        }
        
        .chat-header h1 { font-size: 1.5em; font-weight: 500; }
        .chat-header p { font-size: 0.85em; opacity: 0.9; margin-top: 5px; }
        
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
        
        .message { margin-bottom: 20px; display: flex; animation: fadeIn 0.3s ease-in; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .message.user { justify-content: flex-end; }
        .message-content { max-width: 70%; padding: 12px 16px; border-radius: 18px; line-height: 1.5; white-space: pre-wrap; word-wrap: break-word; }
        .message.user .message-content { background: linear-gradient(45deg, #667eea, #764ba2); color: white; border-bottom-right-radius: 4px; }
        .message.assistant .message-content { background: white; color: #333; border-bottom-left-radius: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }
        .options-container { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 10px; }
        .option-btn { background: #f0f0f0; border: 1px solid #ddd; padding: 8px 16px; border-radius: 20px; cursor: pointer; transition: all 0.2s; font-size: 0.9em; color: #333; }
        .option-btn:hover { background: #667eea; border-color: #667eea; color: white; transform: translateY(-1px); }
        .input-container { background: white; border-top: 1px solid #e0e0e0; padding: 20px; display: flex; gap: 10px; }
        .input-container input { flex: 1; padding: 12px; border: 1px solid #e0e0e0; border-radius: 24px; font-size: 1em; outline: none; }
        .input-container input:focus { border-color: #667eea; }
        .input-container button { background: linear-gradient(45deg, #667eea, #764ba2); color: white; border: none; padding: 12px 24px; border-radius: 24px; cursor: pointer; font-size: 1em; }
        .input-container button:hover { transform: translateY(-1px); }
        .input-container button:disabled { opacity: 0.5; cursor: not-allowed; }
        .restart-btn { background: #f0f0f0; color: #666; margin-top: 10px; }
        
        @media (max-width: 768px) { 
            .message-content { max-width: 85%; } 
            .input-container { padding: 15px; }
            .sidebar { width: 260px; }
        }
    </style>
</head>
<body>
    <div class="app-container">
        <!-- Sidebar -->
        <div class="sidebar {% if not sidebar_open %}closed{% endif %}" id="sidebar">
            <div class="sidebar-header">
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
        
        <!-- Chat Container -->
        <div class="chat-container">
            <button class="toggle-sidebar-btn" onclick="toggleSidebar()">
                {% if sidebar_open %}◀{% else %}▶{% endif %}
            </button>
            
            <div class="chat-header">
                <h1>💬 Tax Assistant Bot</h1>
                <p>Your personal tax eligibility advisor</p>
                <div class="phase-indicator">
                    {% if not completed %}
                        {% if phase == 1 %}📋 Phase 1/2: Tax Refunds Assessment
                        {% else %}💰 Phase 2/2: Tax Savings Assessment{% endif %}
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
    </div>
    
    <script>
        const messagesContainer = document.getElementById('messages-container');
        const messageInput = document.getElementById('message-input');
        const sendBtn = document.getElementById('send-btn');
        let sidebarOpen = {{ 'true' if sidebar_open else 'false' }};
        
        function scrollToBottom() { 
            messagesContainer.scrollTop = messagesContainer.scrollHeight; 
        }
        scrollToBottom();
        
        function toggleSidebar() {
            fetch('/toggle_sidebar', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    const sidebar = document.getElementById('sidebar');
                    const toggleBtn = document.querySelector('.toggle-sidebar-btn');
                    if (data.sidebar_open) {
                        sidebar.classList.remove('closed');
                        toggleBtn.innerHTML = '◀';
                    } else {
                        sidebar.classList.add('closed');
                        toggleBtn.innerHTML = '▶';
                    }
                    sidebarOpen = data.sidebar_open;
                });
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
        
        function sendMessage(predefinedAnswer = null) {
            let answer = predefinedAnswer || messageInput.value.trim();
            if (!answer && !predefinedAnswer) return;
            
            addMessageToUI('user', answer);
            if (!predefinedAnswer) messageInput.value = '';
            setInputEnabled(false);
            
            fetch('/send_message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({answer: answer})
            })
            .then(response => response.json())
            .then(data => {
                setInputEnabled(true);
                if (data.status === 'completed' || data.status === 'phase_complete') {
                    window.location.reload();
                } else if (data.messages) {
                    data.messages.forEach(msg => addMessageToUI(msg.role, msg.content, msg.options));
                    scrollToBottom();
                    // Refresh page to update sidebar
                    setTimeout(() => window.location.reload(), 500);
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
                    btn.textContent = option.replace(/\\n/g, ' ');
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
                    return jsonify({"status": "completed"})
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
                    return jsonify({"status": "completed"})
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
        session["history"].append(current_ref)
        session["waiting_for_answer"] = False
        process_next_question()
        return jsonify({"status": "success", "messages": session["messages"][-1:]})
    
    result = process_handler_next(current_ref, answer)
    
    session["answers"][current_ref] = answer
    session["history"].append(current_ref)
    session["waiting_for_answer"] = False
    
    run_xhr_params(question, answer, current_ref)
    
    if result.get("status") == "completed":
        complete_assessment()
        return jsonify({"status": "completed"})
    
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
        return jsonify({"status": "completed"})
    
    return jsonify({"status": "success", "messages": session["messages"][-1:]})

@app.route("/restart_chat", methods=["POST"])
@safe_route
def restart_chat():
    session.clear()
    init_session()
    return jsonify({"status": "success"})

if __name__ == "__main__":
    app.run(debug=True, threaded=True)