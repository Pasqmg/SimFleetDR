import asyncio
import json
import time

from loguru import logger

from simfleet.common.lib.fleet.models.dr_fleetmanager import DRFleetManagerStrategyBehaviour
from simfleet.communications.protocol import REQUEST_PROTOCOL, REQUEST_PERFORMATIVE
from simfleet.utils.abstractstrategies import FSMSimfleetBehaviour
from simfleet.utils.status import MANAGER_WAITING, MANAGER_REQUEST_POSITIONS, MANAGER_UPDATE


################################################################
#                                                              #
#                     FleetManager Strategy                    #
#                                                              #
################################################################

class WaitForRequestsState(DRFleetManagerStrategyBehaviour):
    """

    """
    async def on_start(self):
        if self.agent.init_time is None:
            self.agent.init_time = time.time()
        self.agent.status = MANAGER_WAITING
        logger.debug("Manager {} in WaitForRequestsState".format(self.agent.agent_id))

    async def run(self):
        new_request = self.check_for_requests()
        if new_request:
            # Reset dict of transport positions
            self.agent.clear_positions()
            # Send message to all transports
            await self.ask_transport_positions()
            return self.set_next_state(MANAGER_REQUEST_POSITIONS)
        else:
            # sleep for 10 seconds
            await asyncio.sleep(10)
            return self.set_next_state(MANAGER_WAITING)

class RequestTransportPositionsState(DRFleetManagerStrategyBehaviour):
    """
    Cyclic state that processes messages with transport agent positions until all have been received
    """

    def __init__(self):
        super().__init__()
        self.n_pending = None

    async def on_start(self):
        self.agent.staus = MANAGER_REQUEST_POSITIONS
        logger.debug("Manager {} in RequestTransportPositions".format(self.agent.agent_id))

        # Pending number of messages to process in this iteration
        n_transports = len(self.agent.get_transport_agents())
        n_messages = len(self.agent.get_transport_positions())
        self.n_pending = n_transports - n_messages

    async def run(self):
        if self.n_pending > 0:
            msg = await self.receive(timeout=5)
            if msg:
                sender = msg.sender
                sender_position = None
                content = json.loads(msg.body)
                performative = msg.get_metadata("performative")
                protocol = msg.get_metadata("protocol")
                logger.debug(f"Manager {self.agent.agent_id} received message from {msg.sender}")
                if performative == REQUEST_PERFORMATIVE:
                    if protocol == REQUEST_PROTOCOL:
                        try:
                            sender_position = content["current_pos"]
                        except KeyError:
                            logger.error("Manager received message with no current position: {}".format(content))

                        # Update sender positions
                        current_positions = self.agent.get_transport_positions()
                        current_positions[str(sender)] = sender_position
                        self.agent.set_transport_positions(current_positions)

                        # Add sender position as a new database stop
                        self.agent.create_and_add_transport_stop(vehicle_id=msg.sender,
                                                                 current_time=time.time() - self.agent.init_time,
                                                                 coords=sender_position)
            # Loop
            return self.set_next_state(MANAGER_REQUEST_POSITIONS)
        else:
            return self.set_next_state(MANAGER_UPDATE)


class SendUpdatedItineraries(DRFleetManagerStrategyBehaviour):
    """
    Manager has the updated position of each transport. Compute new itineraries and send.
    """
    async def on_start(self):
        self.agent.status = MANAGER_UPDATE
        logger.debug("Manager {} in SendUpdatedItineraries".format(self.agent.agent_id))

    async def run(self):
        # Pass transport_positions to Scheduler
        self.agent.pass_transport_positions()
        # Compute new itineraries
        await self.compute_new_itineraries()
        # Send updated itinerary to the corresponding transport
        await self.send_updated_itineraries()
        # TODO maybe await for OK from transports?
        # Go back to wait for requests
        return self.set_next_state(MANAGER_WAITING)

class FSMDRFleetManagerStrategyBehaviour(FSMSimfleetBehaviour):

    def __init__(self):
        super().__init__()
        self.init_time = None

    async def on_start(self):
        self.init_time = 0
        await super().on_start()

    def setup(self):
        # Add states to the FSM
        self.add_state(MANAGER_WAITING, WaitForRequestsState(), initial=True)
        self.add_state(MANAGER_REQUEST_POSITIONS, RequestTransportPositionsState())
        self.add_state(MANAGER_UPDATE, SendUpdatedItineraries())
        # Transitions
        self.add_transition(MANAGER_WAITING, MANAGER_WAITING) # Waiting for new requests
        self.add_transition(MANAGER_WAITING, MANAGER_REQUEST_POSITIONS) # New requests detected
        self.add_transition(MANAGER_REQUEST_POSITIONS, MANAGER_REQUEST_POSITIONS) # Processing transport position msgs
        self.add_transition(MANAGER_REQUEST_POSITIONS, MANAGER_UPDATE) # All transport positions processed
        self.add_transition(MANAGER_UPDATE, MANAGER_WAITING) # New itineraries sent to every transport


