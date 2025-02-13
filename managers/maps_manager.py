import googlemaps
from datetime import datetime
from dotenv import load_dotenv
import os
import re
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class MapsManager:
    def __init__(self):
        load_dotenv()  # Ensure environment variables are loaded
        self.client = googlemaps.Client(key=os.getenv("GOOGLE_MAPS_API_KEY"))
        self.base_rate_per_mile = 1.50
        self.move_size_rates = {
            "studio": 0.80 * 400,        # e.g., 320
            "1-bedroom": 0.80 * 800,     # e.g., 640
            "2-bedroom": 0.80 * 1200,    # e.g., 960
            "3-bedroom": 0.80 * 1600,    # e.g., 1280
            "4-bedroom": 0.80 * 2000,    # e.g., 1600
            "office": 0.80 * 2500,       # e.g., 2000
            "car": 0.80 * 150            # e.g., 120
        }
        # Base additional service costs for a 1-bedroom move.
        self.base_additional_costs = {
            "packing": 150,
            "storage": 100
        }
        self.seasonality_rate = 0.10  # 10% increase during peak seasons
        self.rural_location_rate = 0.10  # 10% increase for rural locations

    def calculate_distance(self, origin, destination):
        """Calculate the driving distance between two locations."""
        try:
            result = self.client.distance_matrix(origins=[origin], destinations=[destination], mode="driving")
            if result['rows'][0]['elements'][0]['status'] == 'OK':
                # Convert distance from meters to miles (1 mile ≈ 1609.34 meters)
                distance = result['rows'][0]['elements'][0]['distance']['value'] / 1609.34
                logger.debug(f"Calculated distance between {origin} and {destination}: {distance} miles")
                return round(distance, 2)
            else:
                logger.error(f"Distance Matrix API Error: {result['rows'][0]['elements'][0]['status']}")
                return None
        except Exception as e:
            logger.error(f"Error calculating distance: {e}")
            return None

    def standardize_move_size(self, move_size):
        """
        Standardizes the move_size input to match the keys in move_size_rates.
        Acceptable examples: '1 bedroom', '1-bed apartment', '1 bed', etc.
        """
        try:
            move_size = move_size.lower().strip()
            # Capture a number followed by variations of 'bed' or 'bedroom' optionally with 'apartment'
            match = re.search(r'(\d+)\s*(?:-?\s*(?:bed(?:room)?(?:\s*apartment)?))', move_size)
            if match:
                number = match.group(1)
                standardized = f"{number}-bedroom"
                logger.debug(f"Standardized move_size: {standardized}")
                return standardized
            elif "studio" in move_size:
                return "studio"
            elif "office" in move_size:
                return "office"
            elif "car" in move_size:
                return "car"
            else:
                logger.warning(f"Unknown move_size format: {move_size}")
                return move_size  # Return as is if not recognized
        except Exception as e:
            logger.error(f"Error standardizing move_size '{move_size}': {e}")
            return move_size

    def is_rural_location(self, location):
        """
        Determines if a location is rural. Placeholder for actual implementation.
        """
        # For now, we'll assume all locations are urban.
        return False

    def is_peak_season(self, move_date):
        """
        Determines if the move_date falls within peak moving seasons.
        Placeholder for actual implementation.
        """
        try:
            date_obj = datetime.strptime(move_date, "%Y-%m-%d")
            month = date_obj.month
            # Assuming peak seasons are June, July, August.
            return month in [6, 7, 8]
        except Exception as e:
            logger.error(f"Error determining peak season for date '{move_date}': {e}")
            return False

    def get_additional_services_costs(self, move_size):
        """
        Returns a dict with dynamic additional service costs based on the move_size.
        For example:
          - studio: packing=$100, storage=$80
          - 1-bedroom: packing=$150, storage=$130
          - 2-bedroom: packing=$200, storage=$180, etc.
        For non-bedroom moves (e.g., office, car) the default base_additional_costs are returned.
        """
        standardized = self.standardize_move_size(move_size)
        costs = {}
        if standardized == "studio":
            costs["packing"] = 100
            costs["storage"] = 80
        elif standardized.endswith("-bedroom"):
            try:
                num_bed = int(standardized.split("-")[0])
            except Exception as e:
                num_bed = 1
            costs["packing"] = 150 + (num_bed - 1) * 50
            costs["storage"] = 130 + (num_bed - 1) * 50
        else:
            costs = self.base_additional_costs.copy()
        return costs

    def estimate_cost(self, origin, destination, move_size, additional_services=None, move_date=None):
        """Estimate the cost of the move."""
        distance = self.calculate_distance(origin, destination)
        if distance is None:
            return None, "Error calculating distance."

        standardized_move_size = self.standardize_move_size(move_size)
        move_size_cost = self.move_size_rates.get(standardized_move_size, 0)
        if move_size_cost == 0:
            logger.warning(f"Move size '{standardized_move_size}' not recognized. Defaulting to base rate.")

        # Calculate additional services cost based on move size.
        additional_cost = 0
        if additional_services:
            service_costs = self.get_additional_services_costs(move_size)
            for service in additional_services:
                service_lower = service.lower().strip()
                if service_lower in service_costs:
                    cost = service_costs[service_lower]
                    additional_cost += cost
                    logger.debug(f"Dynamic additional cost for service '{service_lower}': {cost}")
                else:
                    logger.debug(f"Service '{service_lower}' not recognized for additional cost. Skipping.")
        base_cost = distance * self.base_rate_per_mile
        logger.debug(f"Base Cost (Distance): {base_cost}")

        total_cost = base_cost + move_size_cost + additional_cost
        logger.debug(f"Total Cost before multipliers: {total_cost}")

        # Apply seasonality and rural location multipliers
        if move_date:
            if self.is_peak_season(move_date):
                total_cost += total_cost * self.seasonality_rate
                logger.debug(f"Applied seasonality rate: {self.seasonality_rate * 100}%")
            if self.is_rural_location(origin) or self.is_rural_location(destination):
                total_cost += total_cost * self.rural_location_rate
                logger.debug(f"Applied rural location rate: {self.rural_location_rate * 100}%")
        
        # Define a cost range (e.g., ±10% of total_cost)
        min_cost = total_cost * 1.1
        max_cost = total_cost * 1.4

        logger.debug(f"Estimated Cost Range: ${round(min_cost, 2)} - ${round(max_cost, 2)}")
        return distance, (round(min_cost, 2), round(max_cost, 2))
