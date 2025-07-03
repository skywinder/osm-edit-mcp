"""
OSM Tag Management System

This module provides comprehensive OSM tag validation, natural language processing,
and tag standard management capabilities for the OSM Edit MCP server.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Set
import re
from datetime import datetime
import asyncio
import aiofiles

logger = logging.getLogger(__name__)

class OSMTagManager:
    """Manages OSM tag standards, validation, and natural language processing."""

    def __init__(self, data_file: Optional[str] = None):
        """Initialize the tag manager.

        Args:
            data_file: Path to the OSM tag standards JSON file
        """
        self.data_file = data_file or str(Path(__file__).parent.parent.parent / "data" / "osm_tag_standards.json")
        self.tag_standards = None
        self.primary_tags = {}
        self.natural_language_mappings = {}
        self.tag_descriptions = {}
        self.common_combinations = {}
        self.metadata = {}
        self._loaded = False

    async def load_standards(self) -> bool:
        """Load tag standards from JSON file."""
        try:
            if Path(self.data_file).exists():
                async with aiofiles.open(self.data_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    data = json.loads(content)

                    self.metadata = data.get("metadata", {})
                    self.tag_standards = data.get("tag_standards", {})
                    self.primary_tags = self.tag_standards.get("primary_tags", {})
                    self.natural_language_mappings = self.tag_standards.get("natural_language_mappings", {})
                    self.tag_descriptions = self.tag_standards.get("tag_descriptions", {})
                    self.common_combinations = self.tag_standards.get("common_combinations", {})

                    self._loaded = True
                    logger.info(f"Loaded tag standards from {self.data_file}")
                    return True
            else:
                logger.warning(f"Tag standards file not found: {self.data_file}")
                self._load_fallback_standards()
                return False
        except Exception as e:
            logger.error(f"Error loading tag standards: {e}")
            self._load_fallback_standards()
            return False

    def _load_fallback_standards(self):
        """Load minimal fallback tag standards if JSON file is not available."""
        logger.info("Loading fallback tag standards...")

        self.primary_tags = {
            "amenity": [
                {"value": "restaurant", "count": 0, "description": "Place to eat"},
                {"value": "cafe", "count": 0, "description": "Coffee shop"},
                {"value": "school", "count": 0, "description": "Educational institution"},
                {"value": "hospital", "count": 0, "description": "Medical facility"},
                {"value": "pharmacy", "count": 0, "description": "Pharmacy"},
                {"value": "bank", "count": 0, "description": "Bank"},
                {"value": "fuel", "count": 0, "description": "Gas station"},
                {"value": "parking", "count": 0, "description": "Parking area"},
            ],
            "shop": [
                {"value": "supermarket", "count": 0, "description": "Large food store"},
                {"value": "convenience", "count": 0, "description": "Convenience store"},
                {"value": "bakery", "count": 0, "description": "Bakery"},
                {"value": "clothes", "count": 0, "description": "Clothing store"},
                {"value": "electronics", "count": 0, "description": "Electronics store"},
            ],
            "tourism": [
                {"value": "hotel", "count": 0, "description": "Hotel"},
                {"value": "museum", "count": 0, "description": "Museum"},
                {"value": "attraction", "count": 0, "description": "Tourist attraction"},
                {"value": "information", "count": 0, "description": "Tourist information"},
            ],
            "highway": [
                {"value": "bus_stop", "count": 0, "description": "Bus stop"},
                {"value": "traffic_signals", "count": 0, "description": "Traffic lights"},
                {"value": "crossing", "count": 0, "description": "Pedestrian crossing"},
            ],
            "building": [
                {"value": "house", "count": 0, "description": "House"},
                {"value": "apartments", "count": 0, "description": "Apartment building"},
                {"value": "office", "count": 0, "description": "Office building"},
                {"value": "commercial", "count": 0, "description": "Commercial building"},
            ]
        }

        self.natural_language_mappings = {
            "restaurant": {"amenity": "restaurant"},
            "cafe": {"amenity": "cafe"},
            "coffee shop": {"amenity": "cafe"},
            "school": {"amenity": "school"},
            "hospital": {"amenity": "hospital"},
            "hotel": {"tourism": "hotel"},
            "supermarket": {"shop": "supermarket"},
            "grocery store": {"shop": "supermarket"},
            "bus stop": {"highway": "bus_stop"},
            "parking": {"amenity": "parking"},
        }

        self._loaded = True

    def ensure_loaded(self):
        """Ensure tag standards are loaded."""
        if not self._loaded:
            asyncio.create_task(self.load_standards())

    def get_tag_suggestions(self, key: str, partial_value: str = "") -> List[Dict[str, Any]]:
        """Get tag value suggestions for a given key.

        Args:
            key: OSM tag key (e.g., 'amenity', 'shop')
            partial_value: Partial value to filter suggestions

        Returns:
            List of suggested values with descriptions
        """
        self.ensure_loaded()

        if key not in self.primary_tags:
            return []

        suggestions = []
        partial_lower = partial_value.lower()

        for value_data in self.primary_tags[key]:
            value = value_data.get("value", "")
            description = value_data.get("description", "")

            if not partial_value or partial_lower in value.lower():
                suggestions.append({
                    "value": value,
                    "description": description,
                    "count": value_data.get("count", 0),
                    "popularity": value_data.get("fraction", 0.0)
                })

        # Sort by popularity
        suggestions.sort(key=lambda x: x["count"], reverse=True)
        return suggestions[:20]  # Return top 20 suggestions

    def parse_natural_language(self, text: str) -> Dict[str, str]:
        """Parse natural language description into OSM tags.

        Args:
            text: Natural language description

        Returns:
            Dictionary of OSM tags
        """
        self.ensure_loaded()

        text_lower = text.lower().strip()

        # Direct mapping lookup
        if text_lower in self.natural_language_mappings:
            return self.natural_language_mappings[text_lower]

        # Fuzzy matching for partial matches
        best_match = None
        best_score = 0

        for phrase, tags in self.natural_language_mappings.items():
            # Simple fuzzy matching based on word overlap
            phrase_words = set(phrase.split())
            text_words = set(text_lower.split())

            if phrase_words.issubset(text_words):
                score = len(phrase_words) / len(text_words)
                if score > best_score:
                    best_score = score
                    best_match = tags

        return best_match or {}

    def validate_tags(self, tags: Dict[str, str]) -> Tuple[bool, List[str]]:
        """Validate OSM tags against standards.

        Args:
            tags: Dictionary of OSM tags

        Returns:
            Tuple of (is_valid, list_of_warnings)
        """
        self.ensure_loaded()

        warnings = []
        is_valid = True

        for key, value in tags.items():
            # Check for required tags
            if key in ["name", "amenity", "shop", "tourism", "highway", "building"]:
                if not value or value.strip() == "":
                    warnings.append(f"Empty value for important tag '{key}'")
                    is_valid = False

            # Check against known values
            if key in self.primary_tags:
                known_values = [v["value"] for v in self.primary_tags[key]]
                if value not in known_values:
                    warnings.append(f"Unknown value '{value}' for key '{key}'. Consider: {', '.join(known_values[:5])}")

            # Validate specific formats
            if key == "opening_hours":
                if not self._validate_opening_hours(value):
                    warnings.append(f"Invalid opening hours format: '{value}'")

            elif key == "phone":
                if not self._validate_phone(value):
                    warnings.append(f"Invalid phone number format: '{value}'")

            elif key == "website":
                if not self._validate_url(value):
                    warnings.append(f"Invalid website URL: '{value}'")

        return is_valid, warnings

    def _validate_opening_hours(self, value: str) -> bool:
        """Validate opening hours format."""
        if not value:
            return False

        # Basic validation - should be more comprehensive
        common_patterns = [
            r"^\d{2}:\d{2}-\d{2}:\d{2}$",  # 09:00-17:00
            r"^Mo-Fr \d{2}:\d{2}-\d{2}:\d{2}$",  # Mo-Fr 09:00-17:00
            r"^24/7$",  # 24/7
            r"^closed$",  # closed
        ]

        for pattern in common_patterns:
            if re.match(pattern, value):
                return True

        return False

    def _validate_phone(self, value: str) -> bool:
        """Validate phone number format."""
        if not value:
            return False

        # Basic international phone number validation
        phone_pattern = r"^\+?[\d\s\-\(\)\.]+$"
        return bool(re.match(phone_pattern, value)) and len(value) >= 7

    def _validate_url(self, value: str) -> bool:
        """Validate URL format."""
        if not value:
            return False

        url_pattern = r"^https?://[^\s/$.?#].[^\s]*$"
        return bool(re.match(url_pattern, value))

    def get_tag_combinations(self, primary_tag: Dict[str, str]) -> List[Dict[str, str]]:
        """Get suggested tag combinations for a primary tag.

        Args:
            primary_tag: Primary tag (e.g., {'amenity': 'restaurant'})

        Returns:
            List of suggested additional tags
        """
        self.ensure_loaded()

        combinations = []

        # Get the primary key and value
        if not primary_tag:
            return combinations

        key, value = next(iter(primary_tag.items()))

        # Common combinations for different amenities
        if key == "amenity":
            if value == "restaurant":
                combinations.extend([
                    {"cuisine": ""},
                    {"opening_hours": ""},
                    {"phone": ""},
                    {"website": ""},
                    {"takeaway": "yes"},
                    {"wheelchair": "yes"}
                ])
            elif value == "school":
                combinations.extend([
                    {"school": "primary"},
                    {"grades": ""},
                    {"phone": ""},
                    {"website": ""},
                    {"wheelchair": "yes"}
                ])
            elif value == "hospital":
                combinations.extend([
                    {"emergency": "yes"},
                    {"phone": ""},
                    {"website": ""},
                    {"wheelchair": "yes"}
                ])

        elif key == "shop":
            combinations.extend([
                {"opening_hours": ""},
                {"phone": ""},
                {"website": ""},
                {"wheelchair": "yes"}
            ])

        elif key == "tourism":
            if value == "hotel":
                combinations.extend([
                    {"stars": ""},
                    {"phone": ""},
                    {"website": ""},
                    {"wheelchair": "yes"},
                    {"internet_access": "wlan"}
                ])

        # Always suggest common tags
        combinations.extend([
            {"name": ""},
            {"addr:housenumber": ""},
            {"addr:street": ""},
            {"addr:city": ""},
            {"addr:postcode": ""}
        ])

        return combinations

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the loaded tag standards."""
        self.ensure_loaded()

        total_values = sum(len(values) for values in self.primary_tags.values())

        return {
            "primary_tag_categories": len(self.primary_tags),
            "total_tag_values": total_values,
            "natural_language_mappings": len(self.natural_language_mappings),
            "data_source": self.metadata.get("source", "Unknown"),
            "last_updated": self.metadata.get("created_at", "Unknown"),
            "loaded": self._loaded
        }

    def search_tags(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for tags based on a query.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching tags with metadata
        """
        self.ensure_loaded()

        query_lower = query.lower()
        results = []

        # Search in primary tags
        for key, values in self.primary_tags.items():
            if query_lower in key.lower():
                results.append({
                    "type": "key",
                    "key": key,
                    "description": f"Tag category: {key}",
                    "relevance": 1.0
                })

            for value_data in values:
                value = value_data.get("value", "")
                description = value_data.get("description", "")

                if query_lower in value.lower() or query_lower in description.lower():
                    results.append({
                        "type": "value",
                        "key": key,
                        "value": value,
                        "description": description,
                        "count": value_data.get("count", 0),
                        "relevance": 0.8
                    })

        # Search in natural language mappings
        for phrase, tags in self.natural_language_mappings.items():
            if query_lower in phrase.lower():
                results.append({
                    "type": "natural_language",
                    "phrase": phrase,
                    "tags": tags,
                    "description": f"Natural language: {phrase}",
                    "relevance": 0.6
                })

        # Sort by relevance and count
        results.sort(key=lambda x: (x["relevance"], x.get("count", 0)), reverse=True)

        return results[:limit]

# Global instance
tag_manager = OSMTagManager()

async def initialize_tag_manager():
    """Initialize the global tag manager."""
    await tag_manager.load_standards()

# Convenience functions for backward compatibility
def get_tag_suggestions(key: str, partial_value: str = "") -> List[Dict[str, Any]]:
    """Get tag value suggestions for a given key."""
    return tag_manager.get_tag_suggestions(key, partial_value)

def parse_natural_language(text: str) -> Dict[str, str]:
    """Parse natural language description into OSM tags."""
    return tag_manager.parse_natural_language(text)

def validate_tags(tags: Dict[str, str]) -> Tuple[bool, List[str]]:
    """Validate OSM tags against standards."""
    return tag_manager.validate_tags(tags)

def get_tag_combinations(primary_tag: Dict[str, str]) -> List[Dict[str, str]]:
    """Get suggested tag combinations for a primary tag."""
    return tag_manager.get_tag_combinations(primary_tag)

def search_tags(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search for tags based on a query."""
    return tag_manager.search_tags(query, limit)