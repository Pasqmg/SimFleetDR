"""
Global variable definition.
Adjust the values of these variables to run different experiments and define demand time restrictions.
"""
# GUIMABUS
# # Input/Output global variables
# INPUT_PATH = "../data/input/guimabus/"
# OUTPUT_PATH = "data/output/guimabus/wait-15-travel_factor-1,5/"
# # Intermediate path may be necessary depending on the data folder structure
# INTERMEDIATE_CONFIG_PATH = "../data/configs/guimabus/customer/wait-15-travel_factor-1,5/"
#
# # Path to folder containing problem configuration files
# CONFIG_PATH = "../data/configs/guimabus/win-15-travel_factor-1,5/"
# # Adjust to routes file name
# ROUTES_FILE = INPUT_PATH + 'new_final_routes.json'
# # Adjust to stops file name
# STOPS_FILE = INPUT_PATH + 'final-stops.json'

# COMSIS
# Input/Output global variables
# INPUT_PATH = "../data/input/COMSIS/"
# OUTPUT_PATH = "data/output/"
# # Intermediate path may be necessary depending on the data folder structure
# INTERMEDIATE_CONFIG_PATH = "../data/configs/COMSIS/8v-8cap/"
#
# # Path to folder containing problem configuration files
# CONFIG_PATH = "../data/configs/COMSIS/8v-8cap/"
# # Adjust to routes file name
# ROUTES_FILE = INPUT_PATH + 'routes_500m.json'
# # Adjust to stops file name
# STOPS_FILE = INPUT_PATH + 'final_stops_500m_updated.json'

# ADCAIJ
# Input/Output global variables
INPUT_PATH = "/Users/pasqmg/PycharmProjects/SimFleetDR/input/"
EXPERIMENT_PATH = INPUT_PATH + "3-transports/"
OUTPUT_PATH = EXPERIMENT_PATH + "output/"
# Intermediate path may be necessary depending on the data folder structure
INTERMEDIATE_CONFIG_PATH = ""

# Path to folder containing problem configuration files
CONFIG_PATH = EXPERIMENT_PATH + "dynamic_config.json"
# Adjust to routes file name
ROUTES_FILE = EXPERIMENT_PATH + 'empty_routes.json'
# Adjust to stops file name
STOPS_FILE = EXPERIMENT_PATH + 'dynamic_stops.json'
# Vehicle itineraries file
VEHICLE_ITINERARIES = EXPERIMENT_PATH + 'vehicle_itineraries.json'
# Customer itineraries file
CUSTOMER_ITINERARIES = EXPERIMENT_PATH + 'customer_itineraries.json'

# Demand-generation global variables, which affect the time window computation of each Stop within a Request
# OSRM petition url
ROUTE_HOST = "http://localhost:5000/"
# Time-related globals
MAXIMUM_WAITING_TIME_MINUTES = 15
SERVICE_MINUTES_PER_PASSENGER = 1
TRAVEL_FACTOR = 1.5  # to compute maximum on-board time
SLACK_TIME_MINUTES = 5  # minutes of margin for the system to have flexibility

# Speed factor
SPEEDUP = 1.0  # factor to speed up the simulation, e.g., 2.0 means that the simulation runs twice as fast
