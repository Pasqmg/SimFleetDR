import asyncio
import json
import time

from loguru import logger

from simfleet.dr_fleetmanager_model import DRFleetManagerStrategyBehaviour
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
    Cyclic state that periodically checks whether new customer requests have arrived
    """
    async def on_start(self):
        # For the first execution, set agent init time
        if self.agent.init_time is None:
            self.agent.init_time = time.time()
        self.agent.status = MANAGER_WAITING
        logger.info(f"Manager {self.agent.agent_id} in WaitForRequestsState at time "
                    f"{time.time()-self.agent.init_time:.2f} (seconds)")

    async def run(self):
        # For the first execution
        # If transport agents are not registered yet, wait
        if len(self.agent.get_transport_agents()) < self.agent.get_expected_num_transports() :
            logger.warning(f"Manager strategy will not run until they have registered "
                           f"{self.agent.get_expected_num_transports()} transports")
            await asyncio.sleep(5)
            return self.set_next_state(MANAGER_WAITING)

        # If initial transport itineraries have not been sent, do so and load
        if not self.agent.check_initial_itineraries_sent():
            logger.info(f"Manager {self.agent.agent_id} sending initial itineraries to transports")
            await self.send_updated_itineraries()
            self.agent.set_initial_itineraries_sent()
            return self.set_next_state(MANAGER_WAITING)

        # Usual behaviour, load requests file, check for new requests
        new_request = self.check_for_requests()
        # If new requests, ask current transport positions, go to wait for reply
        if new_request:
            logger.info(f"Manager {self.agent.agent_id} has new requests")
            # Clear dict of transport positions
            self.agent.clear_positions()
            # Send message to all transports
            await self.ask_transport_positions()
            return self.set_next_state(MANAGER_REQUEST_POSITIONS)
        # If no new request, sleep for 30 seconds before checking again
        else:
            logger.info(
                f"Manager {self.agent.agent_id} does not have new requests")
            await asyncio.sleep(30)
            return self.set_next_state(MANAGER_WAITING)

class RequestTransportPositionsState(DRFleetManagerStrategyBehaviour):
    """
    Cyclic state that processes messages with transport agent positions until all have been received
    """

    def __init__(self):
        super().__init__()
        # Clear number of pending messages
        self.n_pending = None

    async def on_start(self):
        self.agent.staus = MANAGER_REQUEST_POSITIONS
        logger.info("Manager {} in RequestTransportPositions".format(self.agent.agent_id))

        # Pending number of messages to process in this iteration
        n_transports = len(self.agent.get_transport_agents())
        n_messages = len(self.agent.get_transport_positions())
        self.n_pending = n_transports - n_messages
        logger.info(f"Manager waiting for {self.n_pending} position messages from transports")

    async def run(self):
        if self.n_pending > 0:
            logger.debug(f"Awaiting messages for 10 seconds...")
            msg = await self.receive(timeout=10)
            if msg:
                sender = msg.sender
                sender_id = sender.node
                sender_position = None
                content = json.loads(msg.body)
                performative = msg.get_metadata("performative")
                protocol = msg.get_metadata("protocol")
                logger.debug(f"Manager {self.agent.agent_id} received message from {msg.sender}: {content}")
                if performative == REQUEST_PERFORMATIVE:
                    if protocol == REQUEST_PROTOCOL:
                        try:
                            sender_position = content["current_pos"]
                        except KeyError:
                            logger.error("Manager received message with no current position: {}".format(content))

                        # Update sender positions
                        current_positions = self.agent.get_transport_positions()
                        logger.debug(f"Manager's current transport positions are: {current_positions}")
                        current_positions[str(sender_id)] = sender_position
                        self.agent.set_transport_positions(current_positions)

                        # TODO self.agent.check_if_stop_exists(sender_position) before creating it
                        # Add sender position as a new database stop
                        self.agent.create_and_add_transport_stop(vehicle_id=msg.sender,
                                                                 current_time=time.time() - self.agent.init_time,
                                                                 coords=sender_position)
                    else:
                        logger.warning(f"Manager received message with unknown protocol: {protocol}")
                else:
                    logger.warning(f"Manager received message with unknown performative {performative}")
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
        logger.info("Manager {} in SendUpdatedItineraries".format(self.agent.agent_id))

    async def run(self):
        # Pass transport_positions to Scheduler
        self.agent.pass_transport_positions()
        # Compute new itineraries
        logger.info(f"Manager {self.agent.agent_id} computing new itineraries...")
        await self.compute_new_itineraries(verbose=1)
        # Send updated itinerary to the corresponding transport
        logger.info(f"\tManager {self.agent.agent_id} sending new itineraries")
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


