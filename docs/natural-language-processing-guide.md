# Natural Language Processing for OSM Editing

## Overview

This guide explains how to use natural language with the OSM Edit MCP Server to describe map features in plain English (or other languages) and have them automatically converted to proper OpenStreetMap tags. The system is designed to make map editing accessible to users without detailed knowledge of OSM tagging conventions.

## Core Concept: Describe What You See

Instead of learning complex tag syntax, users can describe features as they would naturally:

### ✅ Natural Language (Easy)
- "Add a coffee shop with WiFi"
- "There's a grocery store with parking here"
- "Mark this as a residential street"
- "Add a playground that's wheelchair accessible"

### ❌ Traditional Tagging (Complex)
- `amenity=cafe, internet_access=wlan`
- `shop=supermarket, parking=yes`
- `highway=residential`
- `leisure=playground, wheelchair=yes`

## How Natural Language Processing Works

### 1. Input Processing Pipeline

```
User Input → Entity Recognition → Tag Mapping → Validation → Suggestions → OSM Tags
```

#### Example Flow:
```
"Italian restaurant with outdoor seating"
    ↓ Entity Recognition
"restaurant" + "Italian" + "outdoor seating"
    ↓ Tag Mapping
amenity=restaurant + cuisine=italian + outdoor_seating=yes
    ↓ Validation
✅ All tags are valid OSM standards
    ↓ Suggestions
"Would you like to add: opening_hours, wheelchair access, payment methods?"
    ↓ Final Tags
{amenity: restaurant, cuisine: italian, outdoor_seating: yes}
```

### 2. Supported Language Patterns

#### Business Types
```
"coffee shop" → amenity=cafe
"gas station" → amenity=fuel
"grocery store" → shop=supermarket
"fast food restaurant" → amenity=fast_food
"elementary school" → amenity=school, school=elementary
"department store" → shop=department_store
"bike shop" → shop=bicycle
"pizza place" → amenity=restaurant, cuisine=pizza
```

#### Attributes and Features
```
"with WiFi" → wifi=yes OR internet_access=wlan
"wheelchair accessible" → wheelchair=yes
"with parking" → parking=yes
"outdoor seating" → outdoor_seating=yes
"24 hours" OR "24/7" → opening_hours=24/7
"drive-through" → drive_through=yes
"accepts credit cards" → payment:cards=yes
"has playground" → playground=yes
"air conditioned" → air_conditioning=yes
"pet friendly" → dog=yes
```

#### Cuisine and Specialties
```
"Italian restaurant" → amenity=restaurant, cuisine=italian
"Chinese takeout" → amenity=restaurant, cuisine=chinese, takeaway=yes
"burger joint" → amenity=restaurant, cuisine=burger
"coffee and pastries" → amenity=cafe, cuisine=coffee_shop;pastry
"ice cream shop" → shop=ice_cream OR amenity=ice_cream
"bakery" → shop=bakery
```

#### Transportation
```
"bus stop" → highway=bus_stop, public_transport=platform
"bike path" → highway=cycleway
"pedestrian street" → highway=pedestrian
"main road" → highway=primary OR highway=secondary
"residential street" → highway=residential
"parking lot" → amenity=parking
```

### 3. Context-Aware Processing

The system considers multiple factors:

#### Geographic Context
```
Location: "downtown area"
→ Suggests urban amenities, higher building density

Location: "suburban neighborhood"
→ Suggests residential features, single-family homes

Location: "near highway"
→ Suggests transportation-related services (gas, food)
```

#### Temporal Context
```
"late night restaurant" → opening_hours includes late hours
"breakfast place" → opening_hours starts early (6-8 AM)
"weekend market" → opening_hours=Sa-Su only
```

#### Architectural Context
```
"in a shopping mall" → level=1;2;3 (multi-level)
"ground floor shop" → level=0
"rooftop restaurant" → level=roof OR location=rooftop
```

## User Interaction Patterns

### 1. Simple Feature Addition

#### Pattern: "Add a [feature type] [with attributes]"

**User:** "Add a pizza restaurant with delivery"

**AI Processing:**
1. **Parse:** pizza restaurant + delivery
2. **Generate Tags:** amenity=restaurant, cuisine=pizza, delivery=yes
3. **Validate:** ✅ All valid
4. **Suggest:** "Would you like to add opening hours, phone number, or address?"
5. **Ask Location:** "Please provide coordinates or describe the location"

**Complete Interaction:**
```
User: "Add a pizza restaurant with delivery at 40.7128, -74.0060"
AI: I'll create a pizza restaurant with delivery service.

Generated tags:
• amenity=restaurant (Restaurant)
• cuisine=pizza (Pizza restaurant)
• delivery=yes (Offers delivery)

Location: 40.7128, -74.0060 (New York City area)

Additional suggestions:
• opening_hours (Business hours)
• phone (Contact number)
• website (Restaurant website)

⚠️ This will create a new node in OpenStreetMap. Confirm creation?

User: "Yes, and add that it's open until midnight"
AI: Adding opening hours...
• opening_hours=Mo-Su 11:00-00:00 (Open until midnight daily)

Creating pizza restaurant... ✅ Success! Node ID: 123456789
```

