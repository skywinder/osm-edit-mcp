# OSM Tag Validation and Checking Guide

## Overview

This guide explains how to validate, check, and verify OSM tags using both the MCP server tools and external OSM resources. Understanding proper tag validation is crucial for maintaining data quality in OpenStreetMap.

## Official OSM Tag Resources

### 1. OSM Wiki - Primary Documentation
**URL**: https://wiki.openstreetmap.org/

The OSM Wiki is the authoritative source for tag documentation:

#### Key Resources:
- **Map Features**: https://wiki.openstreetmap.org/wiki/Map_features
  - Comprehensive list of all standard tags
  - Organized by category (amenities, shops, highways, etc.)
  - Usage guidelines and examples

- **Tag Documentation Pages**:
  - `https://wiki.openstreetmap.org/wiki/Key:{key_name}`
  - `https://wiki.openstreetmap.org/wiki/Tag:{key}={value}`

#### Examples:
```
https://wiki.openstreetmap.org/wiki/Key:amenity
https://wiki.openstreetmap.org/wiki/Tag:amenity=restaurant
https://wiki.openstreetmap.org/wiki/Key:shop
https://wiki.openstreetmap.org/wiki/Tag:highway=residential
```

### 2. Taginfo - Tag Usage Statistics
**URL**: https://taginfo.openstreetmap.org/

Taginfo provides real-world usage statistics for all OSM tags:

#### Features:
- **Tag frequency**: How often tags are used
- **Geographic distribution**: Where tags are popular
- **Combinations**: Which tags are used together
- **Projects**: Which software/presets use specific tags

#### API Access:
```
https://taginfo.openstreetmap.org/api/4/key/values?key=amenity
https://taginfo.openstreetmap.org/api/4/tag/stats?key=amenity&value=restaurant
```

### 3. OSM Presets and Editors
Standard tag combinations used in popular editors:

#### iD Editor Presets:
- **Repository**: https://github.com/openstreetmap/id-tagging-schema
- **Presets**: Standard tag combinations for common features
- **Validation rules**: Built-in validation for tag combinations

#### JOSM Presets:
- **Presets**: XML-based tag definitions
- **Validation**: Advanced validation rules and warnings

## MCP Server Tag Validation Tools

### 1. `validate_tags` - Comprehensive Tag Validation

#### Usage:
```python
# Validate a set of tags
result = await validate_tags({
    "amenity": "restaurant",
    "cuisine": "italian",
    "outdoor_seating": "yes",
    "wheelchair": "yes"
}, element_type="node")
```

#### Response Structure:
```json
{
  "success": true,
  "validation_results": [
    {
      "tag_key": "amenity",
      "tag_value": "restaurant",
      "level": "valid",
      "message": "Valid amenity value",
      "documentation_url": "https://wiki.openstreetmap.org/wiki/Key:amenity"
    },
    {
      "tag_key": "cuisine",
      "tag_value": "italian",
      "level": "valid",
      "message": "Common cuisine type"
    }
  ],
  "overall_status": "valid",
  "warnings": [],
  "errors": []
}
```

#### Validation Levels:
- **VALID**: ✅ Tag is standard and correctly used
- **INFO**: ℹ️ Tag is acceptable but may need context
- **WARNING**: ⚠️ Tag is deprecated or non-standard
- **ERROR**: ❌ Tag is invalid or incorrectly formatted

### 2. `get_tag_documentation` - Official Documentation Lookup

#### Usage:
```python
# Get official documentation for a tag
doc = await get_tag_documentation("amenity", include_examples=True)
```

#### Response:
```json
{
  "success": true,
  "tag_key": "amenity",
  "description": "Amenities and facilities",
  "wiki_url": "https://wiki.openstreetmap.org/wiki/Key:amenity",
  "standard_values": ["restaurant", "cafe", "school", "hospital", ...],
  "examples": [
    {
      "value": "restaurant",
      "description": "A restaurant",
      "wiki_url": "https://wiki.openstreetmap.org/wiki/Tag:amenity=restaurant"
    }
  ],
  "related_tags": ["cuisine", "opening_hours", "wheelchair"],
  "usage_stats": {
    "total_uses": 2841234,
    "most_common_values": ["restaurant", "cafe", "school"]
  }
}
```

