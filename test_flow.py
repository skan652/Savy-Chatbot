import requests
import json

session = requests.Session()

# Restart
r = session.post('http://127.0.0.1:5000/restart')
print('Restart:', r.status_code, r.headers.get('Location'))

# Answer: Full-time
r = session.post('http://127.0.0.1:5000/answer', json={'answer': 'Full-time'})
print('Full-time:', r.status_code, r.text)

# Answer: UK resident (True)
r = session.post('http://127.0.0.1:5000/answer', json={'answer': True})
print('UK resident:', r.status_code, r.text)

# Get monthly_salary question
r = session.get('http://127.0.0.1:5000/get_question')
print('Current:', r.json().get('current_ref'))
print(json.dumps(r.json(), indent=2))

# Answer salary
r = session.post('http://127.0.0.1:5000/answer', json={'answer': 2000})
print('Salary:', r.status_code, r.text)

# Answer: other_income_sources = True
r = session.post('http://127.0.0.1:5000/answer', json={'answer': True})
print('Other income source:', r.status_code, r.text)

# Get next question
r = session.get('http://127.0.0.1:5000/get_question')
print('Next question:', r.json().get('current_ref'))
print(json.dumps(r.json(), indent=2))
