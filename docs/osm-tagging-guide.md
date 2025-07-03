# OSM Tagging Guide for MCP Server

## Overview

This guide explains how to use the OSM Edit MCP Server's advanced tagging capabilities. The server supports both traditional tag-based operations and natural language processing for intuitive map editing.

## Core Tagging Concepts

### OSM Tag Structure
OpenStreetMap uses key-value pairs called tags to describe map features:
- **Key**: The property type (e.g., `amenity`, `shop`, `highway`)
- **Value**: The specific value (e.g., `restaurant`, `bakery`, `residential`)

Example: `amenity=restaurant` means "this is a restaurant amenity"

### Primary Feature Tags
The main tag that defines what a feature is:

#### Amenities (`amenity=*`)
```
amenity=restaurant     # Restaurant/dining
amenity=cafe          # Coffee shop or casual cafe
amenity=fast_food     # Fast food restaurant
amenity=pub           # Pub or bar
amenity=school        # Educational institution
amenity=hospital      # Medical facility
amenity=bank          # Financial institution
amenity=fuel          # Gas/petrol station
amenity=parking       # Parking area
amenity=pharmacy      # Pharmacy/chemist
```

#### Shops (`shop=*`)
```
shop=supermarket      # Large grocery store
shop=convenience      # Small convenience store
shop=bakery          # Bakery
shop=clothes         # Clothing store
shop=electronics     # Electronics store
shop=hairdresser     # Hair salon
shop=bicycle         # Bicycle shop
shop=books           # Bookstore
```

#### Buildings (`building=*`)
```
building=yes         # Generic building
building=house       # Residential house
building=apartments  # Apartment building
building=commercial  # Commercial building
building=office      # Office building
building=retail      # Retail building
building=industrial  # Industrial building
```

#### Roads (`highway=*`)
```
highway=primary      # Major road
highway=secondary    # Secondary road
highway=residential  # Residential street
highway=footway      # Pedestrian path
highway=cycleway     # Bicycle path
highway=path         # General path
```

### Common Secondary Tags

#### Contact Information
```
name=Business Name           # Official name
phone=+1-555-123-4567       # Phone number
website=https://example.com  # Website URL
email=info@example.com      # Email address
```

#### Accessibility
```
wheelchair=yes       # Wheelchair accessible
wheelchair=no        # Not wheelchair accessible
wheelchair=limited   # Limited accessibility
```

#### Operating Hours
```
opening_hours=Mo-Fr 09:00-17:00    # Monday to Friday, 9 AM to 5 PM
opening_hours=24/7                 # Open 24 hours
opening_hours=Mo-Su 08:00-22:00    # Monday to Sunday, 8 AM to 10 PM
```

#### Services and Features
```
wifi=yes            # WiFi available
wifi=no             # No WiFi
outdoor_seating=yes # Has outdoor seating
takeaway=yes        # Offers takeaway
delivery=yes        # Offers delivery
payment:cash=yes    # Accepts cash
payment:cards=yes   # Accepts cards
```

#### Cuisine Types (for restaurants/cafes)
```
cuisine=italian     # Italian cuisine
cuisine=chinese     # Chinese cuisine
cuisine=pizza       # Pizza
cuisine=burger      # Burgers
cuisine=coffee_shop # Coffee shop
cuisine=ice_cream   # Ice cream
```

## Natural Language Processing

### How It Works
The MCP server can understand natural language descriptions and convert them to proper OSM tags.

### Natural Language Examples

#### Restaurants and Food
| Natural Language | Generated Tags |
|-----------------|----------------|
| "Italian restaurant with outdoor seating" | `amenity=restaurant`, `cuisine=italian`, `outdoor_seating=yes` |
| "Coffee shop with WiFi" | `amenity=cafe`, `cuisine=coffee_shop`, `wifi=yes` |
| "Pizza place that delivers" | `amenity=restaurant`, `cuisine=pizza`, `delivery=yes` |
| "Fast food burger joint" | `amenity=fast_food`, `cuisine=burger` |
| "Ice cream shop" | `amenity=ice_cream`, `cuisine=ice_cream` |
| "Bakery that opens early" | `shop=bakery`, `opening_hours=Mo-Su 06:00-18:00` |

#### Services and Facilities
| Natural Language | Generated Tags |
|-----------------|----------------|
| "Elementary school with wheelchair access" | `amenity=school`, `school=elementary`, `wheelchair=yes` |
| "Hospital with emergency room" | `amenity=hospital`, `emergency=yes` |
| "Gas station with convenience store" | `amenity=fuel`, `shop=convenience` |
| "Bank with ATM" | `amenity=bank`, `atm=yes` |
| "Pharmacy open 24 hours" | `amenity=pharmacy`, `opening_hours=24/7` |
| "Public parking garage" | `amenity=parking`, `parking=multi-storey`, `access=public` |

