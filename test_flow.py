import requests
import json

session = requests.Session()
base = 'http://127.0.0.1:5000'

# Restart session
r = session.post(f"{base}/restart_chat")
print('Restart:', r.status_code, r.text)

# Send an answer
r = session.post(f"{base}/send_message", json={'answer': 'Full-time'})
print('Send Full-time:', r.status_code, r.text)

# Send boolean answer
r = session.post(f"{base}/send_message", json={'answer': True})
print('Send True:', r.status_code, r.text)

# Send numeric salary
r = session.post(f"{base}/send_message", json={'answer': 2000})
print('Send Salary:', r.status_code, r.text)

# Finalize with another boolean
r = session.post(f"{base}/send_message", json={'answer': True})
print('Send True 2:', r.status_code, r.text)
