import requests
import os
from dotenv import load_dotenv
import time
from datetime import datetime, timedelta
from http import server
import calendar
from pathlib import Path
import json
import threading

# Threading stuff
my_semaphore = threading.Semaphore()

load_dotenv()
weatherAPI = os.getenv("API_KEY")
if not weatherAPI:
    raise ValueError("API_KEY not found in environment variables")



def get_lat_long(city):
    with open("./json_data/lat_long.json", "r") as file:
        arr = json.load(file)
        for dic in arr:
            if list(dic.keys())[0] == city:
                return dic[city][0], dic[city][1]


def get_sunset_time_for_city(city):
    cords = get_lat_long(city)
    ret = requests.get("https://api.open-meteo.com/v1/forecast?latitude=" + str(cords[0]) + "&longitude=" + str(cords[1]) + "&daily=sunset&forecast_days=1&temporal_resolution=native")
    return ret.json()["daily"]["sunset"][0]

def get_sunrise_time_for_city(city):
    cords = get_lat_long(city)
    ret = requests.get("https://api.open-meteo.com/v1/forecast?latitude=" + str(cords[0]) + "&longitude=" + str(cords[1]) + "&daily=sunrise&forecast_days=1&temporal_resolution=native")
    return ret.json()["daily"]["sunrise"][0]  

def is_sunset_for_city(city):
    # Define a city boundary
    sunset_time = get_sunset_time_for_city(city)
    sunset_time_struct = time.strptime(sunset_time, "%Y-%m-%dT%H:%M")
    sunset_epoch = calendar.timegm(sunset_time_struct)
    current_epoch = time.time()
    seconds_diff = abs(int(current_epoch) - sunset_epoch)
    hours_between = seconds_diff / 60 / 60
    if hours_between > 1:
        return False
    else: 
        return True


def is_sunrise_for_city(city):
    # Define a city boundary
    sunset_time = get_sunrise_time_for_city(city)
    sunset_time_struct = time.strptime(sunset_time, "%Y-%m-%dT%H:%M")
    sunset_epoch = calendar.timegm(sunset_time_struct)
    current_epoch = time.time()
    seconds_diff = abs(int(current_epoch) - sunset_epoch)
    hours_between = seconds_diff / 60 / 60
    if hours_between > 1:
        return False
    else: 
        return True

def get_cities_with_sunsets_and_sunrises():
    objs = []
    with open("uk_cities.txt", "r") as file:   
        cities_array = list(map(lambda x: x.rstrip("\n"), file.readlines()))
        for city in cities_array:            
            is_sunset = is_sunset_for_city(city)
            is_sunrise = is_sunrise_for_city(city)     
            objs.append({city: [is_sunrise, is_sunset]})
    return objs

def update_cities_json():
    
    with open("./json_data/data.json", "w") as file:
        obj = get_cities_with_sunsets_and_sunrises()
        my_semaphore.acquire()
        json.dump(obj, file)
        my_semaphore.release()
    
        

class My_Handler(server.SimpleHTTPRequestHandler):
    def __init__(self, request, client_address, server, *, directory = None):
        super().__init__(request, client_address, server, directory=directory)
    
    def do_GET(self):
        my_semaphore.acquire()
        if self.path != "/json_data/data.json":
            self.send_error(403)
        else:
            super().do_GET()
        my_semaphore.release()
        



def run():
    http_server = server.HTTPServer(('127.0.0.1', 8000), My_Handler)
    http_server.serve_forever()



if __name__ == "__main__":
    update_cities_json()
    print("starting server")
    update_thread = threading.Thread(target=update_cities_json)
    server_thread = threading.Thread(target=run)
    run()
    update_thread.start()
    

            

   

