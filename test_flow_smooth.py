#!/usr/bin/env python3
"""
Test script to verify the questionnaire flow progresses smoothly through questions
in the correct order.
"""

from state_machine import StateMachineEngine
import json

# Load engine
engine = StateMachineEngine('response.json')

# Print question order
print("=" * 60)
print("QUESTION ORDER")
print("=" * 60)
print(f"Question order: {engine.question_order}")
print(f"Total questions: {len(engine.question_order)}")
print()

# Test the flow by simulating answers
print("=" * 60)
print("TESTING FLOW WITH SAMPLE ANSWERS")
print("=" * 60)

current_ref = None
answers_provided = {}

# Simulate answering questions with default answers
test_answers = {
    "1": "Between £14k & £50k",      # Answer for income question
    "2": "Yes",                       # Answer for travel for work
    "3": "Company vehicle",           # Answer for how do you make journeys
    "4": "8000",                      # Miles per year
    "5": "Mileage rate",             # Mileage payment type
    "6": "I travel to multiple places as part of my job",  # Type of work journeys
    "8": "Yes",                       # Do you buy food and drink
    "9": "3",                         # Days per week
    "10": "122",                      # Spend per day
    "11": "Yes, I pay for it but can claim all of it back from my employer",  # Employer covers
    "12": "5",                        # Reimbursed per day
    "13": "Yes",                      # Earned more than 14k in last 4 years
    "22": "Yes",                      # Earned more than 14k in last 4 years
}

# Start with first question
current_ref = engine.get_first_question()["ref"]
step = 1

while True:
    question = engine.get_question(current_ref)
    
    if not question:
        print(f"\nStep {step}: ERROR - Question {current_ref} not found!")
        break
    
    print(f"\nStep {step}: Question {current_ref} - {question['title'][:50]}")
    
    # Get answer for this question
    answer = test_answers.get(current_ref, "")
    
    if not answer:
        print(f"  → No test answer for this question, using default fallback")
        # Use first option if available
        if question.get("options"):
            answer = question["options"][0]
        else:
            print("  → ERROR: No options and no default answer!")
            break
    
    print(f"  → Answer: {answer[:50]}")
    
    # Get next question
    result = engine.get_next_question_ref(current_ref, answer)
    
    if result.get("status") == "error":
        print(f"  → ERROR: {result.get('message')}")
        break
    
    if result.get("status") == "completed":
        print(f"  → Flow completed!")
        break
    
    next_ref = result.get("next_ref")
    print(f"  → Next: {next_ref}")
    
    current_ref = next_ref
    step += 1
    
    if step > 20:  # Safety limit
        print("\nERROR: Too many steps, possible infinite loop!")
        break

print("\n" + "=" * 60)
print("FLOW TEST COMPLETE")
print("=" * 60)
