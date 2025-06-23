import requests
import json

def send_to_google_chat(message):
    webhook_url = "https://chat.googleapis.com/v1/spaces/4ZsvACAAAAE/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=QAsMtcgO05jwCeg2HXcDrCK7ngmtq0vpQwguobG8-vU"  # Replace with your actual webhook
    headers = {'Content-Type': 'application/json'}
    data = {'text': message}

    response = requests.post(webhook_url, headers=headers, data=json.dumps(data))
    print(f"Status Code: {response.status_code}")
    print(f"Response Text: {response.text}")
    return response
