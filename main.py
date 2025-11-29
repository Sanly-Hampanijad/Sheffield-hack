import requests
import os
from prometheus_client import Gauge, start_http_server
from dotenv import load_dotenv
from datetime import datetime, timedelta
import time

load_dotenv()

env = os.getenv("API_KEY")
if not env:
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

if __name__ == "__main__":
    # Start Prometheus metrics server
    start_http_server(8000)
    city = "Harrogate"

    while True:
        update_metrics(city)
        time.sleep(15)