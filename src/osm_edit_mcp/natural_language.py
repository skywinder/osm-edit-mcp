"""Pure natural-language parsing and OSM tag mapping.

This module has no MCP or network dependencies, so parsing can be reused and
tested independently from tool execution.
"""

from typing import Any, Dict, List

BUSINESS_TYPES = {
    # Food & Drink
    'restaurant': {'amenity': 'restaurant'},
    'cafe': {'amenity': 'cafe'},
    'coffee shop': {'amenity': 'cafe'},
    'bar': {'amenity': 'bar'},
    'pub': {'amenity': 'pub'},
    'fast food': {'amenity': 'fast_food'},
    'food court': {'amenity': 'food_court'},
    'ice cream': {'amenity': 'ice_cream'},
    'bakery': {'shop': 'bakery'},
    'pizzeria': {'amenity': 'restaurant', 'cuisine': 'pizza'},
    'deli': {'shop': 'deli'},

    # Accommodation
    'hotel': {'tourism': 'hotel'},
    'motel': {'tourism': 'motel'},
    'hostel': {'tourism': 'hostel'},
    'guesthouse': {'tourism': 'guest_house'},
    'bed and breakfast': {'tourism': 'guest_house'},
    'b&b': {'tourism': 'guest_house'},

    # Healthcare
    'hospital': {'amenity': 'hospital'},
    'pharmacy': {'amenity': 'pharmacy'},
    'dentist': {'amenity': 'dentist'},
    'veterinary': {'amenity': 'veterinary'},
    'clinic': {'amenity': 'clinic'},
    'doctor': {'amenity': 'doctors'},

    # Education
    'school': {'amenity': 'school'},
    'university': {'amenity': 'university'},
    'college': {'amenity': 'college'},
    'library': {'amenity': 'library'},
    'kindergarten': {'amenity': 'kindergarten'},

    # Financial
    'bank': {'amenity': 'bank'},
    'atm': {'amenity': 'atm'},
    'bureau de change': {'amenity': 'bureau_de_change'},
    'credit union': {'amenity': 'bank'},

    # Transportation
    'gas station': {'amenity': 'fuel'},
    'petrol station': {'amenity': 'fuel'},
    'parking': {'amenity': 'parking'},
    'parking lot': {'amenity': 'parking'},
    'taxi': {'amenity': 'taxi'},
    'bus station': {'amenity': 'bus_station'},
    'bus stop': {'highway': 'bus_stop'},
    'train station': {'railway': 'station'},
    'subway station': {'railway': 'station', 'station': 'subway'},

    # Shopping
    'supermarket': {'shop': 'supermarket'},
    'convenience store': {'shop': 'convenience'},
    'clothing store': {'shop': 'clothes'},
    'bookstore': {'shop': 'books'},
    'electronics store': {'shop': 'electronics'},
    'grocery store': {'shop': 'supermarket'},
    'mall': {'shop': 'mall'},
    'shopping center': {'shop': 'mall'},

    # Entertainment
    'cinema': {'amenity': 'cinema'},
    'theater': {'amenity': 'theatre'},
    'museum': {'tourism': 'museum'},
    'park': {'leisure': 'park'},
    'playground': {'leisure': 'playground'},
    'gym': {'leisure': 'fitness_centre'},
    'fitness center': {'leisure': 'fitness_centre'},

    # Services
    'post office': {'amenity': 'post_office'},
    'police station': {'amenity': 'police'},
    'fire station': {'amenity': 'fire_station'},
    'town hall': {'amenity': 'townhall'},
    'courthouse': {'amenity': 'courthouse'},
    'embassy': {'amenity': 'embassy'},

    # Religious
    'church': {'amenity': 'place_of_worship', 'religion': 'christian'},
    'mosque': {'amenity': 'place_of_worship', 'religion': 'muslim'},
    'synagogue': {'amenity': 'place_of_worship', 'religion': 'jewish'},
    'temple': {'amenity': 'place_of_worship'},

    # Tourism
    'tourist attraction': {'tourism': 'attraction'},
    'viewpoint': {'tourism': 'viewpoint'},
    'information': {'tourism': 'information'},
    'monument': {'tourism': 'monument'},
}

