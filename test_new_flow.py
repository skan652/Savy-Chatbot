from state_machine import StateMachineEngine

engine = StateMachineEngine("response.json")

print("=" * 60)
print("TESTING NEW FLOW DIAGRAM")
print("=" * 60)

# Path 1: Under £14k - Should end immediately
print("\n--- Path 1: Under £14k (Not Eligible) ---")
q1 = engine.get_first_question()
print(f"Q1: {q1['title']}")
result = engine.get_next_question_ref("1", "Under\n£14k")
print(f"Result: {result}")

# Path 2: £14-50k, No travel - Should end
print("\n--- Path 2: £14-50k, No Travel for Work (End) ---")
q2_result = engine.get_next_question_ref("1", "Between\n£14k & £50k")
print(f"Q1 → {q2_result}")
q2 = engine.get_question("2")
print(f"Q2: {q2['title']}")
result = engine.get_next_question_ref("2", "No")
print(f"Result: {result}")

# Path 3: £14-50k, Yes travel, My vehicle
print("\n--- Path 3: My Vehicle (Full Flow) ---")
result = engine.get_next_question_ref("1", "Between\n£14k & £50k")
print(f"Q1 → Q{result['next_ref']}")

result = engine.get_next_question_ref("2", "Yes")
print(f"Q2 → Q{result['next_ref']}")

result = engine.get_next_question_ref("3", "My\nvehicle")
print(f"Q3 → Q{result['next_ref']}")

# Q4 - Mileage
result = engine.get_next_question_ref("4", "5000")
print(f"Q4 (5000 miles) → Q{result['next_ref']}")

# Q5 - Mileage type: Mileage rate
result = engine.get_next_question_ref("5", "Mileage rate")
print(f"Q5 (Mileage rate) → Q{result['next_ref']}")

# Q8 - Food and drink: Yes
result = engine.get_next_question_ref("8", "Yes")
print(f"Q8 (Yes) → Q{result['next_ref']}")

# Q9 - Days per week
result = engine.get_next_question_ref("9", "3")
print(f"Q9 (3 days) → Q{result['next_ref']}")

# Q10 - Spend per day
result = engine.get_next_question_ref("10", "£10")
print(f"Q10 (£10) → Q{result['next_ref']}")

# Q11 - Employer payment for food
result = engine.get_next_question_ref("11", "No, I pay for it and don't get anything back from my employer")
print(f"Q11 → Q{result['next_ref']}")

# Q12 - Amount employer pays
result = engine.get_next_question_ref("12", "£0")
print(f"Q12 (£0) → Q{result['next_ref']}")

# Q13 - Earned more than £14k in last 4 years
result = engine.get_next_question_ref("13", "Yes")
print(f"Q13 (Yes) → {result}")

print("\n--- Path 4: Company Vehicle ---")
result = engine.get_next_question_ref("3", "Company\nvehicle")
print(f"Q3 (Company vehicle) → Q{result['next_ref']}")

print("\n--- Path 5: Train ---")
result = engine.get_next_question_ref("3", "Train")
print(f"Q3 (Train) → Q{result['next_ref']}")

# Q6 - Type of work journeys
result = engine.get_next_question_ref("6", "I travel to multiple places as part of my job")
print(f"Q6 (Multiple places) → Q{result['next_ref']}")

result = engine.get_next_question_ref("6", "I travel to the same place of work each time")
print(f"Q6 (Same place) → Q{result['next_ref']}")

# Q7 - Temporary workplace
result = engine.get_next_question_ref("7", "Yes")
print(f"Q7 (Yes) → Q{result['next_ref']}")

result = engine.get_next_question_ref("7", "No")
print(f"Q7 (No) → {result}")

print("\n" + "=" * 60)
print("FLOW TEST COMPLETE")
print("=" * 60)
