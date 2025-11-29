import requests
import os
from dotenv import load_dotenv
import time

load_dotenv()
weatherAPI = os.getenv("API_KEY")
if not weatherAPI:
    raise ValueError("API_KEY not found in environment variables")

TEMP = Gauge("temperature", "Temperature in Celsius", ["city"])
CLOUD = Gauge("cloud_cover", "Cloud cover percentage", ["city"])
#LAT = Gauge("lat", "City Latitude", ["city"])
#LONG = Gauge("lon", "City Longitude", ["city"])

def get_weather(city):
    url = f"https://api.weatherapi.com/v1/current.json?key={weatherAPI}&q={city}&aqi=no"
    data = requests.get(url).json()
    temp = data["current"]["temp_c"]
    cloud = data["current"]["cloud"]
    return temp, cloud

def update_metrics(city):
    temp, cloud = get_weather(city)
    TEMP.labels(city=city).set(temp)
    CLOUD.labels(city=city).set(cloud)

def can_call_city(city):
    url = f"https://api.weatherapi.com/v1/current.json?key={weatherAPI}&q={city}&aqi=no"
    data = requests.get(url)
    return data.status_code

if __name__ == "__main__":
    # Start Prometheus metrics server
    with open("uk_cities.txt", "r") as file:   
        cities_array = list(map(lambda x: x.rstrip("\n"), file.readlines()))
        
            
        