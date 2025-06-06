from simfleet.demandResponsive.main.utils import get_service_time
from simfleet.demandResponsive.main.globals import MAXIMUM_WAITING_TIME_MINUTES
from simfleet.demandResponsive.main.stop import Stop


class Request:
    """
    Request object. A request represents the transportation demand of a specific customer. A request defines
    a trip of a number of passengers between and origin and a destination stop, that must be completed
    according to a defined time window. A request will be assigned to a vehicle only if it is ensured its
    temporal constraints can be preserved.
    A Request it defined by:
        # passenger_id identifying the issuing customer
        # npass or number of passengers travelling together
        # trip:
            - displacement from an origin stop to a destination stop
            - to be performed within a time window, defined by:
                -- origin stop time window
                -- destination stop time window
        # itinerary/vehicle to which it is assigned (initially None)
    """

    def __init__(self, database, passenger_id, origin_id, destination_id, origin_time_ini, origin_time_end,
                 destination_time_ini, destination_time_end, npass=1):
        # Database
        self.db = database
        # Passenger id
        self.passenger_id = passenger_id
        # Pickup stop
        self.origin_id = origin_id
        self.Spu = Stop(self.db, origin_id)
        self.Spu.passenger_id = passenger_id
        # Setdown stop
        self.destination_id = destination_id
        self.Ssd = Stop(self.db, destination_id)
        self.Ssd.passenger_id = passenger_id
        # Pickup time-window
        self.origin_time_ini = origin_time_ini
        self.origin_time_end = origin_time_end
        # Setdown time-window
        self.destination_time_ini = destination_time_ini
        self.destination_time_end = destination_time_end
        # Number of passengers travelling together for trip t
        self.npass = npass
        # Itinerary to which the trip is currently assigned
        self.itinerary = None
        # Time taken to pickup/setdown passengers
        self.service_time = get_service_time(npass)

        self.create_pickup_stop()  # <-- ES POSSIBLE QUE NO TINGA SENTIT CALCULAR ESTES COSES FINS QUE
        self.create_setdown_stop()  # <-- LES PARADES ESTIGUEN SENT CONSIDERADES A UN ITINERARI CONCRET

    def create_pickup_stop(self):
        """
        Given the Request attributes, computes the necessary attributes to add the time
        window to the trip pickup stop (self.Spu)
        """
        # Compute pickup time window end according to maximum waiting time
        Spu_end_time = self.origin_time_ini + self.service_time + MAXIMUM_WAITING_TIME_MINUTES
        # If the user defined a pickup end time, keep the minimum
        if self.origin_time_end is not None:
            Spu_end_time = min(self.origin_time_end, Spu_end_time)
        # Update pickup time window end
        self.origin_time_end = Spu_end_time
        # Create trip stop
        self.Spu.create_trip_stop(database=self.db, stop_id=self.origin_id, start_time=self.origin_time_ini,
                                  end_time=self.origin_time_end, service_time=self.service_time,
                                  passenger_id=self.passenger_id)

    def create_setdown_stop(self):
        """
        Given the Request attributes, computes the necessary attributes to add the time
        window to the trip setdown stop (self.Ssd)
        """
        # Compute setdown time window end according to maximum waiting time, travel factor and direct trip time
        # Ssd_end_time = self.origin_time_ini + self.service_time + MAXIMUM_WAITING_TIME_MINUTES \
        #               + TRAVEL_FACTOR * self.db.get_route_time_min(self.origin_id,
        #                                                            self.destination_id) + self.service_time
        # If the user defined a setdown end time, keep the minimum
        if self.destination_time_end is not None:
            Ssd_end_time = self.destination_time_end #min(self.destination_time_end, Ssd_end_time)
        self.destination_time_end = Ssd_end_time
        # Create trip stop
        self.Ssd.create_trip_stop(database=self.db, stop_id=self.destination_id, start_time=self.destination_time_ini,
                                  end_time=self.destination_time_end, service_time=self.service_time,
                                  passenger_id=self.passenger_id)

    def to_string(self):
        """
        Prints the information of a request through the standard output
        """
        if self.npass > 1:
            s = "{} passengers ".format(self.npass)
        else:
            s = "{} passenger ".format(self.npass)
        s += "with ID {} requests\n\tpickup at stop {} during [{:.2f}-{:.2f}]\n" \
             "\tsetdown at stop {} during [{:.2f}-{:.2f}]\n".format(self.passenger_id, self.origin_id,
                                                                    self.origin_time_ini, self.origin_time_end,
                                                                    self.destination_id, self.destination_time_ini,
                                                                    self.destination_time_end)
        if self.itinerary is not None:
            s += "Request will be served by vehicle {}\n".format(self.itinerary.vehicle_id)
        else:
            s += "Request is pending assignment\n"
        return s
