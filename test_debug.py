from state_machine import StateMachineEngine

engine = StateMachineEngine("response.json")

# Test getting first question
first = engine.get_first_question()
print(f"First question: {first}")
print(f"First ref: {first['ref']}")

# Test getting a question by ref
q = engine.get_question("1")
print(f"Question 1: {q}")

# Test getting next question
result = engine.get_next_question_ref("1", "Under\n£14k")
print(f"Next result: {result}")

# Test with invalid ref
try:
    invalid = engine.get_question("999")
    print(f"Invalid question: {invalid}")
except Exception as e:
    print(f"Error: {e}")

# Test with invalid answer
result2 = engine.get_next_question_ref("1", "Invalid Answer")
print(f"Invalid answer result: {result2}")