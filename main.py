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


def is_sunset_for_city(sunset_time):
    sunset_time_struct = time.strptime(sunset_time, "%Y-%m-%dT%H:%M")
    sunset_epoch = calendar.timegm(sunset_time_struct)
    current_epoch = time.time()
    seconds_diff = abs(int(current_epoch) - sunset_epoch)
    hours_between = seconds_diff / 60 / 60
    if hours_between > 1:
        return False
    else: 
        return True


def is_sunrise_for_city(sunrise_time):
    sunrise_time_struct = time.strptime(sunrise_time, "%Y-%m-%dT%H:%M")
    sunrise_epoch = calendar.timegm(sunrise_time_struct)
    current_epoch = time.time()
    seconds_diff = abs(int(current_epoch) - sunrise_epoch)
    hours_between = seconds_diff / 60 / 60
    if hours_between > 1:
        return False
    else: 
        return True

def return_req_obj(city):
    lat_long = get_lat_long(city)
    ret = requests.get("https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41&daily=sunset,sunrise&current=rain,relative_humidity_2m&forecast_days=1")
    return ret.json()

def get_data_into_object():
    objs = []
    with open("uk_cities.txt", "r") as file:   
        cities_array = list(map(lambda x: x.rstrip("\n"), file.readlines()))
        for city in cities_array:    
            res = return_req_obj(city)
            lat_long = get_lat_long(city) 
            current_time_struct = time.gmtime(time.time())
            current_time_str = str(current_time_struct.tm_year) \
            + "-" + str(current_time_struct.tm_mon) \
            + "-" + str(current_time_struct.tm_mday) \
            + "T" + str(current_time_struct.tm_hour) \
            + ":" + str(current_time_struct.tm_min)  \
            + ":" + str(current_time_struct.tm_sec) \
            + "Z"
            objs.append({"name": city, 
                         "is_sunrise": is_sunrise_for_city(res["daily"]["sunrise"][0]), 
                         "is_sunset": is_sunset_for_city(res["daily"]["sunset"][0]), 
                         "lat": lat_long[0], 
                         "long": lat_long[1], 
                         "created_at": current_time_str,
                         "rain": res["current"]["rain"],
                         "humidity": res["current"]["relative_humidity_2m"]
                         })
    return objs

def update_cities_json():
    obj = get_data_into_object()
    my_semaphore.acquire()
    with open("./json_data/data.json", "w") as file:
        json.dump(obj, file)
    my_semaphore.release()
    
        

class My_Handler(server.SimpleHTTPRequestHandler):
    def __init__(self, request, client_address, server, *, directory = None):
        super().__init__(request, client_address, server, directory=directory)
    
    def do_GET(self):
        
        if self.path != "/json_data/data.json":
            self.send_error(403)
        else:
            my_semaphore.acquire()
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
    server_thread.run()
    update_thread.start()


            

   

