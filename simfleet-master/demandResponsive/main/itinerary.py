import math

import numpy
import numpy as np

from demandResponsive.main.stop import Stop


class Itinerary:
    """
    Itinerary object. Represents a fleet vehicle in the problem instance. Specifically, it defines the sequence of
    stops the vehicle visits during its active hours. Each visited stop comprises the pickup and/or setdown of at
    least one customer.

    Itineraries are built by inserting trips into them. Each trip is composed by a visit to an origin stop and a
    destination stop. Feasibility checks are implemented to test whether a trip insertion into an itinerary preserves
    the capacity and time constraints of all already inserted trips.

    Itineraries are evaluated according to its cost. Such a cost defines the optimization function of the system.
    """

    def __init__(self, database, vehicle_id, cap, start_stop_id, end_stop_id, start_time, end_time):
        # Database
        self.db = database
        # vehicle to which the itinerary I is assigned
        self.vehicle_id = vehicle_id
        # Capacity of the vehicle
        self.capacity = cap
        # Stop at which the vehicle is located at the beginning of its shift
        self.start_stop = Stop(self.db, start_stop_id)
        # Time at which the vehicle begins its shift
        self.start_time = start_time
        # Stop at which the vehicle must be located at the end of its shift
        self.end_stop = Stop(self.db, end_stop_id)
        # Time at which the vehicle ends its shift
        self.end_time = end_time
        # List of Stop objects that constitutes the itinerary I
        self.stop_list = [self.start_stop, self.end_stop]
        # Last departed stop of the vehicle
        self.current_loc = self.start_stop
        # Kilometers travelled by the vehicle to which I is assigned
        self.traveled_km = self.compute_traveled_km()
        # System cost for I, as criterion for optimization
        self.cost = self.compute_cost()

        # Stats
        # List of waiting times of passengers
        self.customer_waitings = []
        # Dictionaries for customer and vehicle metrics
        self.customer_dict = {}
        self.vehicle_dict = {}

        self.initial_stops_creation()

    def initial_stops_creation(self):
        """
        Creates and initializes the starting and ending Stops of the itinerary, setting also their time windows
        """
        # Trip stop attributes for start stop
        self.start_stop.start_time = self.start_time
        self.start_stop.end_time = math.inf
        self.start_stop.service_time = 0
        self.start_stop.latest = self.start_stop.end_time - self.start_stop.service_time

        # Trip stop attributes for destination stop
        self.end_stop.start_time = self.start_time
        self.end_stop.end_time = self.end_time
        self.end_stop.service_time = 0
        self.end_stop.latest = self.end_stop.end_time = self.end_time - self.end_stop.service_time

        # Itinerary stop attributes for start stop
        self.start_stop.sprev = None
        self.start_stop.snext = self.end_stop
        self.start_stop.npass = 0
        self.start_stop.npres = 0
        self.start_stop.set_leg_time()
        self.start_stop.set_EAT()

        # Itinerary stop attributes for end stop
        self.end_stop.sprev = self.start_stop
        self.end_stop.snext = None
        self.end_stop.npass = 0
        self.end_stop.npres = 0
        self.end_stop.set_leg_time()
        self.end_stop.set_LDT()

        # Time window computations
        self.end_stop.set_EAT()
        self.start_stop.set_LDT()
        self.start_stop.set_slack()
        self.end_stop.set_slack()
        self.start_stop.set_arrival_departure()
        self.end_stop.set_arrival_departure()

    def get_vehicle_position_at_time(self, time: int):
        """
        Returns the node in which the vehicle is at the given time.
        If the vehicle is travelling between nods, return the next visited node.
        """
        # Vehicle is at last stop
        if time >= self.end_time:
            self.current_loc = self.end_stop
            return len(self.stop_list) - 1, "at_stop"

        for i, current_stop in enumerate(self.stop_list):
            # Vehicle is visiting current_node
            if current_stop.arrival_time <= time <= current_stop.departure_time:
                self.current_loc = current_stop
                return i, "at_stop"
            else:
                next_stop = self.stop_list[i + 1]
                # Vehicle is travelling to next_node
                if next_stop.arrival_time > time:
                    self.current_loc = next_stop
                    return i + 1, "travelling_to_stop"  # else, keep searching from next node
        return None, None

    ################################################
    ######## Insertion feasibility checks ##########
    ################################################

    def pickup_insertion_feasibility_check(self, t, Spu, R, T, verbose=0):
        """
        Check feasibility of inserting Spu in R's position, so that leg (R -> R.snext)
        becomes (Spu -> R.snext) therefore creating also a new leg (R -> Spu)

        Feasibility checks make references to the paper whose code was followed for this implementation.
        """
        if verbose > 0:
            print("Checking feasibility of inserting pickup stop {} of trip\n {} between stops {} and {} of "
                  "itinerary\n {}\n".format(Spu.id, t.to_string(), R.id, T.id, self.to_string()))

        # NOTE: Restriction computed in an alternative way. Code is left here commented on purpose.
        # 2nd test of the paper
        # Capacity constraint
        # Maximum number of other passengers sharing travel with trip t
        # npshare_t = self.capacity - t.npass        #
        # # if the npshare_t exceeds the number of seats reserved on departure from R
        # # the trip can not be inserted
        # if npshare_t > R.npres:
        #     if verbose > 0:
        #       print("The number of passengers exceeds the number of seats reserved on "
        #       "departure from R: {} > {}\n".format(npshare_t, R.npres))
        #     return False

        # Time-window constraints #

        # 1st test of the paper
        # if the earliest arrival time at R is later than the latest feasible arrival at Spu
        # the trip can not be inserted after R or any subsequent legs
        if R.eat > Spu.latest:
            if verbose > 0:
                print("The EAT at stop {} is later than the latest feasible arrival at Spu ({}): {} > {}\n"
                      .format(R.id, Spu.id, R.eat, Spu.latest))
            return False, 0  # code 0 indicates to stop searching in this Itinerary

        # 2nd test of the paper
        # Capacity constraint
        available_seats_on_departure_from_R = self.capacity - R.npass
        if t.npass > available_seats_on_departure_from_R:
            if verbose > 0:
                print("The number of passengers exceeds the number of available seats on departure from: {} > {}\n"
                      .format(t.npass, available_seats_on_departure_from_R))
            return False, 1

        # 3rd test of the paper
        # Calculate Spu.eat if coming from R
        Spu_eat = max(R.start_time, R.eat) + R.service_time + self.db.get_route_time_min(R.id, Spu.id)
        Spu_eat_f = max(Spu.start_time, Spu_eat)
        # if the earliest arrival time at Spu is later than the latest feasible arrival at Spu
        # the trip can not be inserted after R
        if Spu_eat > Spu.latest:
            if verbose > 0:
                print("Calculated Spu's EAT if coming from stop {}\n".format(R.id))
                print("The EAT at Spu is later than the latest feasible arrival at Spu: {} > {}\n".format(Spu.eat,
                                                                                                          Spu.latest))
            return False, 1

        # 4th test of the paper
        # Calculate Spu.ldt if going to T
        Spu_ldt = min(T.end_time, T.ldt) - T.service_time - self.db.get_route_time_min(Spu.id, T.id)
        # Spu_ldt_f = min(Spu.end_time, Spu_ldt)
        # if the latest departure time at Spu is sooner than the earliest feasible service start at Spu minus
        # the service time at Spu, the insertion would be infeasible
        if Spu_ldt < Spu_eat_f + Spu.service_time:
            if verbose > 0:
                print("Calculated Spu's LDT if going to stop {}\n".format(T.id))
                print("The LDT at Spu is is sooner than the EAT_F at Spu - service time at Spu: {} < {} - {}\n".format(
                    Spu.ldt, Spu.eat_f, Spu.service_time))
            return False, 1

        # After passing all capacity and time constraints tests, return True to indicate insertion feasibility
        return True, None

    def setdown_insertion_feasibility_check(self, t, index_Spu, index_Ssd, stop_list, Ssd, R, T):
        """
        Assuming an insertion has been found for the pickup stop Spu, creating leg (R* -> Spu),
        Checks the feasibility of inserting setdown stop Ssd in the leg (R -> T), R in {Spu, S*, S.snext, ...}
        """

        # if the earliest arrival time at R is later than the latest feasible arrival at Ssd
        # the trip can not be inserted after R or any subsequent legs
        if R.eat > Ssd.latest:
            return False, 0

        # NOTE: Restriction computed in an alternative way. Code is left here commented on purpose.
        # # the vehicle could not carry the passengers in t past R without becoming overloaded
        # # so the insertion of Ssd in R -> T or any subsequent leg is infeasible
        # npshare_t = self.capacity - t.npass
        # if npshare_t > R.npres:
        #     return False

        for i in range(index_Spu, index_Ssd):
            passengers_on_departure_from_S = stop_list[i].npass + t.npass  # in Spu this number is real
            available_seats_on_departure_from_S = self.capacity - passengers_on_departure_from_S
            if available_seats_on_departure_from_S < 0:
                return False, 1

        # Calculate Ssd.eat if coming from R
        Ssd_eat = max(R.start_time, R.eat) + R.service_time + self.db.get_route_time_min(R.id, Ssd.id)
        Ssd_eat_f = max(Ssd.start_time, Ssd_eat)
        if Ssd_eat > Ssd.latest:
            return False, 1

        # Calculate Ssd.ldt if going to T
        Ssd_ldt = min(T.end_time, T.ldt) - T.service_time - self.db.get_route_time_min(Ssd.id, T.id)
        # Ssd_ldt_f = min(Ssd.end_time, Ssd.ldt)
        if Ssd_ldt < Ssd_eat_f + Ssd.service_time:
            return False, 1

        return True, None

    ################################################
    ####### Itinerary modification methods #########
    ################################################

    def insert_current_stop(self, S):
        """
        Insert stop S in position 0 of the Itinerary, creating leg (S -> T)
        Precondition: Use only on filtered itineraries (itineraries whose first stop is the vehicle's next stop)
        """
        self.stop_list.insert(0, S)
        # Set T's previous stop to S
        T = self.stop_list[1]
        T.sprev = S
        S.leg_time = self.db.get_route_time_min(S.id, T.id)

        # Set time values to S
        S.set_EAT()
        S.set_LDT()
        S.set_slack()

        # Propagate changes in EAT forward from S (may need to be delayed)
        for i in range(1, len(self.stop_list)):
            self.stop_list[i].update_time_window()
            # change = self.stop_list[i].update_EAT()
            # if the change in EAT is 0, there is no need to update the subsequent stops
            # if change == 0:
            #     break

        S.set_arrival_departure()
        T.set_arrival_departure()
        T.set_slack()

        # Update cost
        self.compute_cost()

    def insert_stop(self, S, index_S, npass=0):
        """
        Insert stop S in position index_S of the Itinerary. Assuming R = index_S-1 and T = index_S+1,
        previous leg (R -> T) becomes legs (R -> S) and (S -> T)
        """

        # Insert S after R in the itinerary
        self.stop_list.insert(index_S, S)
        S.sprev = self.stop_list[index_S - 1]
        S.snext = self.stop_list[index_S + 1]

        # Set R's subsequent stop to S
        R = self.stop_list[index_S - 1]  # may be redundant
        R.snext = S
        R.leg_time = self.db.get_route_time_min(R.id, S.id)

        # Set T's previous stop to S
        T = self.stop_list[index_S + 1]
        T.sprev = S
        S.leg_time = self.db.get_route_time_min(S.id, T.id)

        # Set time values to S
        S.set_EAT()
        S.set_LDT()
        S.set_slack()

        # Propagate changes in EAT forward from S (may need to be delayed)
        for i in range(index_S + 1, len(self.stop_list)):
            self.stop_list[i].update_time_window()
            # change = self.stop_list[i].update_EAT()
            # if the change in EAT is 0, there is no need to update the subsequent stops
            # if change == 0:
            #     break

        # Propagate changes in LDT backward from S (may need to be advanced)
        for i in range(index_S - 1, -1, -1):
            self.stop_list[i].update_time_window()
            # change = self.stop_list[i].update_LDT()
            # if the change in EAT is 0, there is no need to update the previous stops
            # if change == 0:
            #     break

        R.set_arrival_departure()
        R.set_slack()
        S.set_arrival_departure()
        T.set_arrival_departure()
        T.set_slack()

        # Set values of passenger-loading variables
        S.npass = R.npass + npass
        S.npres = R.npres + npass

        # Update cost
        self.compute_cost()

    def remove_stop(self, S, index_S):
        """
        Remove stop S in position index_S of the Itinerary. Assuming R = index_S-1 and T = index_S+1,
        previous legs (R -> S) and (S -> T) become leg (R -> T)
        """

        # Get next and previous stops
        R = S.sprev
        T = S.snext

        # Reroute itinerary and adjust leg time
        R.snext = T
        T.sprev = R
        R.leg_time = self.db.get_route_time_min(R.id, T.id)

        # Delete S from the itinerary
        self.stop_list = self.stop_list[0:index_S] + self.stop_list[index_S + 1:]

        # Propagate changes in EAT forward and backward from predecessors and successors of S
        # index_S is now the position of T in the stop list
        # Forward
        for i in range(index_S, len(self.stop_list)):
            try:
                self.stop_list[i].set_EAT()
            except IndexError as e:
                print(e)
                print(f"Index: {i}")
                print(f"List: {self.stop_list}")
        # # Backward
        # for i in range(index_S - 1, -1, -1):
        #     set_EAT(self.stop_list[i])

        # Propagate changes in LDT forward and backward from predecessors and successors of S
        # Backward
        for i in range(index_S - 1, -1, -1):
            try:
                self.stop_list[i].set_LDT()
            except IndexError as e:
                print(e)
                print(f"Index: {i}")
                print(f"List: {self.stop_list}")
        # Forward
        # for i in range(index_S, len(self.stop_list)):
        #     set_LDT(self.stop_list[i])

        # Update cost
        self.compute_cost()

    def compute_dispatching(self):
        """
        Set arrival and departure times to all stops in the Itinerary according to the defined dispatching strategy
        """
        for S in self.stop_list:
            S.set_arrival_departure()

    def update_time_windows(self):
        """
        Updates the time window of each stop in the Itinerary, together with its traveled_km and cost.
        This method must be executed after an insertion/removal of one or many stop.
        """
        for S in self.stop_list:
            S.set_leg_time()
            S.set_EAT()
            S.set_LDT()
            S.set_slack()
            S.set_arrival_departure()
        self.compute_traveled_km()
        self.compute_cost()

    def compute_traveled_km(self):
        """
        Returns the amount of traveled kilometers by the vehicle following the Itinerary
        """
        self.traveled_km = sum(self.db.get_route_distance_km(
            self.stop_list[i].id, self.stop_list[i + 1].id) for i in range(len(self.stop_list) - 1))
        return self.traveled_km

    def compute_cost(self):
        """
        Returns the cost of the Itinerary
        """
        # self.cost = sum(self.db.get_route_time_min(
        #     self.stop_list[i].id, self.stop_list[i + 1].id) for i in range(len(self.stop_list) - 1))
        # return self.cost
        self.cost = self.compute_traveled_km()
        return self.cost

    def compute_busy_time(self):
        """
        Total time spent by the vehicle following this Itinerary traveling between stops or servicing passengers
        """
        total_time = self.end_time - self.start_time
        traveling_time = None
        try:
            traveling_time = sum(x.leg_time for x in self.stop_list)
        except TypeError:
            print("TypeError computing busy time of itinerary {}".format(self.vehicle_id))
            print(self.stop_list)
        servicing_time = sum(x.service_time for x in self.stop_list)
        waiting_time = sum((x.departure_time - x.arrival_time - x.service_time) for x in self.stop_list
                           if x.departure_time < math.inf)
        return total_time, (traveling_time + servicing_time), waiting_time

    ################################################
    ######## Visualisation & Debug methods #########
    ################################################

    def to_string(self):
        customer_waitings = []
        s = "Vehicle with ID {} has {} stops scheduled\n".format(self.vehicle_id, len(self.stop_list))
        s += "\tDeparture from stop {} at time {:.2f}\n".format(self.start_stop.id, self.start_stop.departure_time)
        if len(self.stop_list) > 2:
            for i in range(1, len(self.stop_list) - 1):
                cust_wait = None
                # if the number of customers increases in a stop, it is a pick-up stop

                if (self.stop_list[i].npass - self.stop_list[i - 1].npass) > 0:
                    # compute waiting time of the passengers as start_time minus arrival time
                    cust_wait = self.stop_list[i].arrival_time - self.stop_list[i].start_time
                s += "\t--> stop {:3d}, npass {} -> {}, {}, [{:3.2f}, {:3.2f}] (arr, dep), {:3.2f} min, {:3.2f} min" \
                    .format(int(self.stop_list[i].id), self.stop_list[i - 1].npass, self.stop_list[i].npass,
                            # self.stop_list[i - 1].npres, self.stop_list[i].npres,
                            self.stop_list[i].passenger_id,
                            self.stop_list[i].arrival_time, self.stop_list[i].departure_time,
                            self.stop_list[i].departure_time - self.stop_list[i].arrival_time,
                            # time spent waiting at the stop
                            self.stop_list[i].departure_time - self.stop_list[i].arrival_time
                            - self.stop_list[i].service_time)
                if cust_wait is not None:
                    s += ", customers waited {:3.2f} min \n".format(cust_wait)
                    customer_waitings.append(cust_wait)
                else:
                    # print("cust_wait it {} because current npass is {} and prev npass is {}".format(cust_wait,
                    #                                                                                 self.stop_list[i].npass,
                    #                                                                                 self.stop_list[i-1].npass))
                    s += "\n"
        s += "\tEnd in stop {} at time {:.2f}\n".format(self.end_stop.id, self.end_stop.arrival_time)
        s += "\tVehicle currently at stop {}\n".format(self.current_loc.id)
        tot, busy, wait = self.compute_busy_time()
        s += "\tBusy time: {:.2f} ({:.2f}%), Waiting time: {:.2f} ({:.2f}%), Busy+Wait: {:.2f}%\n" \
            .format(busy, (busy / tot) * 100, wait, (wait / tot) * 100, ((busy + wait) / tot) * 100)
        s += "Itinerary km: {:.2f}, cost: {:.2f}\n".format(self.traveled_km, self.cost)
        self.customer_waitings = customer_waitings
        customer_waitings = numpy.array(customer_waitings)
        s += "Total customers: {}, total waiting: {:.2f} min, avg: {:.2f} min, stdev: {:.2f} min\n".format(
            len(customer_waitings), numpy.sum(customer_waitings), numpy.average(customer_waitings),
            numpy.std(customer_waitings))
        return s

    def to_string_simple(self):
        s = "Itinerary {}: {}\n\twith a cost increment {:.2f}".format(
            self.vehicle_id,
            [x.id for x in self.stop_list], self.cost)
        return s

    def to_string_debug(self):
        s = "Vehicle with ID {} has {} stops scheduled\n".format(self.vehicle_id, len(self.stop_list))
        s += "\tDeparture from stop {} at time {}, EAT {:.2f}, EAT_F {:.2f}, LDT {:.2f}, LDT_F {:.2f}, slack {:.2f}\n" \
            .format(self.start_stop.id, self.start_time, self.start_stop.eat, self.start_stop.eat_f,
                    self.start_stop.ldt, self.start_stop.ldt_f, self.start_stop.slack)
        if len(self.stop_list) > 2:
            for i in range(1, len(self.stop_list) - 1):
                s += "\t--> stop {}, npass {}, EAT {:.2f}, EAT_F {:.2f}, LDT {:.2f}, LDT_F {:.2f}, slack {:.2f}\n" \
                    .format(self.stop_list[i].id, self.stop_list[i].npass, self.stop_list[i].eat,
                            self.stop_list[i].eat_f, self.stop_list[i].ldt, self.stop_list[i].ldt_f,
                            self.stop_list[i].slack)
        s += "\tEnd in stop {} at time {}, EAT {:.2f}, EAT_F {:.2f}, LDT {:.2f}, LDT_F {:.2f}, slack {:.2f}\n" \
            .format(self.end_stop.id, self.end_time, self.end_stop.eat, self.end_stop.eat_f,
                    self.end_stop.ldt, self.end_stop.ldt_f, self.end_stop.slack)
        s += "\tVehicle currently at stop {}\n".format(self.current_loc.id)
        s += "Itinerary km: {:.2f}, cost: {:.2f}\n".format(self.traveled_km, self.cost)
        return s

    ################################################
    ######### Solution evaluation methods ##########
    ################################################

    def customer_stats(self):
        customer_dict = {}
        if len(self.stop_list) > 2:
            for i in range(1, len(self.stop_list) - 1):
                stop = self.stop_list[i]
                customer = stop.passenger_id
                # waiting time
                # if the number of customers increases in a stop, it is a pick-up stop
                if (self.stop_list[i].npass - self.stop_list[i - 1].npass) > 0:
                    # compute waiting time of the passengers as start_time minus arrival time
                    cust_wait = self.stop_list[i].arrival_time - self.stop_list[i].start_time
                    customer_dict[customer] = {'wait': cust_wait, 'on-board': None, 'trip_kms': None, 'min_kms': None}
        for customer in customer_dict.keys():
            # on-board time
            # get indexes of Spu and Ssd of customer
            indices = [i for i, x in enumerate(self.stop_list) if x.passenger_id == customer]
            if len(indices) < 2 or len(indices) > 2:
                print(f"Error computing customer_stats for itinerary {self.vehicle_id}: Customer {customer} "
                      f"appears in {len(indices)} stops, indices: {indices}")
                exit()
            # arrival_time to Spu + service_time = time instant in which customer is inside vehicle
            # arrival_time to Ssd + service_time = time instant in which customer leaves the vehicles
            Spu = self.stop_list[indices[0]]
            Ssd = self.stop_list[indices[1]]
            pickup_time = Spu.arrival_time + Spu.service_time
            dropoff_time = Ssd.arrival_time + Ssd.service_time
            on_board_time = dropoff_time - pickup_time
            if pickup_time > dropoff_time:
                print(f"Error computing customer_stats for itinerary {self.vehicle_id}: Customer {customer} "
                      f"has inconsistent pickup: {pickup_time:.2f} and dropoff: {dropoff_time:.2f} times. "
                      f"On-board: {on_board_time:.2f}")
                exit()
            customer_dict[customer]['on-board'] = on_board_time

            # trip_kms
            trip_stops = self.stop_list[indices[0]:indices[1] + 1]
            if len(trip_stops) < 2:
                print(f"Error computing customer_stats for itinerary {self.vehicle_id}: Customer {customer} "
                      f"has inconsistent trip length: {len(trip_stops)}")
                exit()

            trip_kms = sum(self.db.get_route_distance_km(
                trip_stops[i].id, trip_stops[i + 1].id) for i in range(len(trip_stops) - 1))
            customer_dict[customer]['trip_kms'] = trip_kms

            min_kms = self.db.get_route_distance_km(trip_stops[0].id, trip_stops[-1].id)
            customer_dict[customer]['min_kms'] = min_kms

        self.customer_dict = customer_dict
        return customer_dict

    def vehicle_stats(self):
        # number of stops
        vehicle_dict = {'num_stops': len(self.stop_list)}
        # beginning and ending time
        begin_time = self.start_stop.departure_time
        end_time = self.end_stop.arrival_time
        vehicle_dict['begin_time'] = begin_time
        vehicle_dict['end_time'] = end_time
        # busy time and percentage, waiting time and percentage, usage percentage
        total_time, busy_time, wait_time = self.compute_busy_time()
        vehicle_dict['total_time'] = total_time
        vehicle_dict['busy_time'] = busy_time
        vehicle_dict['wait_time'] = wait_time
        busy_percent = (busy_time / total_time) * 100
        wait_percent = (wait_time / total_time) * 100
        usage_percent = ((busy_time + wait_time) / total_time) * 100
        vehicle_dict['busy_percent'] = busy_percent
        vehicle_dict['wait_percent'] = wait_percent
        vehicle_dict['usage_percent'] = usage_percent
        # itinerary_kms and cost
        vehicle_dict['itinerary_kms'] = self.traveled_km
        vehicle_dict['cost'] = self.cost

        # Itinerary customer stats
        customer_dict = self.customer_dict
        if len(self.customer_dict) == 0:
            customer_dict = self.customer_stats()
        vehicle_dict['total_requests'] = len(customer_dict.keys())
        vehicle_dict['total_wait'] = 0
        vehicle_dict['avg_wait'] = 0
        vehicle_dict['std_wait'] = 0
        if vehicle_dict['total_requests'] > 0:
            customer_waitings = [x['wait'] for x in customer_dict.values()]
            vehicle_dict['total_wait'] = sum(customer_waitings)
            vehicle_dict['avg_wait'] = vehicle_dict['total_wait'] / vehicle_dict['total_requests']
            vehicle_dict['std_wait'] = np.std(customer_waitings)

        self.vehicle_dict = vehicle_dict
        return vehicle_dict

    ################################################
    ####### Methods currently in development #######
    ################################################

    def check_duplicated_stops(self):
        """
        TODO: Checks whether the Itinerary contains two or more subsequent visits to the same stop
        This may occur when scheduling two requests with the same origin or destination stop
        """
        while self.merge_stops():
            pass
        # Update cost
        self.compute_traveled_km()
        self.compute_cost()
        return

    def merge_stops(self, verbose=0):  #
        """
        Merges subsequent stops with the same ID into a single stop, updating its attributes accordingly
        TODO Ensure the time windows of both stops are compatible
        """
        for i in range(len(self.stop_list) - 1):
            if self.stop_list[i].id == self.stop_list[i + 1].id and self.stop_list[i].leg_time == 0:
                if verbose > 0:
                    print(
                        "Stops in indexes {} and {} have the same ID ({})\n".format(i, i + 1, self.stop_list[i].id))
                    print("Stop list: {}\n".format([x.id for x in self.stop_list]))
                    print(self.stop_list[i].to_string())
                    print(self.stop_list[i + 1].to_string())
                # Get duplicated stop
                S1 = self.stop_list[i]
                S2 = self.stop_list[i + 1]
                # Get sprev and snext
                R = self.stop_list[i].sprev
                T = self.stop_list[i + 1].snext
                # Remove duplicated from stop list
                self.stop_list = self.stop_list[:i] + self.stop_list[i + 2:]
                if verbose > 0:
                    print("Duplicated stop removed: {}".format([x.id for x in self.stop_list]))
                # Create merged stop S
                S = new_stop_from_stop(S1)
                # Add service time
                S.service_time = S1.service_time + S2.service_time
                # The number of passengers on departure from S will be the same as those of S2
                S.npass = S2.npass
                S.npres = S2.npres
                # Keep the most restrictive time window
                S.start_time = max(S1.start_time, S2.start_time)
                S.end_time = min(S1.end_time, S2.end_time)
                # Connect stop to the itinerary
                R.snext = S
                T.sprev = S
                S.sprev = R
                S.snext = T
                S.leg_time = S2.leg_time
                # Set EAT and LDF
                S.latest = S.end_time - S.service_time
                S.set_EAT()
                S.set_LDT()
                # Insert S in stop_list
                self.stop_list.insert(i, S)
                if verbose > 0:
                    print("New merge stop:\n")
                    print(S.to_string())
                    print("New stop list: {}\n".format([x.id for x in self.stop_list]))
                return True
        return False
