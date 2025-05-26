import asyncio
import json
import sys

from loguru import logger
from asyncio import CancelledError
from spade.behaviour import CyclicBehaviour
from spade.message import Message
from spade.template import Template
from spade.behaviour import State

from simfleet.utils.helpers import (
    PathRequestException,
    AlreadyInDestination,
)

from simfleet.utils.status import TRANSPORT_MOVING_TO_STATION, CUSTOMER_IN_DEST, TRANSPORT_MOVING_TO_DESTINATION, \
    TRANSPORT_WAITING, TRANSPORT_SELECT_DEST

from simfleet.communications.protocol import (
    REQUEST_PROTOCOL,
    INFORM_PERFORMATIVE,
    REGISTER_PROTOCOL,
    REQUEST_PERFORMATIVE,
    ACCEPT_PERFORMATIVE,
    REFUSE_PERFORMATIVE, TRAVEL_PROTOCOL,
)

from simfleet.common.agents.transport import TransportAgent

class DRTransportAgent(TransportAgent):
    """
            Represents a DR Transport agent in the transport system.

            Attributes:
            """

    def __init__(self, agentjid, password, **kwargs):
        super().__init__(agentjid, password)

        self.fleetmanager_id = kwargs.get('fleet', None)
        self.init_time = None
        self.itinerary = None
        self.index_current_stop = 0
        self.current_stop = None
        self.capacity = None
        self.current_capacity = None
        # For movement
        self.set("origin_stop", None)
        self.set("destination_stop", None)
        self.set("rerouting", False) # if True, the vehicle is going to be rerouted while travelling

        # Transport in stop event
        self.set("arrived_to_stop", None)  # new
        self.transport_arrived_to_stop_event = asyncio.Event()

        def transport_arrived_to_stop_callback(old, new):
            if not self.transport_arrived_to_stop_event.is_set() and new is True:
                self.transport_arrived_to_stop_event.set()

        self.transport_arrived_to_stop_callback = transport_arrived_to_stop_callback

    def check_rerouting(self):
        return self.get('rerouting')

    def clear_rerouting(self):
        self.set('rerouting', False)

    def set_rerouting(self):
        self.set('rerouting', True)

    def update_itinerary(self, new_itinerary):
        """
        Updates the itinerary of the transport, returning the data of the stop that was previously
        the next stop of the transport.
        This allows us to check if immediate rerouting is needed.
        """
        logger.debug(f"Transport {self.agent_id} updating itinerary while at its {self.index_current_stop} stop: "
                     f"{self.current_stop}")
        prev_next_stop = None
        if self.itinerary is not None:
            # TODO ensure transport is not at last stop
            if self.index_current_stop == len(self.itinerary)-1:
                logger.error(f"Transport {self.agent_id} is at the last stop of its itinerary, cannot update it")
                sys.exit(1)
            prev_next_stop = self.itinerary[self.index_current_stop+1]
        self.itinerary = new_itinerary
        return prev_next_stop

    def set_capacity(self, capacity):
        """
            Sets the capacity of the bus and initializes the current capacity.

            Args:
                capacity (int): The total capacity of the bus.
        """
        self.capacity = capacity
        self.current_capacity = capacity

    async def setup(self):
        """
            Sets up the transport agent with the registration and travel behaviors.
        """
        try:
            template = Template()
            template.set_metadata("protocol", REGISTER_PROTOCOL)
            register_behaviour = RegistrationBehaviour()
            self.add_behaviour(register_behaviour, template)
            while not self.has_behaviour(register_behaviour):
                logger.warning(
                    "Transport {} could not create RegisterBehaviour. Retrying...".format(
                        self.agent_id
                    )
                )
                self.add_behaviour(register_behaviour, template)
            self.ready = True
        except Exception as e:
            logger.error(
                "EXCEPTION creating RegisterBehaviour in Transport {}: {}".format(
                    self.agent_id, e
                )
            )

        try:
            template = Template()
            template.set_metadata("protocol", TRAVEL_PROTOCOL)
            travel_behaviour = TravelBehaviour()
            self.add_behaviour(travel_behaviour, template)
            while not self.has_behaviour(travel_behaviour):
                logger.warning(
                    "Transport {} could not create TravelBehaviour. Retrying...".format(
                        self.agent_id
                    )
                )
                self.add_behaviour(travel_behaviour, template)
            self.ready = True
        except Exception as e:
            logger.error(
                "EXCEPTION creating TravelBehaviour in Transport {}: {}".format(
                    self.agent_id, e
                )
            )

    def run_strategy(self):
        """
        Sets the strategy for the transport agent.

        Args: strategy_class (``DRTransportStrategyBehaviour``): The class to be used. Must inherit from
        ``BusStrategyBehaviour``
        """
        if not self.running_strategy:
            template1 = Template()
            template1.set_metadata("protocol", REQUEST_PROTOCOL)
            self.add_behaviour(self.strategy(), template1)
            self.running_strategy = True


    async def set_position(self, coords=None):
        """
        Sets the position of the transport. If no position is provided it is located in a random position.

        Args:
            coords (list): a list coordinates (longitude and latitude)
        """

        await super().set_position(coords)
        self.set("current_pos", coords)

        if self.is_in_destination():
            logger.info(
                "Transport {} has arrived to destination. Status: {}".format(
                    self.agent_id, self.status
                )
            )
            await self.arrived_to_stop()

    def get_position(self):
        return self.get("current_pos")

    def setup_current_stop(self):
        """
            Sets the current location based on the transport's position.
        """
        # We search on the itinerary that contains only non-visited stops
        self.current_stop = self.itinerary[self.index_current_stop]
        if self.current_stop['coords'] != self.get('current_pos'):
            logger.error(f"Transport {self.agent_id} is not located where it was supposed to be: \n"
                         f"{self.current_stop['coords']} != {self.get('current_pos')}\n"
                         f"Current stop: {self.current_stop}")
        # for stop_dict in self.itinerary:
        #     if stop_dict['coords'] == self.get('current_pos'):
        #         self.current_stop = stop_dict

    def update_current_stop(self):
        """
        Sets the current stop as the next one. To be executed after moving.
        """
        self.index_current_stop += 1
        self.setup_current_stop()

    def compare_stops(self, dict1, dict2):
        """
        Compares the main attributes of two stops
        """
        return (dict1['stop_id'] == dict2['stop_id'] and dict1['coords'] == dict2['coords'] and
                dict1['passenger_id'] == dict2['passenger_id'])

    def search_current_stop(self):
        """
        Returns the index of the transport's current stop within all_itinerary
        """
        for i, stop_dict in enumerate(self.itinerary):
            if self.compare_stops(stop_dict, self.current_stop):
                return i
        return None

    async def arrived_to_stop(self):
        """
            Marks the current stop as arrived and triggers the event.
        """
        logger.debug(f"Transport {self.agent_id} has arrived to stop with coords {self.get('curren_pos')}")
        self.update_current_stop()
        logger.success(f"Transport {self.agent_id} arrived to stop "
                       f"\n\t{self.current_stop}")
        # my_next_stop = self.itinerary[0]
        # if self.current_stop['coords'] == my_next_stop['coords']:
        #     logger.debug(f"Transport {self.agent_id} arrived to the correct next stop")
        #     logger.debug(f"Current: {self.current_stop}")
        #     logger.debug(f"Scheduled: {my_next_stop}")
        #     # Remove itinerary[0] from self.itinerary
        #     self.itinerary = self.itinerary[1:]
        # else:
        #     logger.error(f"Transport {self.agent_id} arrived to a stop that was not its next stop")
        #     logger.error(f"Current: {self.current_stop}")
        #     logger.error(f"Should be: {my_next_stop}")
        # Trigger callback for DRTransportStrategyBehaviour
        self.set("arrived_to_stop", True)

    async def stop_movement(self):
        logger.info(f"Stopping current movement of transport {self.agent_id}")
        self.set("arrived_to_stop", True)


