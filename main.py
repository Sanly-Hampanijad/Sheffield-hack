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

    try:
        r.raise_for_status()
    except Exception as e:
        print("Open-Meteo forecast HTTP error:", e)
        print("Response text:", r.text[:1000])
        raise
    data = r.json()

    if "hourly" in data:
        h = data["hourly"]
    if "daily" in data:
        d = data["daily"]

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

    return data


# Scoring Functions
## cloud layer score - high & mid clouds = good, low clouds = bad
## precip score - precip = bad
## air score - 
## time score - no need to include here

def cloud_layer_score(clow, cmid, chigh):
    # Normalize to 0-1
    low_score = 1 - (clow / 100.0)
    mid_score = cmid/100
    high_score = chigh/100

    return clamp01((0.3*low_score + 0.3*mid_score + 0.4*high_score))

def precipitation_score(precip_prob_pct):
    return clamp01(1 - (precip_prob_pct / 100.0))

def air_quality_score(pm25_ugm3, aod):
    # Normalize PM2.5 to 0-50=good, >150=bad
    pm_score = clamp01(1.0 - min(150, pm25_ugm3)/150) # cap at 150
    aod_score = clamp01(1.0 - min(1.0, aod))  # AOD typically 0-1
    air_score = 0.5*pm_score + 0.5*aod_score
    return clamp01(air_score)

def time_score(minutes_from_sunset):
    # ideal is 0 (sunset time), linear dropoff to 0 at ±45 minutes
    # might drop this out entirely, decide tomorrow
    return clamp01(1 - (abs(minutes_from_sunset) / 60.0))

def sunset_probability(cloud, precip, air, time):
    cloud = cloud_layer_score(G_CLOUD_LOW, G_CLOUD_MID, G_CLOUD_HIGH)
    precip = precipitation_score(G_PRECIP_PROB)
    air = air_quality_score(G_PM25, G_AOD)
    time = time_score(G_MINUTES_FROM_SUNSET)
    
    result = clamp01(
        WEIGHTS["cloud"] * cloud +
        WEIGHTS["precip"] * precip +
        WEIGHTS["air"] * air +
        WEIGHTS[time])
    
    return result

def get_sunset_hour_index(sunset_iso, hourly_times):
    if not sunset_iso or not hourly_times:
        return None

    sunset_dt = datetime.fromisoformat(sunset_iso)  # already ISO (e.g. 2025-11-29T15:56)
    hourly_dt = [datetime.fromisoformat(t) for t in hourly_times]

    # Find hour nearest to sunset time
    best_i = min(
        range(len(hourly_dt)),
        key=lambda i: abs((hourly_dt[i] - sunset_dt).total_seconds())
    )
    return best_i


def compute(city):
    raw = collect_raw_data(city)

    # Populate basic WeatherAPI gauges immediately
    G_TEMP.labels(city=city).set(raw["temp_c"] or 0.0)
    G_CLOUD.labels(city=city).set(raw["cloud_overall"] or 0.0)
    G_VIS.labels(city=city).set(raw["visibility_km"] or 0.0)
    G_HUM.labels(city=city).set(raw["humidity_pct"] or 0.0)

    # Extract forecast and aq arrays
    forecast = raw["forecast"]
    aq = raw["air_quality"]
    hourly_times = forecast.get("hourly_time", [])
    localtime = raw.get("localtime")

    # --- SUNSET HOUR VALUES ---
    sunset_list = raw["forecast"]["sunset_daily"]
    hourly_times = raw["forecast"]["hourly_time"]

    if sunset_list:
        sunset_iso = sunset_list[0]  # today's sunset
        sunset_idx = get_sunset_hour_index(sunset_iso, hourly_times)

        clow = raw["forecast"]["cloudcover_low"][sunset_idx]
        cmid = raw["forecast"]["cloudcover_mid"][sunset_idx]
        chigh = raw["forecast"]["cloudcover_high"][sunset_idx]
        precip = raw["forecast"]["precipitation_probability"][sunset_idx]
        pm25 = raw["air_quality"]["pm2_5"][sunset_idx]
        aod = raw["air_quality"]["aod"][sunset_idx]
        
        print(f"DEBUG: sunset_idx={sunset_idx} clow={clow} cmid={cmid} chigh={chigh} precip={precip} pm25={pm25} aod={aod}")

        # Populate gauges, only if value is not None
        if clow is not None:
            G_CLOUD_LOW.labels(city=city).set(clow)
        if cmid is not None:
            G_CLOUD_MID.labels(city=city).set(cmid)
        if chigh is not None:
            G_CLOUD_HIGH.labels(city=city).set(chigh)
        if precip is not None:
            G_PRECIP_PROB.labels(city=city).set(precip)
        if pm25 is not None:
            G_PM25.labels(city=city).set(pm25)
        if aod is not None:
            G_AOD.labels(city=city).set(aod)

    else:
        print("DEBUG: no index found; skipping forecast gauge population.")

    # Compute minutes_from_sunset and set its gauge (if sunset available)
    try:
        # pick today's sunset from forecast (first daily entry)
        sunset_list = forecast.get("sunset_daily", [])
        if sunset_list:
            sunset_iso = sunset_list[0]  # e.g. '2025-11-29T15:56'
            # normalize localtime -> ISO
            lt_iso = localtime.replace(" ", "T")
            lt_dt = datetime.fromisoformat(lt_iso)
            st_dt = datetime.fromisoformat(sunset_iso)
            minutes_from_sunset = (lt_dt - st_dt).total_seconds() / 60.0  # negative = before sunset
            G_MINUTES_FROM_SUNSET.labels(city=city).set(minutes_from_sunset)
            G_SUNSET_WINDOW.labels(city=city).set(1.0 if abs(minutes_from_sunset) <= 45.0 else 0.0)
        else:
            print("DEBUG: no sunset_daily value available")
    except Exception as e:
        print("DEBUG: error computing minutes_from_sunset:", e)

    # Return raw for further inspection if caller wants it
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
        
    with open("uk_cities.txt", "r") as file:   
        cities_array = list(map(lambda x: x.rstrip("\n"), file.readlines()))

    while True:
        try:
            # do the thing
            compute("London")
        except Exception as e:
            print(f"Error occurred: {e}")
        time.sleep(15)
