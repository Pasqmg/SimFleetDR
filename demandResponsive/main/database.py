import json
import time
import geopy.distance
from loguru import logger

from demandResponsive.main.utils import get_stop_coords
from globals import CONFIG_PATH, ROUTES_FILE, STOPS_FILE
from utils import request_route_to_server

class Database:
    """
    Database object. Loads input files and allows consultations of their information.
    The Scheduler initialises a Database that is then shared with other objects that
    require access to input data.

    Input data is composed by:
        # Stops file (.json). Feature collection of dictionaries defining, for each stop
            - id
            - coordinates
            - (optional) properties

        # Routes file (.json). Dictionary indexed by pairs of stop coordinates that defines,
        for each pair of different stops in the Stops file
            - path (list of coordinates of the driving route that connects the stops)
            - distance (of the route that connects the stops, in meters)
            - duration (estimation of time taken by a transport to traverse the route, in seconds)

        # Configuration file (.json). Dictionary describing the vehicle fleet and customer demand
        of an experiment. All agents must be localised in one of the stops of the Stop file.
            - "transports": List of dictionaries, one per fleet vehicle, defining its
                -- name,
                -- position (origin stop), destination (final stop), (coordinates)
                -- capacity,
                -- speed,
                -- start_time (beginning of shift at position), end_time (end of shift at destination)
            - "customers": List of dictionaries, one per customer request, defining
                -- name,
                -- position (origin stop), destination (destination stop), (coordinates)
                -- npass (number of passengers travelling together)
                -- issue_time (time at which the customer issues their request)
                -- origin_time_ini, origin_time_end (temporal window for pickup at origin stop)
                -- destination_time_ini, destination_time_end (temporal window for arrival at the destination)
    """

    def __init__(self):
        """
        Initialises the Database loading the data contained in the input files.
        Paths to input files are defined in /experimentation/globals.py
            - STOPS_FILE: Path to Stops file
            - ROUTES_FILE: Path to Routes file
            - CONFIG_PATH: Path to configuration files folder, to be completed with the specific configuration file
        """
        self.geodesic_distance_matrix = None
        self.geodesic_distance_dict = None
        self.route_distance_matrix = None
        self.route_distance_dict = None
        self.config_dic = None
        try:
            print(f"Loading STOPS_FILE from {STOPS_FILE}")
            file = open(STOPS_FILE, "r")
            self.stops_dic = json.load(file)
            t1 = time.time()
            print(f"Loading ROUTES_FILE from {ROUTES_FILE}")
            file = open(ROUTES_FILE, "r")
            self.routes_dic = json.load(file)
            t2 = time.time()
            print(f"Routes loaded in {t2-t1}s")
        except Exception as e:
            print(str(e))
            self.stops_dic = {}
            self.routes_dic = {}

    def load_config(self, config_file):
        try:
            # print(f"Loading CONFIG from {CONFIG_PATH + config_file}")
            file = open(CONFIG_PATH + config_file, "r")
            self.config_dic = json.load(file)
        except Exception as e:
            print(str(e))
            exit()

    def update_config(self, config_dict):
        self.config_dic = config_dict

    ################################################
    ########## Stop consultation methods ###########
    ################################################

    def get_stop(self, coords):
        """
        Given a set of coordinates, returns the information of the Stop located at the given coordinates.
        """
        res = None
        for stop in self.stops_dic.get("features"):
            if stop.get("geometry").get("coordinates") == coords:
                res = stop
                break
        if res is None:
            logger.critical(f"ERROR :: There is no stop for coords {coords} in the stops_dic")
            exit()
        return res

    def add_stop(self, stop_dict):
        """
        Adds the information of a stop to self.stops_dic
        """
        self.stops_dic["features"].append(stop_dict)

    def get_stop_id(self, coords):
        """
        Search Stop by coordinates, returning its id
        """
        stop = self.get_stop(coords)
        return stop.get("id")

    def get_stop_coords(self, stop_id):
        """
        Search Stop by id, returning its coordinates.
        """
        for stop in self.stops_dic.get("features"):
            if stop.get("id") == stop_id:
                return [stop.get("geometry").get("coordinates")[1], stop.get("geometry").get("coordinates")[0]]

    def delete_current_stops(self):
        """
        Delete from the stops_dic any stop containing "current" in its id
        """
        keep = [stop for stop in self.stops_dic.get("features") if not stop.get("id").contains("current")]
        self.stops_dic["features"] = keep

    ################################################
    ######### Route consultation methods ###########
    ################################################

    def ids_to_points(self, origin_id, destination_id):
        """
        Given the ids of two stops, returns their corresponding coordinates, formated as points
        """
        origin_coords = self.get_stop_coords(origin_id)
        p1 = (origin_coords[1], origin_coords[0])
        destination_coords = self.get_stop_coords(destination_id)
        p2 = (destination_coords[1], destination_coords[0])
        return p1, p2

    def get_route(self, p1, p2):
        """
        Returns the route connecting stop coordinates p1 and p2
        """
        # Exception: same origin and destination
        if p1 == p2:
            return {"path": [], "distance": 0, "duration": 0}

        key = str(p1) + ":" + str(p2)
        route = self.routes_dic.get(key)
        if route is None:
            # Future refinement: ask OSRM for the route
            logger.critical(f"ERROR :: There is no route for key {key} in the routes_dic")
            exit()
        return route

    async def get_route_from_server(self, origin_id, destination_id):
        # try to get route first, otherwise xd
        origin_coords = get_stop_coords(origin_id)
        destination_coords = get_stop_coords(destination_id)
        path, distance, duration = await request_route_to_server(origin_coords, destination_coords)
        if path is None or distance is None or duration is None:
            print(f"ERROR :: Server returned no route from {origin_id}{origin_coords} to "
                  f"{destination_id}{destination_coords}")
            exit()

        # If route is well formatted, store
        if path and distance and duration:
            p1, p2 = self.ids_to_points(origin_id, destination_id)
            key = str(p1) + ":" + str(p2)
            self.routes_dic[key] = {"path": path, "distance": distance, "duration": duration}

    def get_geodesic_distance_km(self, origin_id, destination_id):
        p1, p2 = self.ids_to_points(origin_id, destination_id)
        return geopy.distance.distance(p1, p2).km

    def get_route_distance_km(self, origin_id, destination_id):
        p1, p2 = self.ids_to_points(origin_id, destination_id)
        route = self.get_route(p1, p2)
        return route.get("distance") / 1000

    def get_route_time_min(self, origin_id, destination_id):
        p1, p2 = self.ids_to_points(origin_id, destination_id)
        route = self.get_route(p1, p2)
        return route.get("duration") / 60

    def get_distance_matrix(self, geodesic=False):
        """
        if geodesic is True, distance among stops is computed as a straight line distance
        otherwise, OSRM's distance computation (driving) is employed
        """
        # Check if already computed
        if geodesic:
            if self.geodesic_distance_matrix is not None:
                return self.geodesic_distance_matrix
        else:
            if self.route_distance_matrix is not None:
                return self.route_distance_matrix
        # Matrix computation
        stops_list = self.stops_dic.get('features')
        distance_matrix = []
        for origin in stops_list:
            origin_id = origin.get('id')
            distances = []
            for dest in stops_list:
                dest_id = dest.get('id')
                if geodesic:
                    distances.append(self.get_geodesic_distance_km(origin_id, dest_id))
                else:
                    distances.append(self.get_route_distance_km(origin_id, dest_id))
            distance_matrix.append(distances)
        # Store data
        if geodesic:
            self.geodesic_distance_matrix = distance_matrix
        else:
            self.route_distance_matrix = distance_matrix

        return distance_matrix

    def get_distance_dict(self, geodesic=False):
        """
        Distance matrix computation for stops whose id does not represent
        its relative order within the stops file. i.e: id = 95240853

        if geodesic is True, distance among stops is computed as a straight line distance
        otherwise, OSRM's distance computation (driving) is employed
        """
        # Check if already computes
        if geodesic:
            if self.geodesic_distance_dict is not None:
                return self.geodesic_distance_dict
        else:
            if self.route_distance_dict is not None:
                return self.route_distance_dict
        # Dict computation
        stops_list = self.stops_dic.get('features')
        distance_dict = {}
        for origin in stops_list:
            origin_id = origin.get('id')
            distances = {}
            for dest in stops_list:
                dest_id = dest.get('id')
                if geodesic:
                    distances[dest_id] = self.get_geodesic_distance_km(origin_id, dest_id)
                else:
                    distances[dest_id] = self.get_route_distance_km(origin_id, dest_id)
            distance_dict[origin_id] = distances
        # Store data
        if geodesic:
            self.geodesic_distance_dict = distance_dict
        else:
            self.route_distance_dict = distance_dict
        return distance_dict

    def get_neighbouring_stops(self, stop_id, max_distance_km=1, geodesic=False):
        distance_matrix = self.get_distance_matrix(geodesic)
        neighbours = []
        for i in range(0, len(distance_matrix[stop_id])):
            if i != stop_id:
                if distance_matrix[stop_id][i] <= max_distance_km:
                    neighbours.append((i, distance_matrix[stop_id][i]))
        return neighbours

    def get_neighbouring_stops_dict(self, stop_id, max_distance_km=1, geodesic=False):
        distance_dict = self.get_distance_dict(geodesic)
        neighbours = []
        for key in distance_dict[stop_id]:
            if key != stop_id:
                if distance_dict[stop_id][key] <= max_distance_km:
                    neighbours.append((key, distance_dict[stop_id][key]))
        return neighbours

    ################################################
    ######### Vehicle consultation methods #########
    ################################################

    def get_transports(self):
        transport_dicts = self.config_dic.get('transports')
        transports = []
        for transport in transport_dicts:
            transports.append(transport.get('name'))
        return transports

    def get_transport_dic(self, transport_id):
        for transport in self.config_dic.get('transports'):
            if transport.get('name') == transport_id:
                return transport

    def get_transport_origin(self, transport_id):
        for transport in self.config_dic.get('transports'):
            if transport.get('name') == transport_id:
                return transport.get('position')

    def get_transport_destination(self, transport_id):
        for transport in self.config_dic.get('transports'):
            if transport.get('name') == transport_id:
                return transport.get('destination')

    ################################################
    #### Customer request consultation methods #####
    ################################################

    def get_customers(self):
        customer_dicts = self.config_dic.get('customers')
        customers = []
        for customer in customer_dicts:
            customers.append(customer.get('name'))
        return customers

    def get_customer_dic(self, customer_id):
        for customer in self.config_dic.get('customers'):
            if customer.get('name') == customer_id:
                return customer

    def get_customer_issue_time(self, customer_id):
        for customer in self.config_dic.get('customers'):
            if customer.get('name') == customer_id:
                return customer.get('issue_time')

    def get_customer_origin(self, customer_id):
        for customer in self.config_dic.get('customers'):
            if customer.get('name') == customer_id:
                return customer.get('position')

    def get_customer_destination(self, customer_id):
        for customer in self.config_dic.get('customers'):
            if customer.get('name') == customer_id:
                return customer.get('destination')

    def add_customer(self, customer_dict):
        self.config_dic['customers'].append(customer_dict)
