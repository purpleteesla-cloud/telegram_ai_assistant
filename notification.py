# test_notification.py
import requests

response = requests.post("http://localhost:8000/test_notification")
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")