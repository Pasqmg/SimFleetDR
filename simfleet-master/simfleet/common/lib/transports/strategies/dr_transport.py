import asyncio
import json
import time

from loguru import logger

from simfleet.common.lib.transports.models.dr_transport import DRTransportStrategyBehaviour
from simfleet.utils.abstractstrategies import FSMSimfleetBehaviour

from simfleet.utils.status import TRANSPORT_WAITING, TRANSPORT_MOVING_TO_DESTINATION, TRANSPORT_SELECT_DEST

from simfleet.communications.protocol import (
    REQUEST_PERFORMATIVE,
)

################################################################
#                                                              #
#                       DR Transport Strategy                  #
#                                                              #
################################################################

class InDestState(DRTransportStrategyBehaviour):
    """
        State where the bus is at a stop and allows passengers to board or exit.

        Methods:
            on_start(): Initializes the state and sets the status of the agent.
            run(): Manages passengers boarding and exiting, and updates statistics.
        """
    async def on_start(self):
        if self.agent.init_time is None:
            self.agent.init_time = time.time()
        await super().on_start()
        self.agent.status = TRANSPORT_WAITING
        logger.debug("Transport {} in TransportInDestState".format(self.agent.name))

    async def run(self):
        # Wait until the transport has received the initial itinerary through the travel_behaviour
        if self.itinerary is None:
            await asyncio.sleep(10)
            return self.set_next_state(TRANSPORT_WAITING)

        # Check if the transport needs to be immediately rerouted
        if self.agent.check_rerouting():
            return self.set_next_state(TRANSPORT_SELECT_DEST)

        # Update agent current stop
        self.agent.setup_current_stop()
        # According to the elapsed time, the transport departs the current stop or waits in it
        current_time = time.time() - self.agent.init_time
        if current_time >= self.agent.current_stop['departure_time'] :
            return self.set_next_state(TRANSPORT_SELECT_DEST)
        else:
            # if we have to sleep, do so for 30 seconds (the transport may receive a message from the fleet manager)
            await asyncio.sleep(30)
            return self.set_next_state(TRANSPORT_WAITING)

class SelectDestState(DRTransportStrategyBehaviour):
    """
        State where the bus selects its next destination.

        Methods:
            on_start(): Initializes the state and sets the status of the agent.
            run(): Determines the next stop based on the bus line type and moves to that stop.
        """
    async def on_start(self):
        if self.agent.init_time is None:
            self.agent.init_time = time.time()
        await super().on_start()
        self.agent.status = TRANSPORT_SELECT_DEST
        logger.debug("Transport {} in TransportSelectDestState".format(self.agent.name))

    async def run(self):
        # If we have arrived here because of a rerouting, clear it
        if self.agent.check_rerouting():
            self.agent.clear_rerouting()

        next_destination = self.get_next_stop()
        # if current destination is the end of a route
        if next_destination is None:
            logger.warning(
                "Transport {} has reached the last stop in its itinerary".format(self.agent.jid))

        # Just in case new location arrives exactly as the transport was going to move
        if not self.agent.check_rerouting():
            await self.move_to_next_stop(next_destination['coords'])
            self.set_next_state(TRANSPORT_MOVING_TO_DESTINATION)
        else:
            self.set_next_state(TRANSPORT_SELECT_DEST)
        return


class MovingToDestState(DRTransportStrategyBehaviour):
    """
        State where the bus is moving towards its next destination.

        Methods:
            on_start(): Initializes the state and sets the status of the agent.
            run(): Waits for the bus to arrive at its destination and then transitions states.
    """

    async def on_start(self):
        await super().on_start()
        self.agent.status = TRANSPORT_MOVING_TO_DESTINATION
        logger.debug("Transport {} in TransportMovingToDestState".format(self.agent.name))

    async def run(self):
        # Check if the transport needs to be immediately rerouted
        if self.agent.check_rerouting():
            return self.set_next_state(TRANSPORT_SELECT_DEST)

        if self.agent.is_in_destination():
            return self.set_next_state(TRANSPORT_WAITING)
        # Reset internal flag to False. Coroutines calling wait() will block until set() is called
        self.agent.transport_arrived_to_stop_event.clear()
        # Register an observer callback to be run when the "arrived_to_stop" event is changed
        self.agent.watch_value("arrived_to_stop", self.agent.transport_arrived_to_stop_callback)
        # block behaviour until another coroutine calls set()
        await self.agent.transport_arrived_to_stop_event.wait()
        return self.set_next_state(TRANSPORT_WAITING)



class FSMDRTransportBehaviour(FSMSimfleetBehaviour):
    """
        The finite state machine (FSM) that defines the behavior of the bus transport agent.

        Methods:
            setup(): Configures the FSM with states and transitions.
        """
    def setup(self):
        # Create states
        self.add_state(TRANSPORT_WAITING, InDestState(), initial=True)
        self.add_state(TRANSPORT_MOVING_TO_DESTINATION, MovingToDestState())
        self.add_state(TRANSPORT_SELECT_DEST, SelectDestState())

        # Create transitions
        self.add_transition(TRANSPORT_WAITING, TRANSPORT_WAITING) # Waiting at a stop
        self.add_transition(TRANSPORT_WAITING, TRANSPORT_SELECT_DEST) # Time to leave current stop
        self.add_transition(TRANSPORT_SELECT_DEST, TRANSPORT_MOVING_TO_DESTINATION) # Next stop selected, start movement
        self.add_transition(TRANSPORT_MOVING_TO_DESTINATION, TRANSPORT_WAITING) # Arrived to destination
        self.add_transition(TRANSPORT_MOVING_TO_DESTINATION, TRANSPORT_SELECT_DEST) # Rerouting of next stop
