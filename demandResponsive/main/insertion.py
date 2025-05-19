class Insertion:
    """
    Insertion object. Represents a feasible assigment of a customer request to a vehicle itinerary.
    An insertion is defined by:
        # itinerary to which the trip is going to be inserted
        # trip (customer request data) to be inserted
        # index_Spu. Position within the itinerary where the trip's origin stop is going to be inserted
        # index_Ssd. Position within the itinerary where the trip's destination stop is going to be inserted
        # cost_increment. Net additional cost derived from implementing the insertion
    """
    def __init__(self, itinerary, trip, index_Spu, index_Ssd, cost_increment):
        self.I = itinerary
        self.t = trip
        self.index_Spu = index_Spu
        self.index_Ssd = index_Ssd
        self.cost_increment = cost_increment

    def to_string(self):
        return "Insert\n\tPickup stop {} in position {}\n\tSetdown stop {} in position {}\n\tof " \
               "itinerary {}: {}\n\twith a cost increment of {:.2f}".format(
                self.t.origin_id, self.index_Spu, self.t.destination_id, self.index_Ssd, self.I.vehicle_id,
                [x.id for x in self.I.stop_list], self.cost_increment)

    def to_string_simple(self):
        return "Insert\n\tPickup stop {} in position {}\n\tSetdown stop {} in position {}\n\tof " \
               "itinerary {}\n\twith a cost increment of {:.2f}".format(
                self.t.origin_id, self.index_Spu, self.t.destination_id, self.index_Ssd, self.I.vehicle_id,
                self.cost_increment)
