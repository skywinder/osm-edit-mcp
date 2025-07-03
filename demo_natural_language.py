#!/usr/bin/env python3
"""
Demo: Natural Language OSM Editing
Shows how the MCP server converts natural language to OSM tags
"""

import asyncio
import json
from src.osm_edit_mcp.server import mcp

async def demo_natural_language_processing():
    """Demonstrate natural language to OSM tag conversion"""

    print("🗣️  Natural Language OSM Editing Demo")
    print("=" * 50)

    # Test cases for natural language processing
    test_cases = [
        {
            "description": "coffee shop with WiFi and outdoor seating",
            "element_type": "node",
            "context": "Urban commercial area"
        },
        {
            "description": "Italian restaurant with takeaway and wheelchair access",
            "element_type": "node",
            "context": "Downtown area"
        },
        {
            "description": "residential street with bike lanes",
            "element_type": "way",
            "context": "Suburban neighborhood"
        },
        {
            "description": "bus stop with shelter and real-time display",
            "element_type": "node",
            "context": "Major bus route"
        },
        {
            "description": "grocery store with parking and pharmacy inside",
            "element_type": "node",
            "context": "Shopping center"
        },
        {
            "description": "public library with computers and WiFi",
            "element_type": "node",
            "context": "City center"
        }
    ]

    print("\n🚀 Testing Natural Language Processing...")

    for i, test in enumerate(test_cases, 1):
        print(f"\n--- Test Case {i} ---")
        print(f"Description: '{test['description']}'")
        print(f"Element Type: {test['element_type']}")
        print(f"Context: {test['context']}")

        try:
            # Parse natural language to tags
            result = await mcp.call_tool(
                "parse_natural_language_tags",
                {
                    "description": test["description"],
                    "element_type": test["element_type"],
                    "location_context": test["context"]
                }
            )

            if result.get("success"):
                data = result["data"]
                print("✅ Conversion successful!")

                # Show primary tags
                if "primary_tags" in data:
                    print("📋 Primary Tags:")
                    for key, value in data["primary_tags"].items():
                        print(f"   {key}={value}")

                # Show additional tags
                if "additional_tags" in data:
                    print("🔧 Additional Tags:")
                    for key, value in data["additional_tags"].items():
                        print(f"   {key}={value}")

                # Show suggestions
                if "suggestions" in data and data["suggestions"]:
                    print("💡 Suggestions:")
                    for suggestion in data["suggestions"][:3]:  # Show top 3
                        print(f"   • {suggestion}")

                # Show validation
                if "validation" in data:
                    validation = data["validation"]
                    if validation.get("valid"):
                        print("✅ Tags are valid")
                    else:
                        print("⚠️  Validation warnings:")
                        for warning in validation.get("warnings", []):
                            print(f"   • {warning}")
            else:
                print(f"❌ Error: {result.get('error', 'Unknown error')}")

        except Exception as e:
            print(f"❌ Exception: {e}")

    print("\n" + "=" * 50)
    print("✨ Demo completed!")

async def demo_tag_explanation():
    """Demonstrate converting tags back to natural language"""

    print("\n🔍 Tag Explanation Demo")
    print("=" * 50)

    # Sample OSM tags to explain
    tag_examples = [
        {
            "name": "Coffee Shop",
            "tags": {
                "amenity": "cafe",
                "internet_access": "wlan",
                "outdoor_seating": "yes",
                "cuisine": "coffee_shop"
            }
        },
        {
            "name": "Italian Restaurant",
            "tags": {
                "amenity": "restaurant",
                "cuisine": "italian",
                "takeaway": "yes",
                "wheelchair": "yes",
                "opening_hours": "Mo-Su 11:00-22:00"
            }
        },
        {
            "name": "Residential Road",
            "tags": {
                "highway": "residential",
                "cycleway": "lane",
                "maxspeed": "30",
                "surface": "asphalt"
            }
        }
    ]

    for example in tag_examples:
        print(f"\n--- {example['name']} ---")
        print("Tags:", json.dumps(example["tags"], indent=2))

        try:
            result = await mcp.call_tool("explain_tags", {"tags": example["tags"]})

            if result.get("success"):
                data = result["data"]
                print(f"📝 Human Description: {data.get('human_description', 'N/A')}")

                if "feature_type" in data:
                    print(f"🏷️  Feature Type: {data['feature_type']}")

                if "details" in data and data["details"]:
                    print("📋 Details:")
                    for detail in data["details"]:
                        print(f"   • {detail}")
            else:
                print(f"❌ Error: {result.get('error', 'Unknown error')}")

        except Exception as e:
            print(f"❌ Exception: {e}")

async def demo_tag_suggestions():
    """Demonstrate tag suggestion system"""

    print("\n🎯 Tag Suggestion Demo")
    print("=" * 50)

    # Test scenarios for tag suggestions
    scenarios = [
        {
            "existing_tags": {"amenity": "restaurant"},
            "description": "User wants to add cuisine and accessibility info"
        },
        {
            "existing_tags": {"highway": "primary"},
            "description": "User wants to add traffic and surface details"
        },
        {
            "existing_tags": {"shop": "supermarket"},
            "description": "User wants to add facilities and services"
        }
    ]

    for i, scenario in enumerate(scenarios, 1):
        print(f"\n--- Scenario {i} ---")
        print(f"Existing tags: {scenario['existing_tags']}")
        print(f"Context: {scenario['description']}")

        try:
            result = await mcp.call_tool(
                "suggest_tags",
                {
                    "existing_tags": scenario["existing_tags"],
                    "context": scenario["description"]
                }
            )

            if result.get("success"):
                suggestions = result["data"].get("suggestions", [])
                print("💡 Tag Suggestions:")
                for suggestion in suggestions[:5]:  # Show top 5
                    print(f"   • {suggestion}")
            else:
                print(f"❌ Error: {result.get('error', 'Unknown error')}")

        except Exception as e:
            print(f"❌ Exception: {e}")

async def main():
    """Run all demos"""
    print("🎮 OSM Edit MCP Server - Natural Language Demo")
    print("This demo shows how natural language gets converted to OSM tags")
    print("\n" + "=" * 60)

    try:
        await demo_natural_language_processing()
        await demo_tag_explanation()
        await demo_tag_suggestions()

        print("\n" + "=" * 60)
        print("🎉 All demos completed successfully!")
        print("\n📖 Next Steps:")
        print("1. Check docs/quick-start-guide.md for usage instructions")
        print("2. Review docs/mcp-usage-examples.md for more examples")
        print("3. Set up OAuth credentials to start editing OSM")

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        print("\n🔧 Troubleshooting:")
        print("1. Make sure the server is installed: uv pip install -e .")
        print("2. Check that all dependencies are installed")
        print("3. Review the server logs for errors")

if __name__ == "__main__":
    asyncio.run(main())