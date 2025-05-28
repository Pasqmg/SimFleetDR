import json
import os
import random
import time
import requests
from datetime import datetime

# Genera requests y las va guardando el archivo dynamic_config.json,
# en el path de la variable DYNAMIC_CONFIG_PATH. Las guarda en el
# minutos que marca el issue_time.
# Ejemplo donde se generan 2 requests con issue_time:
# generate_requests(2, 3)


DYNAMIC_CONFIG_PATH = "3-transports/dynamic_config.json"

# LAT_MIN, LAT_MAX = 39.14517, 39.69671
# LNG_MIN, LNG_MAX = -0.96315, -0.24918

LAT_MIN, LAT_MAX = 39.41248, 39.51417
LNG_MIN, LNG_MAX = -0.43751, -0.29128


MIN_TIME_BETWEEN_REQUESTS = 30 # en segundos

def generate_random_coordinate():
    lat = random.uniform(LAT_MIN, LAT_MAX)
    lng = random.uniform(LNG_MIN, LNG_MAX)
    return [lat, lng]

def update_dynamic_config_file(new_customers):
    try:
        with open(DYNAMIC_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "customers" not in data:
            data["customers"] = []

        data["customers"].extend(new_customers)

        temp_path = DYNAMIC_CONFIG_PATH + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        os.replace(temp_path, DYNAMIC_CONFIG_PATH)
        print("dynamic_config actualizado")

    except Exception as e:
        print(f"Error actualizando dynamic_config: {e}")

def get_osrm_duration_in_minutes(origin, destination):
    url = f"https://router.project-osrm.org/route/v1/driving/{origin[1]},{origin[0]};{destination[1]},{destination[0]}?overview=false"
    response = requests.get(url)
    data = response.json()
    duration_sec = data['routes'][0]['duration']
    return duration_sec / 60  # devuelve en minutos

def generate_requests(n_requests, duration_minutes):
    duration_seconds = duration_minutes * 60
    start_time = time.time()

    issue_times = sorted(random.sample(range(10, duration_seconds, MIN_TIME_BETWEEN_REQUESTS), n_requests))
    issue_times = [t / 60 for t in issue_times] # pasamos a minutos de nuevo

    requests = []

    for i, offset in enumerate(issue_times):
        issue_time = offset
        # origin_ini = issue_time + random.uniform(5, 30)
        origin_ini = issue_time
        origin_end = origin_ini + random.uniform(30, 45)

        position = generate_random_coordinate()
        destination = generate_random_coordinate()

        try:
            travel_minutes = get_osrm_duration_in_minutes(position, destination)
        except Exception as e:
            print(f"Error al calcular la ruta {i}: {e}")
            travel_minutes = random.uniform(10, 20)

        dest_ini = origin_ini + travel_minutes
        dest_end = origin_end + (travel_minutes * 2.5)

        req = {
            "position": position,
            "destination": destination,
            "issue_time": issue_time,
            "origin_time_ini": origin_ini,
            "origin_time_end": origin_end,
            "destination_time_ini": dest_ini,
            "destination_time_end": dest_end,
            "npass": 1,
            "password": "secret",
            "fleet_type": "dr",
            "name": f"auto_generated_request_{i}"
        }
        requests.append((offset, req))

    # Muestra las requests
    for i, req in enumerate(requests):
        print(f"req {i}: ")
        print(req)
        print()

    # Simula el tiempo de ejecución y añade cuando toque
    print("Starting simulation...")
    for offset, req in requests:
        now = time.time()
        wait_time = start_time + (offset * 60) - now
        if wait_time > 0:
            time.sleep(wait_time)

        update_dynamic_config_file([req])
        print(f"Request '{req['name']}' añadida en el minuto {offset}")

if __name__ == "__main__":
    generate_requests(20, 20)