# Feature Mappings for Natural Language Processing
FEATURE_MAPPINGS = {
    # Internet & Technology
    'wifi': {'internet_access': 'wlan'},
    'free wifi': {'internet_access': 'wlan', 'internet_access:fee': 'no'},
    'paid wifi': {'internet_access': 'wlan', 'internet_access:fee': 'yes'},
    'no wifi': {'internet_access': 'no'},
    'internet': {'internet_access': 'yes'},

    # Accessibility
    'wheelchair accessible': {'wheelchair': 'yes'},
    'wheelchair limited': {'wheelchair': 'limited'},
    'not wheelchair accessible': {'wheelchair': 'no'},
    'disabled access': {'wheelchair': 'yes'},
    'accessible': {'wheelchair': 'yes'},

    # Seating & Dining
    'outdoor seating': {'outdoor_seating': 'yes'},
    'no outdoor seating': {'outdoor_seating': 'no'},
    'patio': {'outdoor_seating': 'yes'},
    'terrace': {'outdoor_seating': 'yes'},
    'takeaway': {'takeaway': 'yes'},
    'no takeaway': {'takeaway': 'no'},
    'delivery': {'delivery': 'yes'},
    'no delivery': {'delivery': 'no'},
    'reservations': {'reservation': 'yes'},
    'no reservations': {'reservation': 'no'},

    # Services
    'drive through': {'drive_through': 'yes'},
    'drive thru': {'drive_through': 'yes'},
    'no drive through': {'drive_through': 'no'},
    'air conditioning': {'air_conditioning': 'yes'},
    'smoking area': {'smoking': 'separated'},
    'non smoking': {'smoking': 'no'},
    'no smoking': {'smoking': 'no'},
    'cash only': {'payment:cash': 'yes', 'payment:cards': 'no'},
    'cards accepted': {'payment:cards': 'yes'},
    'credit cards': {'payment:cards': 'yes'},

    # Operating Hours
    '24/7': {'opening_hours': '24/7'},
    '24 hours': {'opening_hours': '24/7'},
    'open 24 hours': {'opening_hours': '24/7'},
    'always open': {'opening_hours': '24/7'},

    # Parking
    'parking available': {'parking': 'yes'},
    'no parking': {'parking': 'no'},
    'free parking': {'parking': 'yes', 'parking:fee': 'no'},
    'paid parking': {'parking': 'yes', 'parking:fee': 'yes'},
    'valet parking': {'parking': 'valet'},

    # Family-friendly
    'family friendly': {'family': 'yes'},
    'kids welcome': {'family': 'yes'},
    'pet friendly': {'dog': 'yes'},
    'no pets': {'dog': 'no'},
    'dog friendly': {'dog': 'yes'},
}

# Action verb mappings for natural language processing
ACTION_MAPPINGS = {
    'create': ['add', 'create', 'build', 'establish', 'open', 'put', 'place', 'install', 'set up'],
    'update': ['update', 'change', 'modify', 'edit', 'alter', 'fix', 'adjust', 'revise'],
    'delete': ['delete', 'remove', 'close', 'demolish', 'destroy', 'eliminate', 'take away'],
    'find': ['find', 'search', 'locate', 'show', 'get', 'look for', 'discover']
}

def extract_action_from_text(text: str) -> str:
    """Extract action type from natural language text."""
    text_lower = text.lower()
    for action, verbs in ACTION_MAPPINGS.items():
        if any(verb in text_lower for verb in verbs):
            return action
    return 'find'  # Default action

def map_business_type_to_tags(business_type: str) -> Dict[str, str]:
    """Map business type to OSM tags."""
    business_lower = business_type.lower().strip()
    return BUSINESS_TYPES.get(business_lower, {'amenity': 'unspecified'})

def map_features_to_tags(features: List[str]) -> Dict[str, str]:
    """Map feature descriptions to OSM tags."""
    tags = {}
    for feature in features:
        feature_lower = feature.lower().strip()
        feature_tags = FEATURE_MAPPINGS.get(feature_lower, {})
        tags.update(feature_tags)
    return tags