class RegistrationBehaviour(CyclicBehaviour):
    """
    Manages the registration process for the bus agent in the fleet.

    Methods:
        on_start(): Initializes the registration behavior.
        send_registration(): Sends a registration proposal to the fleet manager.
        run(): Executes the behavior, handling registration acceptance or rejection.
    """

    async def on_start(self):
        logger.debug("Strategy {} started in transport".format(type(self).__name__))

    async def send_registration(self):
        """
        Sends a registration proposal message to the fleet manager.
        """
        logger.debug(
            "Transport {} sent proposal to register to manager {}".format(
                self.agent.name, self.agent.fleetmanager_id
            )
        )
        content = {
            "name": self.agent.name,
            "jid": str(self.agent.jid),
            "fleet_type": self.agent.fleet_type,
        }
        msg = Message()
        msg.to = str(self.agent.fleetmanager_id)
        msg.set_metadata("protocol", REGISTER_PROTOCOL)
        msg.set_metadata("performative", REQUEST_PERFORMATIVE)
        msg.body = json.dumps(content)
        await self.send(msg)

    async def run(self):
        try:
            if not self.agent.registration:
                await self.send_registration()
            msg = await self.receive(timeout=10)
            if msg:
                performative = msg.get_metadata("performative")
                if performative == ACCEPT_PERFORMATIVE:
                    content = json.loads(msg.body)
                    self.agent.set_registration(True, content)
                    logger.info(
                        "[{}] Registration in the fleet manager accepted: {}.".format(
                            self.agent.name, self.agent.fleetmanager_id
                        )
                    )
                    self.kill(exit_code="Fleet Registration Accepted")
                elif performative == REFUSE_PERFORMATIVE:
                    logger.warning(
                        "Registration in the fleet manager was rejected (check fleet type)."
                    )
                    self.kill(exit_code="Fleet Registration Rejected")
        except CancelledError:
            logger.debug("Cancelling async tasks...")
        except Exception as e:
            logger.error(
                "EXCEPTION in RegisterBehaviour of Transport {}: {}".format(
                    self.agent.name, e
                )
            )