### 3. `discover_related_tags` - Find Complementary Tags

#### Usage:
```python
# Find tags that commonly go with restaurants
related = await discover_related_tags({
    "amenity": "restaurant"
}, element_type="node")
```

#### Response:
```json
{
  "success": true,
  "primary_tags": {"amenity": "restaurant"},
  "suggested_tags": [
    {
      "key": "cuisine",
      "confidence": 0.95,
      "reason": "95% of restaurants have cuisine specified",
      "common_values": ["italian", "chinese", "pizza", "burger"]
    },
    {
      "key": "opening_hours",
      "confidence": 0.87,
      "reason": "Operating hours are commonly specified"
    },
    {
      "key": "wheelchair",
      "confidence": 0.73,
      "reason": "Accessibility information is valuable"
    }
  ]
}
```

## Tag Checking Procedures

### 1. Pre-Creation Validation

Before creating any OSM element:

#### Step 1: Validate Core Tags
```python
# Check primary identification tag
await validate_tags({"amenity": "restaurant"})
```

#### Step 2: Validate Tag Combinations
```python
# Check that tags work together logically
await validate_tags({
    "amenity": "restaurant",
    "cuisine": "italian",
    "building": "yes"  # Buildings can contain amenities
})
```

#### Step 3: Check for Missing Essential Tags
```python
# Find recommended additional tags
await discover_related_tags({"amenity": "restaurant"})
```

### 2. Tag Conflict Resolution

When merging or updating tags:

#### Conflict Types:
- **Value Conflicts**: Same key, different values
- **Semantic Conflicts**: Tags that contradict each other
- **Deprecated Tags**: Old tags that should be updated

#### Resolution with `merge_tags`:
```python
result = await merge_tags(
    existing_tags={"amenity": "cafe"},
    new_tags={"amenity": "restaurant"},
    conflict_strategy="ask"  # Prompt user for resolution
)
```

### 3. Batch Validation

For multiple operations:

```python
operations = [
    {
        "type": "create_node",
        "lat": 40.7128,
        "lon": -74.0060,
        "tags": {"amenity": "restaurant", "cuisine": "italian"}
    },
    {
        "type": "add_tags",
        "element_id": 123456,
        "element_type": "node",
        "tags": {"opening_hours": "Mo-Su 11:00-22:00"}
    }
]

# Validate all operations before execution
result = await batch_tag_operations(
    operations=operations,
    dry_run=True  # Test without making changes
)
```

## Natural Language Tag Processing

### Understanding Natural Language Input

The MCP server can process natural language and suggest appropriate tags:

#### 1. `parse_natural_language_tags` - Core NLP Tool

**How it works:**
1. **Entity Recognition**: Identifies features (restaurant, school, shop)
2. **Attribute Extraction**: Finds properties (wheelchair access, WiFi, outdoor seating)
3. **Tag Mapping**: Converts to proper OSM tags
4. **Validation**: Checks against OSM standards
5. **Suggestions**: Recommends additional relevant tags

**Examples:**

| Natural Language | Extracted Entities | Generated Tags |
|------------------|-------------------|----------------|
| "Italian restaurant with patio" | restaurant + italian + patio | `amenity=restaurant`, `cuisine=italian`, `outdoor_seating=yes` |
| "24-hour gas station with convenience store" | gas station + 24-hour + convenience store | `amenity=fuel`, `shop=convenience`, `opening_hours=24/7` |
| "Elementary school with wheelchair access" | school + elementary + wheelchair | `amenity=school`, `school=elementary`, `wheelchair=yes` |
| "Coffee shop with WiFi and takeout" | coffee shop + wifi + takeout | `amenity=cafe`, `cuisine=coffee_shop`, `wifi=yes`, `takeaway=yes` |

#### 2. Context-Aware Processing

The system considers:
- **Element Type**: Node, way, or relation context
- **Geographic Context**: Regional tagging preferences
- **Existing Tags**: Integration with current tags
- **Related Features**: Nearby features that might influence tagging

#### 3. Confidence Scoring

