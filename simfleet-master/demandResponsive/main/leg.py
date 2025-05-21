class Leg:
    """
    Leg of an itinerary. Specifies the itinerary to which it belongs, the stops it connects, and the served customer.
    """

    def __init__(self, itinerary, origin_stop, dest_stop, passenger_id, time_cost, dist_cost, prev=None, next=None):
        # Itinerary in whose stop_list the Leg is stored
        self.itinerary = itinerary
        # Stop the vehicle departed from in the current Leg
        self.origin_stop = origin_stop
        # Stop the vehicle will arrive to in the current Leg
        self.dest_stop = dest_stop
        # Customer whose request motivated the Leg's displacement
        self.passenger_id = passenger_id
        # Temporal cost of the Leg
        self.time_cost = time_cost
        # Distance cost of the Leg (to be reduced)
        self.dist_cost = dist_cost

        # Times of the leg
        self.departure_from_origin = origin_stop.departure_time
        self.arrival_to_dest = self.departure_from_origin + self.time_cost

        # Previous and next legs in the itinerary's stop list
        self.prev = prev
        self.next = next

    def set_prev(self, prev):
        self.prev = prev

    def set_next(self, next):
        self.next = next

    def __str__(self):
        if self.dest_stop is not None:
            return (f"{self.itinerary} :: "
                    f"leg ({int(self.origin_stop.id):3d}, {self.departure_from_origin:3.2f}) --> "
                    f"({int(self.dest_stop.id):3d}, {self.arrival_to_dest:3.2f}), {self.time_cost:3.2f}min, "
                    f"{self.dist_cost:3.2f}km, {self.passenger_id}")
        else:
            return (f"{self.itinerary} :: "
                    f"leg ({int(self.origin_stop.id):3d}, {self.departure_from_origin:3.2f}) --> "
                    f"(None, {self.arrival_to_dest:3.2f}), {self.time_cost:3.2f}, {self.time_cost:3.2f}min, "
                    f"{self.dist_cost:3.2f}km, {self.passenger_id}")
