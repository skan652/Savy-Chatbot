import requests
import json

# Restart
requests.post('http://127.0.0.1:5000/restart')

# Answer: Full-time
requests.post('http://127.0.0.1:5000/answer', json={'answer': 'Full-time'})

# Answer: UK resident (True)
requests.post('http://127.0.0.1:5000/answer', json={'answer': True})

# Get monthly_salary question
r = requests.get('http://127.0.0.1:5000/get_question')
print("Current:", r.json()['key'])

# Answer salary
requests.post('http://127.0.0.1:5000/answer', json={'answer': 2000})

# Answer: other_income_sources = True
requests.post('http://127.0.0.1:5000/answer', json={'answer': True})

# Get next question
r = requests.get('http://127.0.0.1:5000/get_question')
print("Next question:", r.json()['key'])
print(json.dumps(r.json(), indent=2))
