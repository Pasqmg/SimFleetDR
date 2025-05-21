import json
from operator import truediv

from loguru import logger
from openpyxl.packaging.manifest import Override

from simfleet.common.agents.fleetmanager import FleetManagerStrategyBehaviour, FleetManagerAgent
from simfleet.communications.protocol import TRAVEL_PROTOCOL, REQUEST_PERFORMATIVE
from spade.message import Message
from spade.behaviour import State

from demandResponsive.main.database import Database
from demandResponsive.main.launcher import itinerary_from_db, request_from_db
from demandResponsive.main.request import Request
from demandResponsive.main.scheduler import Scheduler


class DRFleetManagerAgent(FleetManagerAgent):

    def __init__(self, agentjid, password):
        super().__init__(agentjid, password)

        # Time control
        self.init_time = None # started by the strategic behaviour
        # demandResponsive
        self.database = None
        self.scheduler = None
        self.clear_positions()
        # TODO Hardcoded, must be adapted before running
        self.dynamic_config_path = '/Users/pasqmg/PycharmProjects/SimFleetDR/input/dynamic_config.json'
        self.dynamic_stops_path = '/Users/pasqmg/PycharmProjects/SimFleetDR/input/dynamic_stops.json'
        # Scheduling
        self.known_customers = {} # customers already known by the manager
        self.unscheduled_customers = [] # list of known but unscheduled customers
        self.scheduled_customers = [] # list of known and scheduled customers
        self.rejected_customers = [] # list of rejected customers/requests
        self.modified_itineraries = {}
        self.initial_itineraries_sent = False

    async def setup(self):
        """
        Adds TransportRegistrationForFleetBehaviour to the agent
        """
        await super().setup()
        self.demandResponsive_setup()

    def demandResponsive_setup(self):
        # Create database
        self.database = Database()

        # Load config and update database
        file = open(self.dynamic_config_path, 'r')
        config_dict = json.load(file)
        self.database.update_config(config_dict)

        # Load itineraries from config file
        itineraries, itinerary_insertion_dic = itinerary_from_db(self.database)

        # Create and initialize scheduler object
        self.scheduler = Scheduler(self.database)
        self.scheduler.pending_requests = []
        self.scheduler.itineraries = itineraries
        self.scheduler.itinerary_insertion_dic = itinerary_insertion_dic

        # Get initial itineraries
        self.modified_itineraries = self.scheduler.get_all_itineraries_as_stop_list()

    def check_initial_itineraries_sent(self):
        return self.initial_itineraries_sent

    def set_initial_itineraries_sent(self):
        self.initial_itineraries_sent = True

    def clear_modified_itineraries(self):
        self.modified_itineraries = {}

    def get_modified_itinerary(self, agent_name):
        return self.modified_itineraries.get(agent_name)

    def add_database(self, database: Database):
        self.database = database

    def get_transport_agents(self):
        return self.get("transport_agents")

    def get_transport_positions(self):
        return self.get("transport_positions")

    def set_transport_positions(self, transport_positions):
        self.set("transport_positions", transport_positions)

    def pass_transport_positions(self):
        self.scheduler.set_transport_positions(self.get("transport_positions"))

    def clear_positions(self):
        """
        Dict with entries "agent_name": position ([coords])
        """
        self.set("transport_positions", {})

    def add_customer(self, customer_dict):
        """
        Adds a customer to the agent's knowledge after receiving its corresponding request
        """
        self.known_customers[customer_dict['name']] = customer_dict

    def create_request_from_customer(self, customer_name):
        """
        Creates the Request object that represents a given customer
        precondition: The customer dict must be in self.database
        :return:
        """
        req = None
        customers = self.database.get_customers()
        for customer in customers:
            if customer == customer_name:
                customer_id = customer
                passenger_id = customer_id
                attributes = self.database.get_customer_dic(passenger_id)

                coords = self.database.get_customer_origin(customer_id)
                origin_id = self.database.get_stop_id([coords[1], coords[0]])

                coords = self.database.get_customer_destination(customer_id)
                destination_id = self.database.get_stop_id([coords[1], coords[0]])

                req = Request(self.database, passenger_id, origin_id, destination_id,
                          attributes.get("origin_time_ini"), attributes.get(
                    "origin_time_end"),
                          attributes.get("destination_time_ini"), attributes.get(
                    "destination_time_end"),
                          attributes.get("npass"))
        return req

    def load_and_update_dynamic_stops(self, new_stop):
        # Read file
        file = open(self.dynamic_stops_path, 'r')
        stops_dict = json.load(file)
        # Update JSON
        stops_dict["features"].append(new_stop)
        # Save file
        file = open(self.dynamic_config_path, 'w')
        json.dump(stops_dict, file)

    def create_and_add_stop(self, customer_name, type, issue_time, coords):
        stop =  {
            "type": "Feature",
            "geometry": {
            "coordinates": coords
        }, "id": str(customer_name)+"-"+str(type)+"-"+str(issue_time)}
        # Add stop to dynamic_stops file
        self.load_and_update_dynamic_stops(stop) # TODO may be unnecessary, may be costly
        self.database.add_stop(stop)

    def create_and_add_transport_stop(self, vehicle_id, issue_time, coords):
        self.create_and_add_stop(customer_name=vehicle_id, type="current", issue_time=0, coords=coords)

    def add_customer_to_database(self, customer_dict):
        self.database.add_customer(customer_dict)

    def add_request_to_scheduler(self, request):
        # Add customer to unscheduled customers
        self.unscheduled_customers.append(request.passenger_id)
        # Update the scheduler
        self.scheduler.pending_requests.append(request)

    async def schedule_new_requests(self):
        self.clear_modified_itineraries()
        end, rejected = await self.scheduler.schedule_new_requests()
        if len(rejected) > 0:
            pass
        # Once the scheduler finishes, we have new itineraries in
        # self.scheduler.itineraries. We can also extract the modified ones.
        self.modified_itineraries = self.scheduler.get_modified_itineraries()

