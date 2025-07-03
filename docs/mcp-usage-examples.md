# MCP Usage Examples for OSM Edit Server

## Overview

This document provides comprehensive examples of how to use the OSM Edit MCP Server with AI assistants and MCP clients. The server supports natural language processing to make OSM editing intuitive and accessible.

## Getting Started

### 1. Server Setup
```bash
# Install and start the MCP server
uv pip install -e .
python main.py

# The server will be available at the configured endpoint
# Default: Uses stdout for MCP communication
```

### 2. Authentication
Before making any edits, authenticate with OSM:
```python
# The server will handle OAuth flow automatically
# User will be redirected to OSM for authorization
# Tokens are stored securely in system keyring
```

## Natural Language Examples

### Adding Restaurants and Food Places

#### Example 1: Italian Restaurant
```
User: "Add an Italian restaurant with outdoor seating at coordinates 40.7128, -74.0060"

AI: I'll help you add an Italian restaurant. Let me parse that description and create the feature.

Using parse_natural_language_tags:
- Description: "Italian restaurant with outdoor seating"
- Suggested tags: amenity=restaurant, cuisine=italian, outdoor_seating=yes
- Validation: ✓ All tags are valid

Would you like me to create this feature at coordinates 40.7128, -74.0060?

User: "Yes, and add that it has WiFi and accepts credit cards"

AI: Adding additional tags:
- wifi=yes (WiFi available)
- payment:cards=yes (Accepts credit cards)

⚠️ This will create a new node in OpenStreetMap. Confirm creation?

User: "Confirmed"

AI: Feature created successfully!
   Node ID: 123456789
   Tags: amenity=restaurant, cuisine=italian, outdoor_seating=yes, wifi=yes, payment:cards=yes
   Location: 40.7128, -74.0060
```

#### Example 2: Coffee Shop Chain
```
User: "There's a Starbucks coffee shop here that's open 24/7"

AI: I'll create a coffee shop with 24-hour operation.

Tags generated:
- amenity=cafe
- name=Starbucks
- brand=Starbucks
- cuisine=coffee_shop
- opening_hours=24/7

Do you have coordinates for this location?

User: "Yes, 37.7749, -122.4194"

AI: Creating Starbucks coffee shop:
   Location: 37.7749, -122.4194 (San Francisco)
   Operating hours: 24/7

⚠️ Confirm creation in OpenStreetMap?

User: "Yes"

AI: Starbucks created successfully! Node ID: 987654321
```

### Adding Shops and Services

#### Example 3: Grocery Store
```
User: "Add a large grocery store that's wheelchair accessible with parking"

AI: I'll create a grocery store with accessibility features.

Natural language parsing:
- "large grocery store" → shop=supermarket
- "wheelchair accessible" → wheelchair=yes
- "with parking" → parking=yes

Generated tags:
- shop=supermarket
- wheelchair=yes
- parking=yes

Would you like to add:
- Name of the store?
- Operating hours?
- Contact information?

User: "It's called FreshMart and it's open 6 AM to 11 PM daily"

AI: Adding details:
- name=FreshMart
- opening_hours=Mo-Su 06:00-23:00

Ready to create. Please provide coordinates.

User: "40.7589, -73.9851"

AI: Creating FreshMart grocery store at 40.7589, -73.9851
   Features: wheelchair accessible, parking available
   Hours: Daily 6 AM - 11 PM

⚠️ Confirm creation?

User: "Create it"

AI: FreshMart created successfully! Node ID: 456789123
```

#### Example 4: Bicycle Shop with Repairs
```
User: "Add a bike shop that does repairs and rentals"

AI: I'll create a bicycle shop with repair and rental services.

Tags generated:
- shop=bicycle
- service:bicycle:repair=yes
- service:bicycle:rental=yes

Suggestions for additional tags:
- name=? (shop name)
- opening_hours=? (business hours)
- phone=? (contact number)
- website=? (website URL)

User: "It's called City Cycles, open weekdays 9-6, weekends 10-5"

AI: Adding business details:
- name=City Cycles
- opening_hours=Mo-Fr 09:00-18:00; Sa-Su 10:00-17:00

Location coordinates needed.

User: "51.5074, -0.1278"

AI: Creating City Cycles bicycle shop:
   Location: 51.5074, -0.1278 (London)
   Services: repairs and rentals
   Hours: Mon-Fri 9-6, Sat-Sun 10-5

⚠️ Confirm creation in OpenStreetMap?

User: "Yes, create it"

AI: City Cycles created successfully! Node ID: 789123456
```

### Adding Public Services