def parse_natural_language_request(request: str) -> Dict[str, Any]:
    """Parse natural language request into structured data."""
    request_lower = request.lower()

    # Extract action
    action = extract_action_from_text(request)

    # Extract business name (look for quotes or "called" patterns)
    import re
    name_match = re.search(r'(?:called|named)\s+["\']([^"\']+)["\']', request, re.IGNORECASE)
    if not name_match:
        name_match = re.search(r'["\']([^"\']+)["\']', request)

    name = name_match.group(1) if name_match else None

    # Extract coordinates (look for lat/lon patterns)
    coord_match = re.search(r'(?:at|coordinates?)\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)', request, re.IGNORECASE)
    coordinates = None
    if coord_match:
        coordinates = {
            'lat': float(coord_match.group(1)),
            'lon': float(coord_match.group(2))
        }

    # Extract address (look for address patterns)
    address_match = re.search(r'(?:at|address)\s+([^,]+(?:,\s*[^,]+)*)', request, re.IGNORECASE)
    address = address_match.group(1).strip() if address_match else None

    # Extract business type
    business_type = None
    for btype in BUSINESS_TYPES.keys():
        if btype in request_lower:
            business_type = btype
            break

    # Extract features
    features = []
    for feature in FEATURE_MAPPINGS.keys():
        if feature in request_lower:
            features.append(feature)

    # Extract location references
    location_refs = []
    location_patterns = [
        r'(?:near|next to|close to|by)\s+([^,]+)',
        r'(?:in|at)\s+([^,]+)',
        r'(?:on|along)\s+([^,]+)'
    ]

    for pattern in location_patterns:
        matches = re.findall(pattern, request, re.IGNORECASE)
        location_refs.extend(matches)

    return {
        'action': action,
        'name': name,
        'business_type': business_type,
        'features': features,
        'coordinates': coordinates,
        'address': address,
        'location_refs': location_refs,
        'raw_request': request
    }

# Enhanced CRUD Operations

# ---------------------------------------------------------------------------
# Unimplemented write operations.
#

# Enhanced Opening Hours Parser
OPENING_HOURS_PATTERNS = {
    'always_open': ['24/7', '24 hours', 'always open', 'round the clock'],
    'business_hours': ['9am-5pm', '9-5', 'business hours', '9am to 5pm'],
    'extended_hours': ['8am-9pm', '8-9', 'extended hours', '8am to 9pm'],
    'weekdays_only': ['monday-friday', 'weekdays', 'mon-fri', 'weekdays only'],
    'weekends_only': ['saturday-sunday', 'weekends', 'sat-sun', 'weekends only'],
    'closed': ['closed', 'shut', 'not open', 'unavailable']
}

def parse_opening_hours(text: str) -> str:
    """Parse natural language opening hours to OSM format."""
    text_lower = text.lower()

    # Check for specific patterns
    for pattern, phrases in OPENING_HOURS_PATTERNS.items():
        if any(phrase in text_lower for phrase in phrases):
            if pattern == 'always_open':
                return '24/7'
            elif pattern == 'business_hours':
                return 'Mo-Fr 09:00-17:00'
            elif pattern == 'extended_hours':
                return 'Mo-Su 08:00-21:00'
            elif pattern == 'weekdays_only':
                return 'Mo-Fr'
            elif pattern == 'weekends_only':
                return 'Sa-Su'
            elif pattern == 'closed':
                return 'off'

    # Try to parse time patterns (e.g., "9am-5pm")
    import re
    time_pattern = r'(\d{1,2})\s*(?:am|pm)?\s*-\s*(\d{1,2})\s*(?:am|pm)?'
    match = re.search(time_pattern, text_lower)
    if match:
        start, end = match.groups()
        return f'Mo-Su {start.zfill(2)}:00-{end.zfill(2)}:00'

    return text  # Return original if no pattern matches


def parse_address_components(address: str) -> Dict[str, str]:
    """Parse address into components (street, city, state, country, etc.)."""
    components = {}
    address_lower = address.lower()

    # Basic parsing patterns
    import re

    # Extract postal code
    postal_match = re.search(r'\b(\d{5}(?:-\d{4})?)\b', address)
    if postal_match:
        components['postal_code'] = postal_match.group(1)

    # Extract common address keywords
    if 'street' in address_lower or 'st' in address_lower:
        components['type'] = 'street'
    elif 'avenue' in address_lower or 'ave' in address_lower:
        components['type'] = 'avenue'
    elif 'boulevard' in address_lower or 'blvd' in address_lower:
        components['type'] = 'boulevard'

    # Extract numbers
    number_match = re.search(r'^\d+', address)
    if number_match:
        components['house_number'] = number_match.group(0)

    components['raw'] = address
    return components