class DRFleetManagerStrategyBehaviour(State):
    """
    Inherited from FleetManagerStrategyBehaviour:
        - get_transport_agents
        - send_registration (to the Directory)
    """

    async def on_start(self):
        """
            Logs that the strategy has started in the Fleet Manager.
        """
        logger.debug("Strategy {} started in manager".format(type(self).__name__))

    def check_for_requests(self) -> bool:
        # Load customers from dynamic_config
        file = open(self.agent.dynamic_config_path, "r")
        dynamic_config = json.load(file)
        current_customers = dynamic_config.get("customers")
        # Compare those customers with known customers
        new_customers = [x for x in current_customers if x['name'] not in self.agent.known_customers.keys()]
        if new_customers:
            # Crate customer's stops and add them to dynamic stops and the database stops
            for new_customer in new_customers:
                # Create origin stop
                self.agent.create_and_add_stop(new_customer["name"], "origin", new_customer["issue_time"],
                                               new_customer["position"])
                # Create destination stop
                self.agent.create_and_add_stop(new_customer["name"], "destination", new_customer["issue_time"],
                                               new_customer["destination"])
                # Add new customer to database
                self.agent.add_customer_to_database(new_customer)
                # Create customer request
                new_request = self.agent.create_request_from_customer(new_customer["name"])
                # Add new customer to scheduler.pending_requests
                self.agent.add_request_to_scheduler(new_request)
            return True
        return False

    async def ask_transport_positions(self):
        """
        Sends a message to every registered transport agent asking for its current position.
        """
        # Message contents
        contents = {"position"}
        transports = self.agent.get_transport_agents()
        for agent in transports:
            msg = Message()
            msg.to = str(agent.jid)
            msg.set_metadata("protocol", TRAVEL_PROTOCOL)
            msg.set_metadata("performative", REQUEST_PERFORMATIVE)
            msg.body = json.dumps(contents)
            await self.send(msg)


    async def compute_new_itineraries(self):
        """
        Executes the scheduler for the new requests. Before that, we must have:
        1) Detected new customers and created their associated stops and requests (self.check_for_requests())
        2) Updated current transport positions, both in self.agent and self.agent.scheduler,
            and created stops representing them  in the Database
            - self.ask_transport_positions()
            - self.agent.create_and_add_transport_stop
            - self.agent.pass_transport_positions()
        """
        await self.agent.schedule_new_requests()
        # once the process finishes, modified itineraries are in self.agent.modified_itineraries

    async def send_updated_itineraries(self):
        """
        For each transport agent with a modified itinerary, send a message with new itinerary
        """
        for agent_name in self.agent.modified_itineraries.keys():
            await self.send_update_transport_itinerary(agent_name)

    async def send_update_transport_itinerary(self, agent_name):
        """
        Sends a message to transport agent_name containing its new itinerary.
        """
        # Message contents
        modified_itinerary = None
        try:
            modified_itinerary = self.agent.get_modified_itinerary(agent_name)
        except AttributeError as e:
            print(f"Transport {agent_name} has no modified itinerary; {e}")
        contents = {'new_itinerary' : modified_itinerary}
        # Send message
        msg = Message()
        msg.to = str(agent_name)
        msg.set_metadata("protocol", TRAVEL_PROTOCOL)
        msg.set_metadata("performative", REQUEST_PERFORMATIVE)
        msg.body = json.dumps(contents)
        await self.send(msg)
