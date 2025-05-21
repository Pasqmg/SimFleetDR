import json
import time

import aiohttp

from demandResponsive.main.globals import SERVICE_MINUTES_PER_PASSENGER, STOPS_FILE


################################################
###### Auxiliary functions for generators ######
################################################

async def request_route_to_server(origin, destination, route_host="http://router.project-osrm.org/", verbose=0):
    """
    Queries the OSRM for a path.

    Args:
        origin (list): origin coordinate (longitude, latitude)
        destination (list): target coordinate (longitude, latitude)
        route_host (string): route to host server of OSRM service

    Returns:
        list, float, float = the path, the distance of the path and the estimated duration
    """
    if verbose > 0:
        print(f"Origin: {origin}, Destination: {destination}")
    url = route_host + "route/v1/car/{src1},{src2};{dest1},{dest2}?geometries=geojson&overview=full"
    # src1, src2, dest1, dest2 = origin[1], origin[0], destination[1], destination[0]
    src1, src2, dest1, dest2 = origin[0], origin[1], destination[0], destination[1]
    url = url.format(src1=src1, src2=src2, dest1=dest1, dest2=dest2)
    if verbose > 0:
        print(f"URL: {url}")

    try:

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                result = await response.json()

        path = result["routes"][0]["geometry"]["coordinates"]
        path = [[point[1], point[0]] for point in path]
        duration = result["routes"][0]["duration"]
        distance = result["routes"][0]["distance"]
        if path[-1] != destination:
            path.append(destination)
        return path, distance, duration
    except Exception as e:
        print(f"Exception requesting route: {e}")
        print(f"Origin: {origin}, Destination: {destination}")
        print(f"URL: {url}")
        return None, None, None


def load_config(config_file):
    config_dic = {}
    try:
        with open(config_file, 'r') as f:
            config_dic = json.load(f)
    except Exception as e:
        print(str(e))
        exit()
    return config_dic


def load_stops():
    try:
        print(f"Loading stops from {STOPS_FILE}")
        t1 = time.time()
        file = open(STOPS_FILE, "r")
        stops_dic = json.load(file)
        t2 = time.time()
        print(f"\tStops loaded in {t2 - t1} sec.")
        return stops_dic
    except Exception as e:
        print(str(e))
        exit()


def get_stop_coords(stop):
    return [stop.get("geometry").get("coordinates")[1], stop.get("geometry").get("coordinates")[0]]


def get_coords_from_id(id, stop_dic):
    found = False
    i = 0
    while not found and i < len(stop_dic["features"]):
        data = stop_dic["features"][i]
        if data.get("id") == id:
            found = True
            return get_stop_coords(data)
        i += 1
    if not found:
        print(f"Error: Couldn't find stop {id}")


def ids_to_points(origin_id, destination_id):
    origin_coords = get_stop_coords(origin_id)
    p1 = (origin_coords[1], origin_coords[0])
    destination_coords = get_stop_coords(destination_id)
    p2 = (destination_coords[1], destination_coords[0])
    return p1, p2


################################################
###### Auxiliary functions for Scheduler #######
################################################

def get_service_time(npass):
    """
    Return the time needed to pickup/setdown npass passengers
    """
    return SERVICE_MINUTES_PER_PASSENGER * npass



