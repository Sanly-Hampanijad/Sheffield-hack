import requests
import os
env = os.getenv("API_KEY")
print(env)
response = requests.get("https://api.weatherapi.com/v1/current.json?key="+ env + "&q=London&aqi=no")

print(response.json())