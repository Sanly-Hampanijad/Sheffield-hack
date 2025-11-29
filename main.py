import requests
import os
from prometheus_client import start_http_server, Gauge
from dotenv import load_dotenv
import time
from datetime import datetime, timedelta


load_dotenv()
weatherAPI = os.getenv("API_KEY")
if not weatherAPI:
    raise ValueError("API_KEY not found in environment variables")

# Prometheus metrics (labels: city)
G_TEMP = Gauge("temperature_c", "Temperature (C)", ["city"])
G_CLOUD = Gauge("cloud_overall_pct", "Overall cloud % (from WeatherAPI)", ["city"])
G_CLOUD_LOW = Gauge("cloud_low_pct", "Low cloud %", ["city"])
G_CLOUD_MID = Gauge("cloud_mid_pct", "Mid cloud %", ["city"])
G_CLOUD_HIGH = Gauge("cloud_high_pct", "High cloud %", ["city"])
G_PRECIP_PROB = Gauge("precipitation_probability_pct", "Precipitation probability (%)", ["city"])
G_AOD = Gauge("aerosol_optical_depth", "Aerosol optical depth", ["city"])
G_PM25 = Gauge("pm2_5_ugm3", "PM2.5 (µg/m3)", ["city"])
G_VIS = Gauge("visibility_km", "Visibility (km)", ["city"])
G_HUM = Gauge("relative_humidity_pct", "Relative humidity (%)", ["city"])

# Derived and final metrics
G_MINUTES_FROM_SUNSET = Gauge("minutes_from_sunset", "Minutes from sunset (localtime -> sunset)", ["city"])
G_SUNSET_WINDOW = Gauge("sunset_window_flag", "1 if within sunset window (±45m)", ["city"])
G_SUNSET_PROB = Gauge("sunset_probability", "Heuristic probability of good sunset (0-1)", ["city"])

# Configurable weights (tweakable)
WEIGHTS = {
    "cloud": 0.45,
    "precip": 0.20,
    "air": 0.20,
    "time": 0.15
}

# Helper clamp ??
def clamp01(x):
    return max(0.0, min(1.0, x))

# Weather API call
def get_weather(city):
    """
    Return dict with: lat, lon, temp_c, cloud_overall, visibility_km, humidity_pct, localtime (ISO 'YYYY-MM-DD HH:MM')
    """
    url = f"https://api.weatherapi.com/v1/current.json?key={weatherAPI}&q={city}&aqi=no"
    data = requests.get(url).json()
    loc = data.get("location", {})
    cur = data.get("current", {})

    return {
        "lat": float(loc.get("lat")),
        "lon": float(loc.get("lon")),
        "temp_c": cur.get("temp_c"),
        "cloud_overall": cur.get("cloud"),
        "visibility_km": cur.get("vis_km"),
        "humidity_pct": cur.get("humidity"),
        "localtime": loc.get("localtime") # YYYY-MM-DD HH:MM
    }

# Open Meteo API call
def get_openmeteo_forecast(lat, lon, timezone="Europe/London"):
    """
    return hourly arrays of: sunset_times (ISO), cloud_low_pct, cloud_mid_pct, cloud_high_pct, precipitation_mm, aod, pm2_5
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "cloudcover_low,cloudcover_mid,cloudcover_high,precipitation_probability",
        "daily": "sunrise,sunset",
        "timezone": timezone
    }
    url = "https://api.open-meteo.com/v1/forecast"
    r = requests.get(url, params=params, timeout=10)

    print("Open-Meteo forecast request ->", r.url, "status:", r.status_code)
    try:
        r.raise_for_status()
    except Exception as e:
        print("Open-Meteo forecast HTTP error:", e)
        print("Response text:", r.text[:1000])
        raise
    data = r.json()

    if "hourly" in data:
        h = data["hourly"]
        print("hourly.time len:", len(h.get("time", [])))
    if "daily" in data:
        d = data["daily"]
        print("daily.sunset len:", len(d.get("sunset", [])))

    return data

def get_openmeteo_air_quality(lat, lon, timezone="Europe/London"):
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pm2_5,aerosol_optical_depth",
        "timezone": timezone
    }
    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    r = requests.get(url, params=params, timeout=10)

    try:
        r.raise_for_status()
    except Exception as e:
        print("Response text:", r.text[:1000])
        raise
    data = r.json()

    if "hourly" in data:
        print("aq hourly.time len:", len(data["hourly"].get("time", [])))
    return data


# 1. Extract the “current-hour index” from the hourly forecast - which hour corresponds to the current localtime
# 2. Populate the guages to Prometheus
# 3. compute sunset distance ?
# 4. compute score (the math one)


# Scoring Functions
## cloud layer score
## precip score
## air score

def compute(city):
    # Get weather data from weather api and open meteo
    # call funct to formulate final score
    # print or return final score
    #
    raw = collect_raw_data(city)

    print("\n === Raw Data ===")
    for k, v in raw.items():
        print(f"{k}: {v}")

    return raw

def collect_raw_data(city):
    """ calls weatherapi, openmeteo and openmeteo air quality,
    returns a single merged dict containing all raw fields
    """
    weather = get_weather(city)

    lat = weather["lat"]
    lon = weather["lon"]

    openmeteo = get_openmeteo_forecast(lat, lon)
    airquality = get_openmeteo_air_quality(lat, lon)

    raw = {
        "city": city,

        # WeatherAPI data
        "lat": lat,
        "lon": lon,
        "localtime": weather["localtime"],
        "temp_c": weather["temp_c"],
        "cloud_overall": weather["cloud_overall"],
        "visibility_km": weather["visibility_km"],
        "humidity_pct": weather["humidity_pct"],

        # OpenMeteo data
        "forecast": {
            "hourly_time": openmeteo.get("hourly", {}).get("time", []),
            "cloudcover_low": openmeteo.get("hourly", {}).get("cloudcover_low", []),
            "cloudcover_mid": openmeteo.get("hourly", {}).get("cloudcover_mid", []),
            "cloudcover_high": openmeteo.get("hourly", {}).get("cloudcover_high", []),
            "precipitation_probability": openmeteo.get("hourly", {}).get("precipitation_probability", []),
            "sunset_daily": openmeteo.get("daily", {}).get("sunset", [])
        },

        # OpenMeteo Air Quality data
         "air_quality": {
            "pm2_5": airquality.get("hourly", {}).get("pm2_5", []),
            "aod": airquality.get("hourly", {}).get("aerosol_optical_depth", []),
            "aq_time": airquality.get("hourly", {}).get("time", [])
        }
    }

    return raw

if __name__ == "__main__":
    # Start Prometheus metrics server
    start_http_server(8000)
    city = "Harrogate"

    while True:
        try:
            # do the thing
            compute("London")
        except Exception as e:
            print(f"Error occurred: {e}")
        time.sleep(15)
