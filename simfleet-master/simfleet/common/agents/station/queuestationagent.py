import json
import time

from loguru import logger
from collections import deque
from spade.message import Message
from spade.template import Template
from spade.behaviour import CyclicBehaviour, OneShotBehaviour

from simfleet.common.geolocatedagent import GeoLocatedAgent

from simfleet.communications.protocol import (
    REQUEST_PROTOCOL,
    REQUEST_PERFORMATIVE,
    ACCEPT_PERFORMATIVE,
    REFUSE_PERFORMATIVE,
    CANCEL_PERFORMATIVE,
    INFORM_PERFORMATIVE,
    COORDINATION_PROTOCOL,
)


class QueueStationAgent(GeoLocatedAgent):
    """
    A QueueStationAgent is responsible for managing a queue of agents (vehicles) requesting various services,
    such as charging or fueling. It extends GeoLocatedAgent to include geographic position tracking, and handles
    both the queue of waiting agents and the management of service slots.

    Attributes:
        queuebehaviour (QueueBehaviour): Manages the waiting lists and the queue logic.
        waiting_lists (dict): Tracks the waiting lists of agents for each service type.
        simulatorjid (str): Identifier for the simulator agent that provides coordination.
    """

    def __init__(self, agentjid, password):
        GeoLocatedAgent.__init__(self, agentjid, password)

        # Initialize queue management behaviour
        self.queuebehaviour = self.QueueBehaviour()

        self.waiting_lists = {}  # Waiting lists for each service type

        # JID of the simulator agent
        self.simulatorjid = None

    def set_simulatorjid(self, jid):
        """
        Sets the JID of the simulator agent responsible for coordination.

        Args:
            jid (str): The JID of the simulator agent.
        """
        self.simulatorjid = str(jid)

    def get_simulatorjid(self):
        """
        Returns the JID of the simulator agent.

        Returns:
            str: The simulator agent JID.
        """
        return self.simulatorjid

    async def setup(self):
        """
        Configures the agent, setting up the behavior templates to handle different performative messages.
        """
        logger.debug("Agent[{}]: Queue station running".format(self.name))

        template1 = Template()
        template1.set_metadata("protocol", REQUEST_PROTOCOL)
        template1.set_metadata("performative", REQUEST_PERFORMATIVE)

        template2 = Template()
        template2.set_metadata("protocol", REQUEST_PROTOCOL)
        template2.set_metadata("performative", CANCEL_PERFORMATIVE)

        self.add_behaviour(self.queuebehaviour, template1 | template2)

    def add_queue(self, name):
        """
        Adds a queue for a specific bus line or service line.

        Args:
            line (str): The name of the line or service.
            **arguments: Additional arguments related to the line.
        """

        if name not in self.waiting_lists:

            self.waiting_lists[name] = deque()  # Create a deque for the line

            logger.debug(
                "Agent[{}]: The queue ({}) has been inserted.".format(self.name, name)
            )
        else:
            logger.warning("Agent[{}]: The queue ({}) exists.".format(self.name, name))

    def remove_queue(self, name):
        if name in self.waiting_lists:
            del self.waiting_lists[name]
            logger.warning(
                "Agent[{}]: The queue ({}) has been removed. ".format(self.name, name)
            )

    async def request_agent_position(self, agent_id, content):
        """
        Requests the position of an agent by sending a message.

        Args:
            agent_id (str): The ID of the agent.
            content (dict): The content of the message.
        """
        reply = Message()
        reply.to = str(agent_id)
        reply.set_metadata("protocol", COORDINATION_PROTOCOL)
        reply.set_metadata("performative", REQUEST_PERFORMATIVE)
        reply.body = json.dumps(content)
        await self.send(reply)

    def to_json(self):
        data = super().to_json()
        return data

    # Queue management for agents requesting services
    class QueueBehaviour(CyclicBehaviour):
        """
        Manages the queue of agents waiting for services and handles requests for entry and cancellation.
        """

        def __init__(self):
            super().__init__()

        def total_queue_size(self, service_name):
            """
            Returns the total size of the queue for a given service.

            Args:
                service_name (str): The name of the service.

            Returns:
                int: The number of agents in the queue.
            """
            return len(self.agent.waiting_lists[service_name])

        def queue_agent_to_waiting_list(self, service_name, id_agent, **kwargs):
            """
            Adds an agent to the waiting list for a specific service.

            Args:
                service_name (str): The name of the service.
                id_agent (str): The ID of the agent.
                **kwargs: Additional arguments for the agent.
            """
            self.agent.waiting_lists[service_name].append((id_agent, kwargs))

        def dequeue_first_agent_to_waiting_list(self, service_name):
            """
            Removes and returns the first agent from the waiting list for a service.

            Args:
                service_name (str): The name of the service.

            Returns:
                tuple: A tuple containing the agent ID and arguments.
            """
            if len(self.agent.waiting_lists[service_name]) == 0:
                return None
            return self.agent.waiting_lists[service_name].popleft()

        def dequeue_agent_to_waiting_list(self, service_name, id_agent):
            """
            Removes a specific agent from the waiting list of a service.

            Args:
                service_name (str): The name of the service.
                id_agent (str): The ID of the agent to remove.
            """
            if service_name in self.agent.waiting_lists:
                for agent in self.agent.waiting_lists[service_name]:
                    if agent[0] == id_agent:
                        self.agent.waiting_lists[service_name].remove(agent)
                        break

        def find_queue_position(self, service_name, agent_id):
            try:
                position = self.agent.waiting_lists[service_name].index(agent_id)
                return position
            except ValueError:
                return None

        def get_queue(self, service_name):
            if service_name in self.agent.waiting_lists:
                return self.agent.waiting_lists[service_name]

        async def accept_request_agent(self, agent_id, content=None):
            """
            Accepts a request from an agent by sending a message.

            Args:
                agent_id (str): The ID of the agent.
                content (dict, optional): The content of the message.
            """
            if content is None:
                content = {}
            reply = Message()
            reply.to = str(agent_id)
            reply.set_metadata("protocol", REQUEST_PROTOCOL)
            reply.set_metadata("performative", ACCEPT_PERFORMATIVE)
            reply.body = json.dumps(content)
            await self.send(reply)
            logger.debug(
                "Agent[{}]: The agent accepted entry proposal".format(self.agent.name)
            )

        async def refuse_request_agent(self, agent_id):
            """
            Refuses a request from an agent by sending a message.

            Args:
                agent_id (str): The ID of the agent.
            """
            reply = Message()
            reply.to = str(agent_id)
            reply.set_metadata("protocol", REQUEST_PROTOCOL)
            reply.set_metadata("performative", REFUSE_PERFORMATIVE)
            content = {}
            reply.body = json.dumps(content)

            await self.send(reply)
            logger.debug(
                "Agent[{}]: The agent refused proposal from agent [{}]".format(
                    self.agent.name, agent_id
                )
            )

        async def on_start(self):
            logger.debug(
                "Agent[{}]: Strategy ({}) started.".format(
                    self.agent.name, type(self).__name__
                )
            )

        async def run(self):
            """
            Main behavior logic for handling agent requests, including acceptance, refusal,
            and cancellation based on service availability.
            """
            msg = await self.receive(timeout=5)

            if msg:
                performative = msg.get_metadata("performative")
                protocol = msg.get_metadata("protocol")
                agent_id = msg.sender
                content = json.loads(msg.body)

                if protocol == REQUEST_PROTOCOL and performative == CANCEL_PERFORMATIVE:

                    if "service_name" in content:
                        service_name = content["service_name"]

                    logger.warning(
                        "Agent[{}]: The agent received a REFUSE from agent [{}].".format(
                            self.agent.name, agent_id
                        )
                    )
                    self.dequeue_agent_to_waiting_list(service_name, str(agent_id))

                    logger.debug(
                        "Agent[{}]: The agent [{}] has been dequeue.".format(
                            self.agent.name, agent_id
                        )
                    )
                elif (
                    protocol == REQUEST_PROTOCOL
                    and performative == REQUEST_PERFORMATIVE
                ):

                    if "service_name" in content:
                        service_name = content["service_name"]

                    if "line" in content:
                        service_name = content["line"]

                    if "object_type" in content:
                        object_type = content["object_type"]

                    if "args" in content:
                        arguments = content["args"]

                    # Check proximity before enqueuing
                    template3 = Template()
                    template3.set_metadata("protocol", COORDINATION_PROTOCOL)
                    template3.set_metadata("performative", INFORM_PERFORMATIVE)

                    instance = CheckNearBehaviour(
                        self.agent.get_simulatorjid(),
                        str(agent_id),
                        service_name,
                        object_type,
                        arguments,
                    )
                    self.agent.add_behaviour(instance, template3)

                    await instance.join()  # Wait for the behaviour to complete

                    service_name = instance.service_name
                    agent_position = instance.agent_position
                    user_agent_id = instance.user_agent_id
                    arguments = instance.arguments

                    if (
                        service_name not in self.agent.waiting_lists
                        or not self.agent.near_agent(
                            coords_1=self.agent.get_position(), coords_2=agent_position
                        )
                    ):

                        await self.refuse_request_agent(user_agent_id)
                        logger.warning(
                            "Agent[{}]: The agent has REFUSED request from agent [{}] for service ({})".format(
                                self.agent.name, user_agent_id, service_name
                            )
                        )
                    else:

                        # Queue
                        self.queue_agent_to_waiting_list(
                            service_name, str(user_agent_id), **arguments
                        )

                        content = {"station_id": str(self.agent.jid)}
                        await self.accept_request_agent(user_agent_id, content)

                        logger.info(
                            "Agent[{}]: The agent [{}] has been queue".format(
                                self.agent.name,
                                user_agent_id,
                            )
                        )
                else:
                    logger.warning(
                        "Agent[{}]: The agent has not received agent position of [{}] from the Simulator".format(
                            self.agent.name,
                            agent_id,
                        )
                    )