#### Example 5: Elementary School
```
User: "Add an elementary school with wheelchair access and a playground"

AI: I'll create an elementary school with accessibility and recreational features.

Tags generated:
- amenity=school
- school=elementary
- wheelchair=yes
- playground=yes

Additional recommended tags:
- name=? (school name)
- website=? (school website)
- phone=? (contact number)
- grades=? (grade levels, e.g., "K-5")

User: "Lincoln Elementary, grades K-5, phone 555-123-4567"

AI: Adding school details:
- name=Lincoln Elementary School
- grades=K-5
- phone=+1-555-123-4567

Coordinates needed for placement.

User: "42.3601, -71.0589"

AI: Creating Lincoln Elementary School:
   Location: 42.3601, -71.0589 (Boston area)
   Grade levels: K-5
   Features: wheelchair accessible, playground
   Contact: 555-123-4567

⚠️ This will add a school to OpenStreetMap. Confirm?

User: "Confirmed"

AI: Lincoln Elementary School created! Node ID: 321654987
```

#### Example 6: Hospital with Emergency Services
```
User: "Add a hospital with emergency room and helicopter landing"

AI: I'll create a hospital with emergency services and helicopter access.

Tags generated:
- amenity=hospital
- emergency=yes
- helicopter=yes

Additional suggested tags:
- name=? (hospital name)
- website=? (hospital website)
- phone=? (main number)
- emergency:phone=? (emergency number)

User: "St. Mary's Hospital, emergency line 911"

AI: Adding hospital details:
- name=St. Mary's Hospital
- emergency:phone=911

Location coordinates required.

User: "34.0522, -118.2437"

AI: Creating St. Mary's Hospital:
   Location: 34.0522, -118.2437 (Los Angeles area)
   Services: emergency room, helicopter landing
   Emergency: 911

⚠️ This will add medical facility to OpenStreetMap. Confirm?

User: "Yes"

AI: St. Mary's Hospital created successfully! Node ID: 147258369
```

## Advanced Tagging Operations

### Modifying Existing Features

#### Example 7: Updating Restaurant Information
```
User: "Update the restaurant at node 123456789 to add delivery service and update hours"

AI: I'll update the restaurant with delivery service and new hours.

First, let me get the current tags for node 123456789...

Current tags:
- amenity=restaurant
- cuisine=italian
- outdoor_seating=yes
- wifi=yes
- payment:cards=yes

What are the new operating hours?

User: "Monday to Thursday 11 AM to 10 PM, Friday-Saturday 11 AM to 11 PM, Sunday 12 PM to 9 PM"

AI: Adding updates:
- delivery=yes (delivery service)
- opening_hours=Mo-Th 11:00-22:00; Fr-Sa 11:00-23:00; Su 12:00-21:00

Updated tags preview:
- amenity=restaurant (unchanged)
- cuisine=italian (unchanged)
- outdoor_seating=yes (unchanged)
- wifi=yes (unchanged)
- payment:cards=yes (unchanged)
- delivery=yes (NEW)
- opening_hours=Mo-Th 11:00-22:00; Fr-Sa 11:00-23:00; Su 12:00-21:00 (NEW)

⚠️ This will modify existing OSM data. Confirm changes?

User: "Confirmed"

AI: Restaurant updated successfully!
   Added delivery service and operating hours
   Changes applied to node 123456789
```

#### Example 8: Adding Tags to Multiple Features
```
User: "Add WiFi information to all cafes in the area that don't have it specified"

AI: I'll help you add WiFi tags to cafes. First, let me search for cafes without WiFi tags in the area.

What area should I search? Please provide:
- Bounding box coordinates, or
- Center point and radius, or
- City/neighborhood name

User: "Search within 1km of coordinates 40.7128, -74.0060"

AI: Searching for cafes within 1km of 40.7128, -74.0060...

Found 5 cafes without WiFi tags:
1. Node 111222333 - "Joe's Coffee" (amenity=cafe)
2. Node 444555666 - "Bean There" (amenity=cafe, cuisine=coffee_shop)
3. Node 777888999 - "Morning Brew" (amenity=cafe)
4. Node 123789456 - "Café Central" (amenity=cafe, cuisine=coffee_shop)
5. Node 987654321 - "Starbucks" (amenity=cafe, brand=Starbucks)

For each cafe, what WiFi status should I add?
- wifi=yes (free WiFi available)
- wifi=no (no WiFi)
- wifi=customers (WiFi for customers only)

User: "Add wifi=yes to Joe's Coffee and Bean There, wifi=customers to the others"

AI: Preparing batch tag updates:

Batch 1 - wifi=yes:
- Node 111222333 (Joe's Coffee)
- Node 444555666 (Bean There)

Batch 2 - wifi=customers:
- Node 777888999 (Morning Brew)
- Node 123789456 (Café Central)
- Node 987654321 (Starbucks)

⚠️ This will modify 5 existing features in OpenStreetMap. Confirm batch update?

User: "Proceed"

AI: Batch update completed successfully!
   Updated 5 cafes with WiFi information
   2 with free WiFi, 3 with customer WiFi
```

