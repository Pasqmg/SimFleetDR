import math


class Stop:
    """
    Stop object. A Stop can be part of a trip (in a Request) or of an Itinerary. A Stop object defines the time
    window in which it can be visited and serviced. In addition, it contains the necessary attributes to easily
    check the feasibility of inserting stops in an itinerary.
    """

    # Create a stop that is not part of a trip or itinerary
    def __init__(self, database, stop_id):
        # Database
        self.db = database
        # Stop-independent attributes (stop S)
        self.id = stop_id
        # spatial location of S
        self.coords = self.db.get_stop_coords(stop_id)

        # Trip-dependent attributes
        # start of the time-window of S
        self.start_time = None
        # end of the time-window of S
        self.end_time = None
        # duration of service time at S, normally for loading/unloading passengers
        self.service_time = None
        # latest feasible arrival time at S
        self.latest = None

        # Itinerary-dependent attributes (itinerary I, stop S)
        # predecessor stop in I
        self.sprev = None
        # successor stop in I
        self.snext = None
        # number of passengers on board the vehicle on departure from S
        self.npass = None
        # number of seats reserved on departure from S
        self.npres = None
        # CAPACITY CONSTRAINT: capacity <= npass + npress
        # The number of passengers on board + the number of reserved seats can not exceed the capacity of the
        # vehicle represented by the itinerary to which the stop is assigned
        # travel time on the leg connecting S to its successor T
        self.leg_time = None
        # Earliest arrival time
        self.eat = None
        # Latest departure time
        self.ldt = None
        # Earliest feasible commencement of a service interval at S
        self.eat_f = None
        # Latest feasible termination of a service interval at S
        self.ldt_f = None
        # Slack time
        self.slack = None

        # Dispatching strategy dependent attributes
        self.arrival_time = None
        self.departure_time = None

        # Passenger id (optional)
        self.passenger_id = None

    def create_trip_stop(self, database, stop_id, start_time, end_time, service_time, passenger_id):
        """
        Updates the Stop attributes that define its time window, according to the information defined
        by the trip of the Request to which the S top belongs.
        """
        self.__init__(database, stop_id)
        self.start_time = start_time
        self.end_time = end_time
        self.service_time = service_time
        self.latest = end_time - service_time
        self.passenger_id = passenger_id

    def create_itinerary_stop(self, database, stop_id, start_time, end_time, service_time, passenger_id, sprev, snext,
                              npass, npres, leg_time, eat, ldt, eat_f, ldt_f, slack):
        """
        Updates the necessary Stop attributes for its inclusion in an itinerary. First, the Stop time window is set
        invoking the create_trip_stop function. Then, itinerary-dependent attributes are computed.
        """
        self.create_trip_stop(database, stop_id, start_time, end_time, service_time, passenger_id)
        self.sprev = sprev
        self.snext = snext
        self.npass = npass
        self.npres = npres
        self.leg_time = leg_time
        self.eat = eat
        self.ldt = ldt
        self.eat_f = eat_f
        self.ldt_f = ldt_f
        self.slack = slack

    def set_leg_time(self, value=None):
        """
        Computes the leg time of the Stop; time taken to travel from the current Stop to the
        subsequent Stop in the itinerary (snext)

        Precondition: the Stop is an itinerary stop.
        """
        if value is not None:
            self.leg_time = value
        elif self.snext is None:
            self.leg_time = 0
        else:
            self.leg_time = self.db.get_route_time_min(self.id, self.snext.id)

    def set_EAT(self):
        """
        Compute Earliest Arrival Time (EAT) of the Stop according to its temporal window
        and its previous stop in the itinerary (sprev)
        """
        # For the case of the first stop in an itinerary (vehicle departure)
        if self.sprev is None:
            self.eat = self.eat_f = self.start_time
        else:
            self.eat = max(self.sprev.start_time, self.sprev.eat) + self.sprev.service_time + self.sprev.leg_time
            self.eat_f = max(self.start_time, self.eat)

    def set_LDT(self):
        """
        Compute Latest Departure Time (LDT) of the Stop according to its temporal window
        and its subsequent stop in the itinerary (snext)
        """
        # For the case of the last stop in an itinerary (vehicle destination)
        if self.snext is None:
            self.ldt = self.ldt_f = self.end_time
        else:
            self.ldt = min(self.snext.end_time, self.snext.ldt) - self.snext.service_time - self.leg_time
            self.ldt_f = min(self.end_time, self.ldt)

    def update_EAT(self, verbose=0):
        """
        Updates the Earliest Arrival Time (EAT) of the Stop after another stop is inserted in its itinerary.
        """
        prev_eat = self.eat
        R = self.sprev
        new_eat = max(R.start_time, R.eat) + R.service_time + R.leg_time
        if new_eat != prev_eat:
            self.eat = new_eat
            self.eat_f = max(self.start_time, self.eat)
            # When inserting a stop in an itinerary, EAT may be delayed in subsequent stops
            if new_eat > prev_eat:
                if verbose > 0:
                    print("The EAT of stop {} was delayed in {:.2f} seconds\n"
                          .format(self.id, new_eat - prev_eat))
                return new_eat - prev_eat
            # When removing a stop from an itinerary, EAT may be advanced in subsequent stops
            else:
                if verbose > 0:
                    print("The EAT of stop {} was advanced in {:.2f} seconds\n"
                          .format(self.id, prev_eat - new_eat))
                return prev_eat - new_eat
        return 0

    def update_LDT(self, verbose=0):
        """
        Updates the Latest Departure Time (LDT) of the Stop after another stop is inserted in its itinerary.
        """
        prev_ldt = self.ldt
        T = self.snext
        new_ldt = min(T.end_time, T.ldt) - T.service_time - self.leg_time
        if new_ldt != prev_ldt:
            self.ldt = new_ldt
            self.ldt_f = min(self.end_time, self.ldt)
            # When inserting a stop in an itinerary, LDT may be advanced in previous stops
            if new_ldt < prev_ldt:
                if verbose > 0:
                    print("The LDT of stop {} was advanced in {:.2f} seconds\n"
                          .format(self.id, prev_ldt - new_ldt))
                return prev_ldt - new_ldt
            # When removing a stop in an itinerary, LDT may be delayed in previous stops
            else:
                if verbose > 0:
                    print("The LDT of stop {} was delayed in {:.2f} seconds\n"
                          .format(self.id, new_ldt - prev_ldt))
                return new_ldt - prev_ldt
        return 0

    def set_slack(self):
        """
        Computes and sets the slack time of the Stop. The slack time represents the extra time
        the vehicle visiting the Stop can spend waiting at it.

        The service interval of a stop is computed as [EAT+service_time, LDT]. The slack time
        is therefore the exceeding time of LDT - EAT - service_time.

        The visit to the stop is therefore defined by [EAT, LDT-slack_time].
        """
        self.slack = self.ldt - self.eat - self.service_time
        # if self.slack < 0:
        #     print(f"WARNING :: Negative slack time ({self.slack:.2f}) in stop {self.id}\n"
        #           f"\tLDT: {self.ldt:.2f}, EAT: {self.eat:.2f}, service_time: {self.service_time:.2f}")

    def set_arrival_departure(self):
        """
        Sets the time at which the vehicle visiting the Stop will arrive to it and depart from it.
        These values are computed according to the dispatching strategy.
        """
        if self.sprev is None:
           self.arrival_time = self.start_time
        else:
           self.arrival_time = max(self.start_time + self.sprev.leg_time, self.eat_f)
            #self.arrival_time = self.eat_f
        if self.snext is not None:
            # self.departure_time = self.snext.eat_f - self.leg_time
            self.departure_time = max(self.snext.start_time, self.snext.eat_f - self.leg_time)
        else:
            self.departure_time = math.inf

    def update_time_window(self):
        self.set_leg_time()
        self.set_EAT()
        self.set_LDT()
        self.set_arrival_departure()
        self.set_slack()

    def to_string_trip(self):
        """
        Returns the Stop information as a formatted string
        """
        s = "Stop with ID {} located at ({:.2f}, {:.2f})\n".format(self.id, self.coords[0], self.coords[1])
        s += "\t Time window\n\t\t start_time: {:.2f}\n".format(self.start_time)  # start_time_window
        s += "\t\t latest: {:.2f}, end_time: {:.2f}\n".format(self.latest, self.end_time)  # latest, end_time
        return s

    def to_string(self):
        """
        Returns the Stop information as a formatted string
        """
        s = "Stop with ID {} located at ({:.2f}, {:.2f})\n".format(self.id, self.coords[0], self.coords[1])
        try:
            s += "\t prev stop {}\n".format(self.sprev.id)
        except AttributeError:
            s += "\t prev stop {}\n".format(None)
        try:
            if self.snext is not None:
                s += "\t next stop {}, with leg time {:.2f}\n".format(self.snext.id, self.leg_time)
            else:
                s += f"\t next stop None, with leg time {self.leg_time:.2f}\n"
        except Exception:
            s += f"\t next stop None, with leg time {self.leg_time:.2f}\n"
        s += "\t Time window\n\t\t start_time: {:.2f}\n".format(self.start_time)  # start_time_window
        s += "\t\t EAT: {:.2f}, EAT_F: {:.2f}\n".format(self.eat, self.eat_f)  # eat, eat_f
        s += "\t\t LDT: {:.2f}, LDT_F: {:.2f}\n".format(self.ldt, self.ldt_f)  # ldt, ldt_f
        s += "\t\t slack: {:.2f}\n".format(self.slack)  # slack
        s += "\t\t latest: {:.2f}, end_time: {:.2f}\n".format(self.latest, self.end_time)  # latest, end_time
        s += "\t Arrival at {:.2f}, departure at {:.2f}\n".format(self.arrival_time, self.departure_time)
        s += "\t Capacity\n\t\t Passengers on board on departure from here: {}".format(self.npass)
        s += "\t Number of seats reserved on departure from here: {}\n".format(self.npres)
        return s
