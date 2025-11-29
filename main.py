import requests
import os

from dotenv import load_dotenv

load_dotenv()

env = os.getenv("API_KEY")
if not env:
    raise ValueError("API_KEY not found in environment variables")


response = requests.get("https://api.weatherapi.com/v1/current.json?key="+ env + "&q=London&aqi=no")

print(response.json())