### Tag Validation and Correction

#### Example 9: Fixing Deprecated Tags
```
User: "Check if the tags on node 987654321 are up to current standards"

AI: I'll validate the tags on node 987654321 against current OSM standards.

Current tags:
- amenity=fuel
- shop=fishmonger
- highway=unsurfaced
- name=Old Gas Station

Validation results:

❌ DEPRECATED: shop=fishmonger
   → Recommended: shop=seafood

❌ DEPRECATED: highway=unsurfaced
   → Recommended: highway=track + surface=unpaved

⚠️ WARNING: Multiple primary features (amenity=fuel + shop=*)
   → Consider separating into multiple features

✅ VALID: amenity=fuel
✅ VALID: name=Old Gas Station

Would you like me to fix the deprecated tags?

User: "Yes, fix the deprecated tags and help resolve the multiple features issue"

AI: I'll fix the deprecated tags and provide options for the multiple features.

Proposed changes:
1. shop=fishmonger → shop=seafood
2. highway=unsurfaced → Remove (not appropriate for fuel station)

For the multiple features conflict:
Option A: Keep as fuel station only (remove shop=seafood)
Option B: Keep as seafood shop only (remove amenity=fuel)
Option C: Split into two separate features

Which option do you prefer?

User: "Option A - it's primarily a gas station"

AI: Applying corrections:
- Remove: shop=fishmonger, highway=unsurfaced
- Keep: amenity=fuel, name=Old Gas Station

Final tags:
- amenity=fuel
- name=Old Gas Station

⚠️ This will remove deprecated tags from node 987654321. Confirm?

User: "Confirmed"

AI: Tags updated successfully!
   Removed deprecated tags, resolved conflicts
   Node 987654321 now follows current OSM standards
```

#### Example 10: Tag Suggestions for Incomplete Features
```
User: "This node only has amenity=restaurant but no other details. Suggest what tags to add."

AI: I'll analyze the restaurant and suggest appropriate additional tags.

Current tags:
- amenity=restaurant

Essential missing tags:
❗ cuisine=* (REQUIRED) - What type of food?

Recommended additional tags:
- name=* (restaurant name)
- opening_hours=* (operating hours)
- phone=* (contact number)
- website=* (restaurant website)

Useful optional tags:
- outdoor_seating=yes/no (patio/terrace dining)
- wheelchair=yes/no/limited (accessibility)
- takeaway=yes/no (takeout available)
- delivery=yes/no (delivery service)
- wifi=yes/no/customers (internet access)
- payment:cash=yes/no (cash accepted)
- payment:cards=yes/no (cards accepted)

What type of restaurant is this?

User: "It's a Thai restaurant called 'Bangkok Garden' with takeout and delivery"

AI: Great! I'll add the essential tags:

Proposed additions:
- cuisine=thai
- name=Bangkok Garden
- takeaway=yes
- delivery=yes

Would you also like to add:
- Operating hours?
- Phone number?
- Accessibility information?
- Payment methods?

User: "Add opening hours: Tuesday-Sunday 5 PM to 10 PM, closed Mondays"

AI: Adding operating hours:
- opening_hours=Tu-Su 17:00-22:00

Complete tag set:
- amenity=restaurant (existing)
- cuisine=thai (NEW)
- name=Bangkok Garden (NEW)
- takeaway=yes (NEW)
- delivery=yes (NEW)
- opening_hours=Tu-Su 17:00-22:00 (NEW)

⚠️ This will add 5 new tags to the restaurant. Confirm?

User: "Add them"

AI: Bangkok Garden restaurant updated successfully!
   Added cuisine, name, services, and hours
   The restaurant listing is now complete
```

## Integration Patterns

### Working with Changesets