Each suggested tag includes a confidence score:
- **High (0.8-1.0)**: Very likely correct
- **Medium (0.5-0.8)**: Probably correct, review recommended
- **Low (0.0-0.5)**: Possible option, needs verification

### Advanced Natural Language Features

#### Multi-Language Support
```python
# Process descriptions in different languages
await parse_natural_language_tags(
    description="Restaurante italiano con terraza",  # Spanish
    location_context="Spain"
)
# Results in same tags with appropriate name translations
```

#### Contextual Understanding
```python
# Understanding business context
await parse_natural_language_tags(
    description="Corner market that sells beer",
    element_type="node"
)
# Results: shop=convenience + alcohol=yes (not amenity=bar)
```

#### Temporal Context
```python
# Understanding time-based attributes
await parse_natural_language_tags(
    description="Restaurant open late on weekends"
)
# Suggests: opening_hours=Mo-Th 11:00-22:00; Fr-Sa 11:00-24:00; Su 11:00-22:00
```

## Validation Best Practices

### 1. Always Validate Before Creating
- Use `validate_tags` before any creation operation
- Check `discover_related_tags` for completeness
- Verify coordinates are reasonable for the feature type

### 2. Handle Warnings Appropriately
- **INFO**: Generally safe to proceed
- **WARNING**: Review and consider alternatives
- **ERROR**: Must fix before proceeding

### 3. Use Dry Run for Complex Operations
- Test batch operations with `dry_run=True`
- Review all changes before execution
- Validate tag combinations across multiple elements

### 4. Check Official Sources
- Consult OSM Wiki for authoritative guidance
- Use Taginfo for usage patterns
- Follow editor preset recommendations

### 5. Document Unusual Tags
- Add `note` or `description` tags for non-standard usage
- Reference sources for unusual tag values
- Consider regional variations in tagging

## Common Validation Scenarios

### Scenario 1: Restaurant Chain
```python
# Natural language: "McDonald's with drive-through and playground"
tags = {
    "amenity": "fast_food",
    "name": "McDonald's",
    "brand": "McDonald's",
    "cuisine": "burger",
    "drive_through": "yes",
    "playground": "yes"
}

validation = await validate_tags(tags, element_type="node")
# Result: All valid, suggests adding opening_hours and wheelchair access
```

### Scenario 2: Mixed-Use Building
```python
# Natural language: "Building with apartments above and shops below"
# This requires a way (building outline) + relations
tags = {
    "building": "mixed_use",
    "building:levels": "3",
    "shop": "yes",
    "residential": "apartments"
}

validation = await validate_tags(tags, element_type="way")
# Result: Valid, but suggests using relations for complex mixed use
```

### Scenario 3: Historical Feature
```python
# Natural language: "19th century church, now a museum"
tags = {
    "tourism": "museum",
    "historic": "church",
    "building": "church",
    "heritage": "yes",
    "start_date": "1847"
}

validation = await validate_tags(tags, element_type="way")
# Result: Valid combination showing historical context + current use
```

## Integration with External Validation

### OSM Inspector Integration
For advanced validation, consider external tools:
- **OSM Inspector**: http://tools.geofabrik.de/osmi/
- **KeepRight**: https://www.keepright.at/
- **Osmose**: https://osmose.openstreetmap.fr/

### Quality Assurance Workflows
1. **Pre-Creation**: Use MCP validation tools
2. **Post-Creation**: Monitor with QA tools
3. **Community Review**: Respond to changeset comments
4. **Continuous Improvement**: Update based on feedback

## Error Handling and Recovery

### Common Tag Errors
- **Typos in keys**: `ameneity` instead of `amenity`
- **Invalid values**: Non-standard cuisine types
- **Missing required tags**: Ways without proper highway tags
- **Conflicting tags**: `amenity=restaurant` + `landuse=forest`

### Recovery Procedures
1. **Immediate**: Use `modify_element_tags` to fix errors
2. **Batch**: Use `batch_tag_operations` for multiple fixes
3. **Revert**: Create corrective changeset if needed

### Monitoring and Alerts
- Set up changeset monitoring for your edits
- Respond to community feedback promptly
- Use QA tools to identify potential issues

This comprehensive validation system ensures that all tags created through the MCP server meet OSM standards and contribute to high-quality map data.