#### Shops and Retail
| Natural Language | Generated Tags |
|-----------------|----------------|
| "Clothing store for women" | `shop=clothes`, `clothes=women` |
| "Bicycle repair shop" | `shop=bicycle`, `service:bicycle:repair=yes` |
| "Bookstore with cafe" | `shop=books`, `amenity=cafe` |
| "Electronics store" | `shop=electronics` |
| "Hair salon for men and women" | `shop=hairdresser`, `male=yes`, `female=yes` |
| "Grocery store open late" | `shop=supermarket`, `opening_hours=Mo-Su 06:00-24:00` |

#### Recreation and Entertainment
| Natural Language | Generated Tags |
|-----------------|----------------|
| "Public park with playground" | `leisure=park`, `playground=yes` |
| "Movie theater" | `amenity=cinema` |
| "Gym with swimming pool" | `leisure=fitness_centre`, `sport=swimming` |
| "Library with computer access" | `amenity=library`, `internet_access=yes` |
| "Sports bar with big screens" | `amenity=bar`, `sport=yes` |

### Using Natural Language with MCP Tools

#### 1. `parse_natural_language_tags`
Convert descriptions to tags for review:
```python
# Input: "Mexican restaurant with patio and live music"
# Output: {
#   "amenity": "restaurant",
#   "cuisine": "mexican",
#   "outdoor_seating": "yes",
#   "live_music": "yes"
# }
```

#### 2. `create_feature_with_natural_language`
Create complete features from descriptions:
```python
# Input: "Coffee shop with WiFi and outdoor seating"
# Creates node with proper coordinates and tags
# Validates all tags before creation
# Provides confirmation step for safety
```

#### 3. `explain_tags`
Convert tags back to natural language:
```python
# Input: {"amenity": "restaurant", "cuisine": "italian", "outdoor_seating": "yes"}
# Output: "This is a restaurant serving italian cuisine with outdoor seating"
```

## Tag Validation and Standards

### Validation Levels
- **ERROR**: Invalid or incorrect tags that will prevent creation
- **WARNING**: Deprecated or non-standard tags that should be reviewed
- **INFO**: Suggestions for additional tags

### Common Validation Rules

#### Coordinate Validation
- Latitude: -90.0 to +90.0
- Longitude: -180.0 to +180.0

#### Tag Key Rules
- Must use lowercase letters, numbers, underscores, colons
- No spaces or special characters (except : and _)
- Maximum 255 characters

#### Tag Value Rules
- Can contain any UTF-8 characters
- Maximum 255 characters
- Should follow established conventions

#### Required Tag Combinations
Some features require multiple tags:
```
# Schools should have education level
amenity=school + school=primary|secondary|elementary

# Restaurants should have cuisine type
amenity=restaurant + cuisine=*

# Shops should have specific shop type
shop=yes → should use shop=supermarket, shop=clothes, etc.
```

### Deprecated Tags
The system will warn about deprecated tags and suggest alternatives:
```
shop=fishmonger → shop=seafood
amenity=emergency_phone → emergency=phone
highway=unsurfaced → highway=track + surface=unpaved
```

## Common Tagging Patterns

### Complete Restaurant Example
```json
{
  "amenity": "restaurant",
  "name": "Bella Vista Italian",
  "cuisine": "italian",
  "outdoor_seating": "yes",
  "wheelchair": "yes",
  "opening_hours": "Mo-Su 11:00-22:00",
  "phone": "+1-555-123-4567",
  "website": "https://bellavista.example.com",
  "payment:cash": "yes",
  "payment:cards": "yes",
  "wifi": "yes"
}
```

### Complete Store Example
```json
{
  "shop": "supermarket",
  "name": "FreshMart Grocery",
  "opening_hours": "Mo-Su 06:00-23:00",
  "wheelchair": "yes",
  "parking": "yes",
  "wifi": "customers",
  "payment:cash": "yes",
  "payment:cards": "yes",
  "website": "https://freshmart.example.com"
}
```

### Complete School Example
```json
{
  "amenity": "school",
  "name": "Lincoln Elementary School",
  "school": "elementary",
  "grades": "K-5",
  "wheelchair": "yes",
  "website": "https://lincoln.school.edu",
  "phone": "+1-555-987-6543"
}
```

## Advanced Tagging Features

### Batch Operations
The MCP server supports batch tagging operations for efficiency:

```python
operations = [
  {
    "type": "add_tags",
    "element_id": 12345,
    "element_type": "node",
    "tags": {"amenity": "restaurant", "cuisine": "italian"}
  },
  {
    "type": "modify_tags",
    "element_id": 67890,
    "element_type": "way",
    "tags": {"name": "Updated Name"},
    "remove_keys": ["old_tag"]
  }
]
```

### Tag Conflict Resolution
When updating existing elements, the system:
1. Compares existing tags with new tags
2. Identifies conflicts and overlaps
3. Suggests resolution strategies
4. Requires user confirmation for changes