class TravelBehaviour(CyclicBehaviour):
    """
    Listen for FleetManager requests of current position or incoming itinerary updates.
    if current position, reply with self.get("current_pos")
    if itinerary_update, update itinerary, check if immediate rerouting necessary
        if immediate rerouting, suspend movement (if any), suspend strategy behaviour, go to SelectDestState
    """
    async def on_start(self):
        logger.debug("Strategy {} started in transport".format(type(self).__name__))

    async def send_current_position(self):
        msg = Message()
        contents = {"current_pos": self.agent.get_position()}
        msg.to = str(self.agent.fleetmanager_id)
        msg.set_metadata("protocol", REQUEST_PROTOCOL)
        msg.set_metadata("performative", REQUEST_PERFORMATIVE)
        msg.body = json.dumps(contents)
        await self.send(msg)

    async def run(self):
        msg = await self.receive(timeout=10)
        if msg:
            sender = msg.sender
            content = json.loads(msg.body)
            performative = msg.get_metadata("performative")
            protocol = msg.get_metadata("protocol")
            logger.debug(f"Transport {self.agent.name} received message from {sender}: {msg.body}")
            # Manager asking for the transport's position
            if "position" in content.keys():
                await self.send_current_position()
            # Manager sending new itinerary
            elif "new_itinerary" in content.keys():
                new_itinerary = content.get("new_itinerary")
                if self.agent.itinerary is None:
                    # First time the transport receives the itinerary
                    self.agent.update_itinerary(new_itinerary)
                    logger.success(f"Transport {self.agent.agent_id} received its first itinerary:\n\t{new_itinerary}")
                else:
                    # The stop that was the next stop before the update of the itinerary
                    prev_next_stop = self.agent.update_itinerary(new_itinerary)
                    logger.success(f"Transport {self.agent.agent_id} updated its itinerary:\n\t{new_itinerary}")
                    # If the next stop is no longer the same, we need rerouting
                    if not self.agent.compare_stops(prev_next_stop, self.agent.itinerary[self.agent.index_current_stop+1]):
                        logger.debug(f"Previous next stop changes after itinerary update:\n"
                                    f"Previous: {prev_next_stop}\n"
                                    f"Current: {self.agent.itinerary[self.agent.index_current_stop+1]}")
                        # TODO Note to self: we should not use agent.status here
                        if self.agent.status == TRANSPORT_SELECT_DEST:
                            self.agent.set_rerouting()
                        if self.agent.status == TRANSPORT_MOVING_TO_DESTINATION:
                            self.agent.set_rerouting()
                            await self.agent.stop_movement()
                        # if agent.status == TRANSPORT_WAITING all is fine
            # Manager sent unknown message
            else:
                logger.error(f"Transport {self.agent.agent_id} received unknown message from {msg.sender}: {msg.body}")

class DRTransportStrategyBehaviour(State):
    """
    Class to define a transport strategy for the DR Transport agent. Inherit from this class to implement custom strategies.
    """

    async def on_start(self):
        logger.debug(
            "Strategy {} started in transport {}".format(
                type(self).__name__, self.agent.name
            )
        )

    def get_next_stop(self):
        if self.agent.itinerary is None:
            return None
        if self.agent.index_current_stop < len(self.agent.itinerary):
            return self.agent.itinerary[self.agent.index_current_stop + 1]
        return self.agent.itinerary[-1]

    async def move_to_next_stop(self, next_destination):
        """
            Moves the transport to the next stop.

            Args:
                next_destination (tuple): Coordinates of the next stop.
        """
        logger.info("Transport {} in route to {}".format(self.agent.name, next_destination))
        dest = next_destination
        # set current destination as next destination
        self.agent.set("next_pos", dest)
        # Invoke move_to
        try:
            await self.agent.move_to(dest)
        except AlreadyInDestination:
            self.agent.dest = dest
            await self.agent.arrived_to_stop()
        except PathRequestException as e:
            logger.error(
                "Raising PathRequestException in pick_up_customer for {}".format(
                    self.agent.name
                )
            )
            raise e

