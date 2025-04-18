import requests
import json

# File path to the JSON file
json_file_path = "data.json"

# Server URL (replace with your XAMPP server's IP and script location)
url = "http://<YOUR_XAMPP_SERVER_IP>/receiver.php"

# Load the JSON data
with open(json_file_path, 'r') as file:
    json_data = json.load(file)

# Send the JSON data as a POST request
response = requests.post(url, json=json_data)

# Print the server's response
print(f"Server response: {response.text}")