### Tag Suggestions
The system provides intelligent tag suggestions based on:
- Similar features in the area
- Common tag combinations
- OSM best practices
- User's editing history

## Best Practices

### 1. Start with Primary Tags
Always begin with the main feature tag:
- `amenity=*` for facilities and services
- `shop=*` for retail establishments
- `highway=*` for roads and paths
- `building=*` for structures

### 2. Add Descriptive Tags
Include relevant details:
- Name of the business/feature
- Contact information when available
- Accessibility information
- Operating hours

### 3. Use Standard Values
Follow established OSM conventions:
- Check existing tags before creating new ones
- Use lowercase values when possible
- Follow regional tagging practices

### 4. Validate Before Creating
Always use the validation tools:
- `validate_tags()` to check standards compliance
- Review warnings and suggestions
- Test with `dry_run=true` for batch operations

### 5. Document Your Changes
Provide clear changeset comments:
- "Added Italian restaurant with outdoor seating"
- "Updated store hours and contact information"
- "Added accessibility tags to school"

## Error Handling and Troubleshooting

### Common Errors

#### Invalid Coordinates
```
Error: Latitude 95.0 is outside valid range (-90, 90)
Solution: Check coordinate values and correct
```

#### Missing Required Tags
```
Error: amenity=restaurant missing cuisine tag
Solution: Add cuisine=* tag to specify food type
```

#### Deprecated Tags
```
Warning: shop=fishmonger is deprecated, use shop=seafood
Solution: Update to modern tag standard
```

#### Tag Conflicts
```
Warning: Both amenity=restaurant and shop=bakery present
Solution: Choose primary feature type
```

### Validation Workflow
1. Use `parse_natural_language_tags()` to generate initial tags
2. Review suggestions and warnings
3. Use `validate_tags()` to check compliance
4. Fix any errors or deprecated tags
5. Create feature with validated tags

## Integration with MCP

### Using with AI Assistants
The MCP server is designed to work seamlessly with AI assistants:

1. **Natural Input**: Users can describe features in plain English
2. **Smart Conversion**: System converts to proper OSM tags
3. **Validation**: Automatic checking against OSM standards
4. **Confirmation**: Safety checks before modifying live data
5. **Explanation**: Convert technical tags back to readable descriptions

### Example Conversation Flow
```
User: "Add a Mexican restaurant with patio dining"
AI: Using parse_natural_language_tags...
   Suggested tags: amenity=restaurant, cuisine=mexican, outdoor_seating=yes
   Validation: All tags valid ✓
   Would you like me to create this feature?

User: "Yes, and add that it has WiFi"
AI: Adding wifi=yes tag...
   Creating feature with all validated tags...
   ⚠️ This will modify live OSM data. Confirm?

User: "Confirmed"
AI: Feature created successfully!
   Created: Mexican restaurant with patio dining and WiFi
```

## Reference Links

- [OSM Wiki - Map Features](https://wiki.openstreetmap.org/wiki/Map_Features)
- [OSM Wiki - Tagging Guidelines](https://wiki.openstreetmap.org/wiki/Good_practice)
- [TagInfo - Tag Usage Statistics](https://taginfo.openstreetmap.org/)
- [OSM Wiki - Key Lists](https://wiki.openstreetmap.org/wiki/Category:Keys)
- [iD Editor Presets](https://github.com/openstreetmap/id-tagging-schema)

## Appendix: Complete Tag Reference

### All Supported Primary Tags

#### Amenities
- restaurant, cafe, fast_food, food_court, pub, bar, biergarten
- school, university, college, library, hospital, clinic, pharmacy
- bank, atm, post_office, police, fire_station, courthouse
- place_of_worship, fuel, parking, toilets, telephone, emergency_phone
- cinema, theatre, nightclub, casino, brothel, studio
- recycling, waste_disposal, marketplace, vending_machine

#### Shops
- supermarket, convenience, department_store, mall, kiosk
- clothes, shoes, jewelry, watches, bags, sports
- electronics, mobile_phone, computer, hifi, camera
- books, stationery, newsagent, music, video, games
- bakery, butcher, seafood, greengrocer, alcohol, beverages
- hairdresser, beauty, chemist, medical_supply, optician
- bicycle, car, car_repair, tyres, fuel, car_wash
- furniture, interior_decoration, bed, kitchen, bathroom_furnishing
- florist, garden_centre, pet, gift, toys, art

#### Highway Types
- motorway, trunk, primary, secondary, tertiary, unclassified, residential
- service, track, path, footway, cycleway, bridleway, steps
- pedestrian, living_street, bus_guideway, raceway

#### Building Types
- yes, house, apartments, detached, semidetached_house, terrace
- commercial, retail, office, industrial, warehouse, kiosk
- hotel, dormitory, hospital, school, university, public
- church, mosque, temple, synagogue, shrine, civic, government
- train_station, transportation, service, garage, garages, parking

This comprehensive guide provides everything needed to effectively use the OSM Edit MCP Server's advanced tagging capabilities.