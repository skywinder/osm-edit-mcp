#!/usr/bin/env python3
"""
Script to fetch OSM tag standards from TagInfo API and save to JSON file.
This replaces the hardcoded tag standards in server.py with dynamic data.
"""

import json
import asyncio
import aiohttp
import logging
from pathlib import Path
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# TagInfo API endpoints
TAGINFO_API_BASE = "https://taginfo.openstreetmap.org/api/4"
DATA_DIR = Path(__file__).parent.parent / "data"

class OSMTagFetcher:
    """Fetches OSM tag data from TagInfo API."""

    def __init__(self):
        self.session = None
        self.tag_standards = {
            "primary_tags": {},
            "natural_language_mappings": {},
            "tag_descriptions": {},
            "common_combinations": {}
        }

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch_key_values(self, key: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch most common values for a given OSM key."""
        url = f"{TAGINFO_API_BASE}/key/values"
        params = {
            "key": key,
            "filter": "all",
            "lang": "en",
            "sortname": "count",
            "sortorder": "desc",
            "page": 1,
            "rp": limit
        }

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", [])
                else:
                    logger.warning(f"Failed to fetch values for key '{key}': {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching values for key '{key}': {e}")
            return []

    async def fetch_key_info(self, key: str) -> Dict[str, Any]:
        """Fetch general information about an OSM key."""
        url = f"{TAGINFO_API_BASE}/key/stats"
        params = {"key": key}

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", [])
                else:
                    logger.warning(f"Failed to fetch info for key '{key}': {response.status}")
                    return {}
        except Exception as e:
            logger.error(f"Error fetching info for key '{key}': {e}")
            return {}

    async def fetch_popular_keys(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch most popular OSM keys."""
        url = f"{TAGINFO_API_BASE}/keys/all"
        params = {
            "filter": "all",
            "lang": "en",
            "sortname": "count",
            "sortorder": "desc",
            "page": 1,
            "rp": limit
        }

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", [])
                else:
                    logger.warning(f"Failed to fetch popular keys: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching popular keys: {e}")
            return []

    async def build_tag_standards(self):
        """Build comprehensive tag standards from TagInfo API."""
        logger.info("Fetching popular OSM keys...")

        # Key categories we're interested in
        important_keys = [
            "amenity", "shop", "tourism", "highway", "building", "natural",
            "landuse", "leisure", "man_made", "office", "craft", "public_transport",
            "barrier", "power", "railway", "waterway", "place", "addr:housenumber",
            "name", "opening_hours", "phone", "website", "cuisine", "religion"
        ]

        for key in important_keys:
            logger.info(f"Fetching values for key: {key}")
            values = await self.fetch_key_values(key, limit=100)

            if values:
                self.tag_standards["primary_tags"][key] = []
                for value_data in values:
                    value_info = {
                        "value": value_data.get("value", ""),
                        "count": value_data.get("count", 0),
                        "description": value_data.get("description", ""),
                        "fraction": value_data.get("fraction", 0.0)
                    }
                    self.tag_standards["primary_tags"][key].append(value_info)

            # Small delay to be respectful to the API
            await asyncio.sleep(0.1)

        # Build natural language mappings
        self.build_natural_language_mappings()

        logger.info("Tag standards built successfully!")

    def build_natural_language_mappings(self):
        """Build natural language to OSM tag mappings."""
        mappings = {
            # Food and dining
            "restaurant": {"amenity": "restaurant"},
            "cafe": {"amenity": "cafe"},
            "bar": {"amenity": "bar"},
            "pub": {"amenity": "pub"},
            "fast food": {"amenity": "fast_food"},
            "bakery": {"shop": "bakery"},
            "supermarket": {"shop": "supermarket"},
            "grocery store": {"shop": "supermarket"},
            "convenience store": {"shop": "convenience"},

            # Accommodation
            "hotel": {"tourism": "hotel"},
            "motel": {"tourism": "motel"},
            "hostel": {"tourism": "hostel"},
            "guest house": {"tourism": "guest_house"},
            "camping": {"tourism": "camp_site"},
            "campsite": {"tourism": "camp_site"},

            # Transportation
            "bus stop": {"highway": "bus_stop"},
            "train station": {"railway": "station"},
            "subway station": {"railway": "station", "station": "subway"},
            "airport": {"aeroway": "aerodrome"},
            "parking": {"amenity": "parking"},
            "gas station": {"amenity": "fuel"},
            "petrol station": {"amenity": "fuel"},

            # Healthcare
            "hospital": {"amenity": "hospital"},
            "doctor": {"amenity": "doctors"},
            "pharmacy": {"amenity": "pharmacy"},
            "dentist": {"amenity": "dentist"},
            "veterinarian": {"amenity": "veterinary"},

            # Education
            "school": {"amenity": "school"},
            "university": {"amenity": "university"},
            "college": {"amenity": "college"},
            "kindergarten": {"amenity": "kindergarten"},
            "library": {"amenity": "library"},

            # Shopping
            "mall": {"shop": "mall"},
            "shopping center": {"shop": "mall"},
            "clothing store": {"shop": "clothes"},
            "bookstore": {"shop": "books"},
            "electronics store": {"shop": "electronics"},
            "hardware store": {"shop": "doityourself"},

            # Entertainment
            "cinema": {"amenity": "cinema"},
            "theater": {"amenity": "theatre"},
            "museum": {"tourism": "museum"},
            "zoo": {"tourism": "zoo"},
            "park": {"leisure": "park"},

            # Services
            "bank": {"amenity": "bank"},
            "atm": {"amenity": "atm"},
            "post office": {"amenity": "post_office"},
            "police station": {"amenity": "police"},
            "fire station": {"amenity": "fire_station"},

            # Buildings
            "house": {"building": "house"},
            "apartment": {"building": "apartments"},
            "office building": {"building": "office"},
            "commercial building": {"building": "commercial"},
            "warehouse": {"building": "warehouse"},
            "garage": {"building": "garage"},

            # Natural features
            "forest": {"natural": "forest"},
            "lake": {"natural": "water", "water": "lake"},
            "river": {"waterway": "river"},
            "mountain": {"natural": "peak"},
            "beach": {"natural": "beach"},
            "park": {"leisure": "park"},

            # Common phrases
            "place to eat": {"amenity": "restaurant"},
            "place to stay": {"tourism": "hotel"},
            "place to shop": {"shop": "supermarket"},
            "place to park": {"amenity": "parking"},
            "place to study": {"amenity": "library"},
            "place to exercise": {"leisure": "fitness_centre"},
            "place to worship": {"amenity": "place_of_worship"},

            # Activity-based
            "get coffee": {"amenity": "cafe"},
            "buy groceries": {"shop": "supermarket"},
            "fill up gas": {"amenity": "fuel"},
            "see a movie": {"amenity": "cinema"},
            "catch a bus": {"highway": "bus_stop"},
            "take the train": {"railway": "station"},
            "get money": {"amenity": "atm"},
            "send mail": {"amenity": "post_office"},
        }

        self.tag_standards["natural_language_mappings"] = mappings

    def save_to_file(self, filename: str = "osm_tag_standards.json"):
        """Save tag standards to JSON file."""
        DATA_DIR.mkdir(exist_ok=True)
        filepath = DATA_DIR / filename

        # Add metadata
        output_data = {
            "metadata": {
                "source": "TagInfo API",
                "created_at": asyncio.get_event_loop().time(),
                "description": "OSM tag standards fetched from TagInfo API"
            },
            "tag_standards": self.tag_standards
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Tag standards saved to {filepath}")
        return filepath

async def main():
    """Main function to fetch and save OSM tag standards."""
    logger.info("Starting OSM tag standards update...")

    async with OSMTagFetcher() as fetcher:
        await fetcher.build_tag_standards()
        filepath = fetcher.save_to_file()

        # Print summary
        primary_tags = fetcher.tag_standards["primary_tags"]
        natural_mappings = fetcher.tag_standards["natural_language_mappings"]

        logger.info(f"Summary:")
        logger.info(f"  - Primary tag categories: {len(primary_tags)}")
        logger.info(f"  - Natural language mappings: {len(natural_mappings)}")
        logger.info(f"  - Total tag values: {sum(len(values) for values in primary_tags.values())}")
        logger.info(f"  - File saved to: {filepath}")

if __name__ == "__main__":
    asyncio.run(main())