### 2. Feature Modification

#### Pattern: "Update/modify [element] to add/change [attributes]"

**User:** "Add WiFi and outdoor seating to the cafe at node 987654321"

**AI Processing:**
1. **Fetch Element:** Get existing tags for node 987654321
2. **Verify Type:** Confirm it's actually a cafe (amenity=cafe)
3. **Generate New Tags:** wifi=yes, outdoor_seating=yes
4. **Merge:** Combine with existing tags
5. **Validate:** Check for conflicts

**Complete Interaction:**
```
User: "Add WiFi and outdoor seating to the cafe at node 987654321"
AI: I'll update the cafe with WiFi and outdoor seating.

Current cafe: "Blue Mountain Coffee" (amenity=cafe, name=Blue Mountain Coffee)

Adding:
• wifi=yes (WiFi available)
• outdoor_seating=yes (Outdoor seating available)

⚠️ This will modify existing OSM data. Confirm update?

User: "Confirm"
AI: Updated successfully! The cafe now includes WiFi and outdoor seating information.
```

### 3. Complex Feature Descriptions

#### Pattern: Multi-attribute descriptions

**User:** "Add a 24-hour gas station with convenience store, car wash, and EV charging"

**AI Processing:**
1. **Primary Feature:** gas station → amenity=fuel
2. **Attributes:**
   - 24-hour → opening_hours=24/7
   - convenience store → shop=convenience
   - car wash → car_wash=yes
   - EV charging → amenity=charging_station (or socket:type2=yes)
3. **Structure Decision:** Multiple features require multiple nodes or relations

**Complete Interaction:**
```
User: "Add a 24-hour gas station with convenience store, car wash, and EV charging"
AI: This is a complex facility with multiple features. I'll create it as a main gas station with additional services.

Main feature (amenity=fuel):
• amenity=fuel (Gas station)
• opening_hours=24/7 (24-hour operation)
• shop=convenience (Convenience store)
• car_wash=yes (Car wash available)
• socket:type2=yes (EV charging available)

Location needed. Please provide coordinates.

User: "42.3601, -71.0589"
AI: Creating 24-hour gas station complex...

⚠️ This will create a new node in OpenStreetMap with multiple services. Confirm?

User: "Yes"
AI: ✅ Created! Node ID: 456789123
Features: Gas station, convenience store, car wash, EV charging
Operating: 24/7
```

## Advanced Natural Language Features

### 1. Ambiguity Resolution

When descriptions are unclear, the AI asks for clarification:

**User:** "Add a bar"

**AI:** "What type of bar did you mean?
- Drinking establishment (amenity=bar)
- Snack bar/counter service (amenity=fast_food, cuisine=snacks)
- Hotel bar (amenity=bar, location=hotel)
- Sports bar (amenity=bar, sport=yes)

Please clarify or provide more details."

### 2. Regional Adaptations

The system adapts to regional terminology:

#### US English:
```
"gas station" → amenity=fuel
"drugstore" → shop=chemist
"crosswalk" → highway=crossing
```

#### UK English:
```
"petrol station" → amenity=fuel
"chemist" → shop=chemist
"zebra crossing" → highway=crossing
```

#### Other Languages:
```
"restaurante" (Spanish) → amenity=restaurant
"boulangerie" (French) → shop=bakery
"apotheke" (German) → shop=pharmacy
```

### 3. Contextual Intelligence

#### Seasonal Context:
```
"Christmas tree lot" → shop=garden_centre, seasonal=christmas_trees
"summer food truck" → amenity=fast_food, mobile=yes
```

#### Cultural Context:
```
"halal restaurant" → amenity=restaurant, diet:halal=yes
"kosher bakery" → shop=bakery, diet:kosher=yes
"vegan cafe" → amenity=cafe, diet:vegan=yes
```

## Validation and Safety

### 1. Automatic Validation

Every natural language input goes through validation:

```
User Input → Tag Generation → OSM Standards Check → Warning/Error Detection
```

#### Validation Results:
- ✅ **Valid:** Standard OSM tags, proceed
- ⚠️ **Warning:** Non-standard but acceptable tags
- ❌ **Error:** Invalid tags, needs correction

### 2. Conflict Detection

**Example:**
```
User: "Add a gas station bakery"
AI: I detected potentially conflicting features:
• amenity=fuel (Gas station)
• shop=bakery (Bakery)

Did you mean:
1. Gas station with bakery inside (amenity=fuel + shop=bakery)
2. Bakery near a gas station (separate features)
3. Something else?

Please clarify.
```

### 3. Completeness Checking

The AI suggests missing essential information:

```
User: "Add a restaurant"
AI: I'll create a restaurant. Basic tags generated:
• amenity=restaurant

Recommended additions:
• cuisine=? (What type of food?)
• name=? (Restaurant name)
• opening_hours=? (Business hours)
• wheelchair=? (Accessibility)

Would you like to add any of these?
```

