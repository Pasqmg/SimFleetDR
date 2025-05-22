import argparse
import json
import os

from loguru import logger

from demandResponsive.main.globals import OUTPUT_PATH, CONFIG_PATH
from demandResponsive.main.database import Database
from demandResponsive.main.itinerary import Itinerary
from demandResponsive.main.request import Request
from demandResponsive.main.scheduler import Scheduler

VERBOSE = 0


def list_files(directory):
    try:
        # List all files in the specified directory
        files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
        return files
    except Exception as e:
        print(f"Error: {e}")
        return []


def remove_extensions(file_list):
    base_names = [os.path.splitext(file)[0] for file in file_list]
    return base_names


def list_filenames(directory):
    files = list_files(directory)
    return remove_extensions(files)


def request_from_db(database):
    """
    Creation of Request objects from customer information in the configuration file
    """
    db = database
    customers = db.get_customers()
    requests = []
    for customer in customers:
        customer_id = customer
        passenger_id = customer_id
        attributes = db.get_customer_dic(passenger_id)

        coords = db.get_customer_origin(customer_id)
        origin_id = db.get_stop_id([coords[1], coords[0]])

        coords = db.get_customer_destination(customer_id)
        destination_id = db.get_stop_id([coords[1], coords[0]])

        req = Request(db, passenger_id, origin_id, destination_id,
                      attributes.get("origin_time_ini"), attributes.get(
                "origin_time_end"),
                      attributes.get("destination_time_ini"), attributes.get(
                "destination_time_end"),
                      attributes.get("npass"))

        requests.append(req)
        if VERBOSE > 0:
            print("Created request from configuration file:")
            print(req.to_string())
    return requests


def itinerary_from_db(database):
    """
    Creation of initial Itinerary objects from vehicle information in the configuration file.
    Initial itineraries contain as first and last stop the warehouse where the vehicle is stored.

    Initialization of itinerary_insertion_dic, a data structure reflecting the insertions contained in each itinerary.
    """
    db = database
    transports = db.get_transports()
    if transports is None:
        logger.error(f"Launcher did not get transports from database: {transports}")
    itineraries = []
    itinerary_insertion_dic = {}
    for transport in transports:
        vehicle_id = transport

        coords = db.get_transport_origin(vehicle_id)
        start_stop_id = db.get_stop_id([coords[1], coords[0]])

        coords = db.get_transport_destination(vehicle_id)
        end_stop_id = db.get_stop_id([coords[1], coords[0]])

        attributes = db.get_transport_dic(vehicle_id)

        I = Itinerary(
            db,
            vehicle_id,
            attributes.get("capacity"),
            start_stop_id,
            end_stop_id,
            attributes.get("start_time"),
            attributes.get("end_time"))
        itineraries.append(I)
        itinerary_insertion_dic[vehicle_id] = []
        if VERBOSE > 0:
            print("Created itinerary from configuration file:")
            print(I.to_string())
            print(I.start_stop.to_string())
            print(I.end_stop.to_string())
    return itineraries, itinerary_insertion_dic


def scheduler_insertion_search(config_file):
    """
    Test function to initialize a Scheduler and debug its insertion search procedure.
    Kept here for future developments.
    """
    sche = Scheduler(config_file)
    requests = request_from_db(config_file)
    itineraries = itinerary_from_db(config_file)
    sche.pending_requests = requests
    sche.itineraries = itineraries
    sche.schedule_all_requests_by_time_order()
    for request in sche.pending_requests:
        best_insertion, feasible_insertions = sche.exhaustive_search(request)
        print(
            "Found {} feasible insertion(s)".format(
                len(feasible_insertions)))
        for insert, ci in feasible_insertions:
            print(insert.to_string())
        print("\nBest insertion found:")
        if best_insertion is not None:
            print(best_insertion.to_string() + "\n")
            sche.insert_trip(best_insertion)
        print(best_insertion.I.to_string())
    print("Final itineraries\n")
    for I in sche.itineraries:
        print(I.to_string())
        for i in range(len(I.stop_list)):
            print("Stop with index {}:\n".format(i))
            print(I.stop_list[i].to_string())
            print("\n")


def run_all_experiments(max_experiments=None):
    count = 0
    database = Database()
    for config_file in list_files(CONFIG_PATH):
        print("Solving config {}".format(config_file))
        database.load_config(config_file)
        # Load itineraries from config file
        itineraries, itinerary_insertion_dic = itinerary_from_db(database)

        # Load requests from config file
        requests = request_from_db(database)

        # Create and initialize scheduler object
        sche = Scheduler(database)
        sche.pending_requests = requests
        sche.itineraries = itineraries
        sche.itinerary_insertion_dic = itinerary_insertion_dic

        # Schedule all requests by order of issuance
        sche.schedule_all_requests_by_time_order(verbose=0)
        output = sche.simulation_stats()

        # Save output file
        with open(OUTPUT_PATH + "out+" + config_file, "w") as outfile:
            json.dump(output, outfile, indent=4)
        print("Outfile saved: out+" + config_file)
        print()


def main(arguments):
    """
    Given a configuration file, runs a Scheduler in its default mode, scheduling Requests by
    ascending issuance time order. The metrics of the solution is stored in an output file.
    """
    config_file = arguments.config_file
    database = Database()
    database.load_config(config_file)
    # Load itineraries from config file
    itineraries, itinerary_insertion_dic = itinerary_from_db(database)

    # Load requests from config file
    requests = request_from_db(database)

    # Create and initialize scheduler object
    sche = Scheduler(database)
    sche.pending_requests = requests
    sche.itineraries = itineraries
    sche.itinerary_insertion_dic = itinerary_insertion_dic

    # Schedule all requests by order of issuance
    sche.schedule_all_requests_by_time_order(verbose=1)
    output = sche.simulation_stats()

    # Save output file
    with open(OUTPUT_PATH + "out+" + config_file, "w") as outfile:
        json.dump(output, outfile, indent=4)
    print("Outfile saved: out+" + config_file)


def debug_main(arguments):
    config_file = arguments.config_file
    database = Database()
    database.load_config(config_file)
    # Load itineraries from config file
    itineraries, itinerary_insertion_dic = itinerary_from_db(database)

    # Load requests from config file
    requests = request_from_db(database)

    # Create and initialize scheduler object
    sche = Scheduler(database)
    sche.pending_requests = requests
    sche.itineraries = itineraries
    sche.itinerary_insertion_dic = itinerary_insertion_dic

    # Debug
    sche.test_insertion()


if __name__ == '__main__':
    run_all_experiments()

    # parser = argparse.ArgumentParser()
    #
    # # Add arguments
    # parser.add_argument("config_file", type=str, help="config_file")
    #
    # # Parse the arguments
    # args = parser.parse_args()
    #
    # # Call the main function with the parsed arguments
    # main(args)
