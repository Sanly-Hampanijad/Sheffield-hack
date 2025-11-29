import requests
import os

from dotenv import load_dotenv

load_dotenv()

env = os.getenv("API_KEY")
if not env:
    raise ValueError("API_KEY not found in environment variables")

def get_weather(city):
    url = f"https://api.weatherapi.com/v1/current.json?key={env}&q={city}&aqi=no"
    data = requests.get(url).json()
    return data["current"]["temp_c"], data["current"]["cloud"]
    
def get_sunnyness(city):
    url = f"https://api.weatherapi.com/v1/current.json?key={env}&q={city}&aqi=no"
    data = requests.get(url).json()
    return data

print(get_sunnyness("Leeds"))