#### Example 11: Organized Batch Editing
```
User: "I want to add several businesses on Main Street. Create a changeset for this."

AI: I'll create a changeset for adding Main Street businesses.

Creating changeset:
- Comment: "Adding businesses on Main Street"
- Source: "Local survey"
- Created by: OSM Edit MCP Server

Changeset created: #12345678

Now I can add multiple features to this changeset. What businesses would you like to add?

User: "A bakery, a bookstore, and a coffee shop, all between coordinates 40.7500-40.7600, -74.0000 to -73.9900"

AI: I'll add three businesses to changeset #12345678.

Business 1 - Bakery:
What's the name and exact location?

User: "Miller's Bakery at 40.7520, -74.0050"

AI: Adding Miller's Bakery:
- shop=bakery
- name=Miller's Bakery
- Location: 40.7520, -74.0050

Business 2 - Bookstore:
Name and location?

User: "Chapter & Verse Books at 40.7540, -74.0030"

AI: Adding Chapter & Verse Books:
- shop=books
- name=Chapter & Verse Books
- Location: 40.7540, -74.0030

Business 3 - Coffee Shop:
Name and location?

User: "Corner Café at 40.7560, -74.0010"

AI: Adding Corner Café:
- amenity=cafe
- name=Corner Café
- Location: 40.7560, -74.0010

Summary for changeset #12345678:
1. Miller's Bakery (bakery)
2. Chapter & Verse Books (bookstore)
3. Corner Café (coffee shop)

⚠️ This will add 3 new businesses to OpenStreetMap. Confirm creation?

User: "Create all three"

AI: All businesses created successfully!
   Changeset #12345678 contains:
   - Node 111111111: Miller's Bakery
   - Node 222222222: Chapter & Verse Books
   - Node 333333333: Corner Café

Would you like to close the changeset or add more features?

User: "Close the changeset"

AI: Changeset #12345678 closed successfully.
   Added 3 businesses on Main Street
```

### Error Handling Examples

#### Example 12: Handling Invalid Coordinates
```
User: "Add a restaurant at coordinates 95.0, 200.0"

AI: ❌ Error: Invalid coordinates provided

Issues found:
- Latitude 95.0 is outside valid range (-90.0 to +90.0)
- Longitude 200.0 is outside valid range (-180.0 to +180.0)

Valid coordinate ranges:
- Latitude: -90.0 (South Pole) to +90.0 (North Pole)
- Longitude: -180.0 (antimeridian west) to +180.0 (antimeridian east)

Please provide coordinates within these ranges.

User: "Sorry, I meant 45.0, -122.0"

AI: ✅ Coordinates validated: 45.0, -122.0 (Portland, Oregon area)

Now I can add the restaurant. What type of restaurant is it?

User: "A sushi restaurant"

AI: Creating sushi restaurant:
- amenity=restaurant
- cuisine=sushi
- Location: 45.0, -122.0

⚠️ Confirm creation?

User: "Yes"

AI: Sushi restaurant created successfully! Node ID: 555666777
```

#### Example 13: Handling Tag Conflicts
```
User: "Add these tags to node 123456: amenity=restaurant, shop=supermarket, cuisine=italian"

AI: ⚠️ Tag conflict detected on node 123456

Conflicts found:
- amenity=restaurant + shop=supermarket (multiple primary feature types)

Current analysis:
- amenity=restaurant (restaurant/dining facility)
- shop=supermarket (grocery store)
- cuisine=italian (Italian food)

These represent conflicting business types. Options:

A) Restaurant with grocery section:
   - Keep: amenity=restaurant, cuisine=italian
   - Remove: shop=supermarket
   - Consider adding: shop=deli (if it sells Italian groceries)

B) Grocery store with prepared food:
   - Keep: shop=supermarket
   - Remove: amenity=restaurant
   - Consider adding: prepared_food=yes

C) Separate features:
   - Create two different nodes for restaurant and supermarket

Which option best represents the real-world feature?

User: "It's actually an Italian deli that serves prepared food and sells groceries"

AI: Perfect! That clarifies the feature type.

Recommended tags for Italian deli:
- shop=deli (primary feature)
- cuisine=italian (Italian specialties)
- prepared_food=yes (serves ready-to-eat food)
- name=? (deli name)

This is more accurate than restaurant+supermarket. Shall I apply these tags?

User: "Yes, and the name is 'Nonna's Italian Deli'"

AI: Applying corrected tags:
- shop=deli
- cuisine=italian
- prepared_food=yes
- name=Nonna's Italian Deli

⚠️ This will replace the conflicting tags. Confirm?

User: "Confirmed"

AI: Nonna's Italian Deli tagged successfully!
   Resolved conflicts with appropriate deli classification
```

## Tool Reference Quick Guide

### Core Tools
- `parse_natural_language_tags()` - Convert descriptions to OSM tags
- `create_feature_with_natural_language()` - Create features from descriptions
- `validate_tags()` - Check tags against OSM standards
- `explain_tags()` - Convert tags to human language
- `suggest_additional_tags()` - Recommend complementary tags

### CRUD Operations
- `create_node()` - Create new point features
- `create_way()` - Create new line/area features
- `query_elements()` - Search and retrieve existing features
- `add_tags()` - Add tags to existing features
- `modify_tags()` - Update existing tags
- `remove_tags()` - Remove specific tags

### Advanced Features
- `batch_tag_operations()` - Multiple tag operations at once
- `resolve_tag_conflicts()` - Handle conflicting tags
- `get_tag_documentation()` - Get help for specific tags
- `search_nearby_features()` - Find features in an area

This comprehensive guide shows how to effectively use the OSM Edit MCP Server for natural language map editing with proper validation and safety measures.