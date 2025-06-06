import json
from loguru import logger
from asyncio import CancelledError

from simfleet.common.lib.customers.models.taxicustomer import TaxiCustomerStrategyBehaviour
from simfleet.communications.protocol import (
    INFORM_PERFORMATIVE,
    CANCEL_PERFORMATIVE,
    PROPOSE_PERFORMATIVE
)
from simfleet.utils.status import TRANSPORT_WAITING, TRANSPORT_MOVING_TO_CUSTOMER, TRANSPORT_IN_CUSTOMER_PLACE, CUSTOMER_WAITING, \
    CUSTOMER_IN_TRANSPORT, CUSTOMER_IN_DEST, CUSTOMER_ASSIGNED


################################################################
#                                                              #
#                       Customer Strategy                      #
#                                                              #
################################################################

class AcceptFirstRequestBehaviour(TaxiCustomerStrategyBehaviour):
    """
    A customer strategy behavior that accepts the first proposal it receives from a transport agent.
    It defines how the customer agent interacts with transport agents and handles different communication protocols.

    Inherits from:
        TaxiCustomerStrategyBehaviour: A base class for customer behaviors in the electric taxi fleet system.

    Methods:
        run(): The main coroutine responsible for the strategy's execution. It listens for messages
               and reacts based on the agent's current status and the message's performative.
    """

    async def run(self):
        """
                The core coroutine that implements the customer strategy.
                It handles message receiving, proposal acceptance, refusal, and status updates.
                The customer will accept the first valid transport proposal and update its status
                based on the incoming messages from transport agents.
        """

        if self.agent.status is None:
            self.agent.status = CUSTOMER_WAITING
            return

        # If the customer does not have a fleet manager assigned, get the list of fleet managers.
        if self.agent.get_fleetmanagers() is None:

            fleetmanager_list = await self.agent.get_list_agent_position(self.agent.fleet_type, self.agent.get_fleetmanagers())

            self.agent.set_fleetmanagers(fleetmanager_list)

            return

        if self.agent.status == CUSTOMER_WAITING:

            # New statistics
            # Event 1: Customer Request
            self.agent.events_store.emit(
                event_type="customer_request",
                details={}
            )

            await self.send_request(content={})

        try:
            msg = await self.receive(timeout=5)

            if msg:
                performative = msg.get_metadata("performative")
                transport_id = msg.sender
                content = json.loads(msg.body)
                logger.debug("Agent[{}]: The agent informed of: {}".format(self.agent.name, content))

                # Handle transport proposals.
                if performative == PROPOSE_PERFORMATIVE:
                    if self.agent.status == CUSTOMER_WAITING:
                        logger.debug(
                            "Agent[{}]: The agent received proposal from transport [{}]".format(
                                self.agent.name, transport_id
                            )
                        )

                        # New statistics
                        # Event 3: Transport Offer Acceptance
                        self.agent.events_store.emit(
                            event_type="transport_offer_acceptance",
                            details={}
                        )

                        await self.accept_transport(transport_id)
                        self.agent.status = CUSTOMER_ASSIGNED
                    else:
                        await self.refuse_transport(transport_id)

                # Handle transport cancellation.
                elif performative == CANCEL_PERFORMATIVE:
                    if self.agent.transport_assigned == str(transport_id):
                        logger.warning(
                            "Agent[{}]: The agent received a CANCEL from Transport [{}].".format(
                                self.agent.name, transport_id
                            )
                        )
                        self.agent.status = CUSTOMER_WAITING

                # Handle status updates from the transport.
                elif performative == INFORM_PERFORMATIVE:
                    if "status" in content:
                        status = content["status"]

                        if status == TRANSPORT_MOVING_TO_CUSTOMER:
                            logger.info(
                                "Agent[{}]: The agent waiting for transport.".format(self.agent.name)
                            )

                            # New statistics
                            # Event 4: Travel for Pickup
                            self.agent.events_store.emit(
                                event_type="wait_for_pickup",
                                details={}
                            )

                        elif status == TRANSPORT_IN_CUSTOMER_PLACE:
                            self.agent.status = CUSTOMER_IN_TRANSPORT
                            logger.info("Agent[{}]: The agent in transport.".format(self.agent.name))

                            # New statistics
                            # Event 5: Customer Pickup
                            self.agent.events_store.emit(
                                event_type="customer_pickup",
                                details={}
                            )

                            # New statistics
                            # Event 6: Travel to destination
                            self.agent.events_store.emit(
                                event_type="travel_to_destination",
                                details={}
                            )

                            await self.inform_transport(transport_id, CUSTOMER_IN_TRANSPORT)
                        elif status == CUSTOMER_IN_DEST:
                            self.agent.status = CUSTOMER_IN_DEST

                            # New statistics
                            # Event 7: Travel to destination
                            self.agent.events_store.emit(
                                event_type="trip_completion",
                                details={}
                            )

                            await self.inform_transport(transport_id, CUSTOMER_IN_DEST)
                            logger.info(
                                "Agent[{}]: The agent arrived to destination.".format(
                                    self.agent.name
                                )
                            )

        except CancelledError:
            logger.debug("Cancelling async tasks...")

        except Exception as e:
            logger.error(
                "EXCEPTION in AcceptFirstRequestBehaviour of agent [{}]: {}".format(
                    self.agent.name, e
                )
            )