class CheckNearBehaviour(OneShotBehaviour):
    def __init__(
        self, simulatorjid, user_agent_id, service_name, object_type, arguments
    ):
        super().__init__()

        self.agent_simulator_id = simulatorjid
        self.user_agent_id = user_agent_id
        self.service_name = service_name
        self.object_type = object_type
        self.arguments = arguments
        self.agent_position = None

    async def request_agent_position_near(self, agent_id, content):
        reply = Message()
        reply.to = str(agent_id)
        reply.set_metadata("protocol", COORDINATION_PROTOCOL)
        reply.set_metadata("performative", REQUEST_PERFORMATIVE)
        reply.body = json.dumps(content)
        await self.send(reply)

    async def run(self):

        content = {"user_agent_id": self.user_agent_id, "object_type": self.object_type}
        await self.request_agent_position_near(
            agent_id=self.agent_simulator_id, content=content
        )

        msg = await self.receive(timeout=30)

        if msg:
            performative = msg.get_metadata("performative")
            protocol = msg.get_metadata("protocol")
            agent_id = msg.sender
            content = json.loads(msg.body)

            if (
                protocol == COORDINATION_PROTOCOL
                and performative == INFORM_PERFORMATIVE
            ):

                if "agent_position" in content:
                    agent_position = content["agent_position"]

                if "user_agent_id" in content:
                    user_agent_id = content["user_agent_id"]

                logger.debug(
                    "Agent[{}]: The agent has received msg from agent [{}] for near check".format(
                        self.agent.name, agent_id
                    )
                )

                self.agent_position = agent_position

            else:
                logger.warning(
                    "Agent[{}]: The agent has not received agent position of [{}] from the Simulator".format(
                        self.agent.name,
                        agent_id,
                    )
                )