## Best Practices for Users

### 1. Be Specific but Natural
```
✅ Good: "Italian restaurant with outdoor seating and takeout"
❌ Too vague: "food place"
❌ Too technical: "amenity=restaurant, cuisine=italian"
```

### 2. Include Important Attributes
```
✅ Good: "24-hour pharmacy with drive-through"
✅ Good: "elementary school with playground"
✅ Good: "wheelchair accessible library"
```

### 3. Mention Location Context When Helpful
```
✅ Good: "coffee shop in the university area"
✅ Good: "gas station near the highway"
✅ Good: "corner store in residential neighborhood"
```

### 4. Provide Corrections When Needed
```
User: "Add a coffee shop"
AI: [Creates amenity=cafe]
User: "Actually, it's more of a full restaurant that serves coffee"
AI: "I'll change that to amenity=restaurant with cuisine=coffee_shop"
```

## AI Assistant Guidelines

### 1. Always Confirm Before Creating

**Pattern:**
```
1. Parse natural language
2. Show generated tags with explanations
3. Ask for confirmation
4. Suggest additional relevant tags
5. Request location if not provided
6. Create only after explicit confirmation
```

### 2. Explain Tag Choices

**Example:**
```
AI: "Based on 'coffee shop with WiFi', I generated:
• amenity=cafe (Standard tag for coffee shops)
• internet_access=wlan (WiFi available)

Alternative interpretations:
• cuisine=coffee_shop (If it's primarily a restaurant)
• wifi=yes (Alternative WiFi tag)

Which would you prefer?"
```

### 3. Handle Uncertainty Gracefully

```
User: "Add some kind of food place"
AI: "I need more specifics to choose the right tags:
• Restaurant (full service dining)
• Fast food (quick service)
• Cafe (coffee and light meals)
• Food truck (mobile vendor)
• Deli/takeaway (primarily takeout)

What type of food place is it?"
```

### 4. Educational Approach

Help users learn OSM concepts:

```
AI: "I used 'amenity=cafe' for your coffee shop. In OpenStreetMap:
• amenity=cafe: Coffee shops, light meals
• amenity=restaurant: Full-service dining
• amenity=fast_food: Quick service restaurants

This helps map users find the right type of place!"
```

## Error Handling and Recovery

### 1. Input Parsing Errors

```
User: "Add a qwerty restaurant"
AI: "I didn't recognize 'qwerty' as a food type. Did you mean:
• Quick service restaurant (amenity=fast_food)
• Quality restaurant (amenity=restaurant)
• Something else?

Or could you describe the type of food served?"
```

### 2. Validation Failures

```
User: "Add a swimming pool restaurant"
AI: "I detected potentially conflicting features:
• leisure=swimming_pool (Swimming pool)
• amenity=restaurant (Restaurant)

Did you mean:
1. Restaurant with a swimming pool (amenity=restaurant + swimming_pool=yes)
2. Restaurant near a swimming pool (separate features)
3. Pool-side dining area (amenity=restaurant + location=poolside)

Please clarify the relationship."
```

### 3. Coordinate Validation

```
User: "Add a cafe at 200, 200"
AI: "❌ Those coordinates (200, 200) are invalid:
• Latitude must be between -90 and 90
• Longitude must be between -180 and 180

Please provide valid coordinates or describe the location (e.g., 'near downtown', 'on Main Street')."
```

## Integration Examples

### 1. Voice Input Support

```
User (voice): "Add a Mexican restaurant with a patio"
AI (text): "I heard: 'Mexican restaurant with a patio'
Generated tags:
• amenity=restaurant (Restaurant)
• cuisine=mexican (Mexican food)
• outdoor_seating=yes (Patio/outdoor seating)

Is this correct?"
```

### 2. Image Description Integration

```
User: "I have a photo of a bakery storefront"
AI: "Based on the image, I can see:
• Storefront with bread/pastry displays
• Sign reading 'Fresh Baked Daily'
• Outdoor seating area

Suggested tags:
• shop=bakery
• outdoor_seating=yes
• fresh_food=yes

Would you like me to create this bakery?"
```

### 3. Bulk Operations

```
User: "Add three coffee shops: Starbucks at 40.7128,-74.0060, local cafe at 40.7130,-74.0062, and Dunkin at 40.7125,-74.0065"

AI: "I'll create three coffee shops:

1. Starbucks (40.7128, -74.0060):
   • amenity=cafe, name=Starbucks, brand=Starbucks

2. Local cafe (40.7130, -74.0062):
   • amenity=cafe
   (Need name for local cafe)

3. Dunkin (40.7125, -74.0065):
   • amenity=cafe, name=Dunkin', brand=Dunkin'

⚠️ This will create 3 new nodes. What's the name of the local cafe?"
```

This natural language processing system makes OSM editing accessible to anyone, regardless of their technical knowledge of OpenStreetMap tagging conventions. The AI assistant acts as an intelligent translator between human language and structured OSM data.