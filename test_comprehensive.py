#!/usr/bin/env python3
"""
Comprehensive Test Suite for OSM Edit MCP Server
Tests all 31 MCP tools systematically and generates detailed reports
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import traceback

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from osm_edit_mcp.server import (
    get_osm_node, get_osm_way, get_osm_relation, get_osm_elements_in_area,
    create_changeset, get_changeset, close_changeset, get_server_info,
    find_nearby_amenities, validate_coordinates, get_place_info,
    search_osm_elements, create_osm_node, create_osm_way, create_osm_relation,
    update_osm_node, update_osm_way, update_osm_relation,
    delete_osm_node, delete_osm_way, delete_osm_relation,
    create_place_from_description, find_and_update_place,
    delete_place_from_description, parse_natural_language_osm_request,
    bulk_create_places, validate_osm_data, get_changeset_history,
    export_osm_data, get_osm_statistics, smart_geocode,
    check_authentication, config, logger
)

class TestResult:
    """Represents the result of a single test"""
    def __init__(self, tool_name: str, success: bool, message: str,
                 duration: float = 0.0, error: Optional[str] = None):
        self.tool_name = tool_name
        self.success = success
        self.message = message
        self.duration = duration
        self.error = error
        self.timestamp = datetime.now().isoformat()

class OSMTestSuite:
    """Comprehensive test suite for all OSM Edit MCP tools"""

    def __init__(self):
        self.results: List[TestResult] = []
        self.setup_logging()

    def setup_logging(self):
        """Setup logging for the test suite"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('test_results.log')
            ]
        )
        self.logger = logging.getLogger(__name__)

    async def run_test(self, test_name: str, test_func, *args, **kwargs) -> TestResult:
        """Run a single test and return result"""
        start_time = asyncio.get_event_loop().time()

        try:
            self.logger.info(f"Testing {test_name}...")
            result = await test_func(*args, **kwargs)

            duration = asyncio.get_event_loop().time() - start_time

            if isinstance(result, dict) and result.get('success'):
                return TestResult(test_name, True, "Test passed", duration)
            elif isinstance(result, dict) and not result.get('success'):
                error_msg = result.get('error', 'Unknown error')
                return TestResult(test_name, False, f"Test failed: {error_msg}", duration, error_msg)
            else:
                return TestResult(test_name, True, "Test completed", duration)

        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            error_msg = f"{type(e).__name__}: {str(e)}"
            self.logger.error(f"Test {test_name} failed: {error_msg}")
            return TestResult(test_name, False, f"Test failed with exception", duration, error_msg)

    async def test_read_operations(self):
        """Test all read-only operations that don't modify OSM data"""
        self.logger.info("=== Testing Read Operations ===")

        # Test 0: Check authentication status first
        auth_result = await self.run_test("check_authentication", check_authentication)
        self.results.append(auth_result)
        if auth_result.success:
            self.logger.info(f"✅ Authentication working: {auth_result.message}")
        else:
            self.logger.warning(f"⚠️ Authentication issue: {auth_result.error}")

        # Test 1: Get server info
        result = await self.run_test("get_server_info", get_server_info)
        self.results.append(result)

        # Test 2: Validate coordinates
        result = await self.run_test("validate_coordinates", validate_coordinates, 51.5074, -0.1278)
        self.results.append(result)

        # Test 3: Get OSM node (using dev server ID that exists)
        result = await self.run_test("get_osm_node", get_osm_node, 150537)
        self.results.append(result)

        # Test 4: Get OSM way (try a few different IDs for dev server)
        result = await self.run_test("get_osm_way", get_osm_way, 1)
        self.results.append(result)

        # Test 5: Get OSM relation (try a smaller ID for dev server)
        result = await self.run_test("get_osm_relation", get_osm_relation, 1)
        self.results.append(result)

        # Test 6: Get elements in area (larger area for dev server compatibility)
        result = await self.run_test("get_osm_elements_in_area", get_osm_elements_in_area,
                                   "-0.13,-0.12,51.50,51.51")
        self.results.append(result)

        # Test 7: Find nearby amenities
        result = await self.run_test("find_nearby_amenities", find_nearby_amenities,
                                   51.5074, -0.1278, 500, "restaurant")
        self.results.append(result)

        # Test 8: Get place info
        result = await self.run_test("get_place_info", get_place_info, "London")
        self.results.append(result)

        # Test 9: Search OSM elements
        result = await self.run_test("search_osm_elements", search_osm_elements,
                                   "cafe", "node")
        self.results.append(result)

        # Test 10: Smart geocode
        result = await self.run_test("smart_geocode", smart_geocode,
                                   "10 Downing Street, London")
        self.results.append(result)

        # Test 11: Parse natural language request
        result = await self.run_test("parse_natural_language_osm_request",
                                   parse_natural_language_osm_request,
                                   "Find Italian restaurants near the London Eye")
        self.results.append(result)

        # Test 12: Export OSM data
        result = await self.run_test("export_osm_data", export_osm_data,
                                   "-0.13,-0.12,51.50,51.51", "json")
        self.results.append(result)

        # Test 13: Get OSM statistics
        result = await self.run_test("get_osm_statistics", get_osm_statistics,
                                   "-0.13,-0.12,51.50,51.51")
        self.results.append(result)

        # Test 14: Get changeset history
        result = await self.run_test("get_changeset_history", get_changeset_history,
                                   None, 10)
        self.results.append(result)

        # Test 15: Validate OSM data
        test_data = {
            "type": "node",
            "lat": 51.5074,
            "lon": -0.1278,
            "tags": {"name": "Test Location", "amenity": "restaurant"}
        }
        result = await self.run_test("validate_osm_data", validate_osm_data, test_data)
        self.results.append(result)

    async def test_write_operations_simulation(self):
        """Test write operations in simulation mode (no actual API calls)"""
        self.logger.info("=== Testing Write Operations (Simulation) ===")

        # These tests check the tool logic without making actual API calls
        # They will fail at the API level but validate the input processing

        # Test 16: Create changeset (will fail without OAuth but validates input)
        result = await self.run_test("create_changeset", create_changeset,
                                   "Test changeset for validation")
        self.results.append(result)

        # Test 17: Get changeset (test with a known changeset ID)
        result = await self.run_test("get_changeset", get_changeset, 1)
        self.results.append(result)

        # Test 18: Create OSM node (Belgrade location with unique name)
        # First create a changeset for this test
        changeset_result = await create_changeset("Test node creation", {"test": "true"})
        changeset_id = changeset_result.get("data", {}).get("changeset_id", 1) if changeset_result.get("success") else 1

        import random
        test_name = f"Test Node {random.randint(1000, 9999)}"
        result = await self.run_test("create_osm_node", create_osm_node,
                                   44.80366197537814, 20.486398637294773,
                                   {"name": test_name, "amenity": "restaurant"}, changeset_id)
        self.results.append(result)

        # Test 19: Create OSM way (will fail without changeset but validates input)
        result = await self.run_test("create_osm_way", create_osm_way,
                                   [1, 2, 3], {"highway": "residential"}, 1)
        self.results.append(result)

        # Test 20: Create OSM relation (will fail without changeset but validates input)
        members = [{"type": "way", "ref": 1, "role": "outer"}]
        result = await self.run_test("create_osm_relation", create_osm_relation,
                                   members, {"type": "multipolygon"}, 1)
        self.results.append(result)

        # Test 21: Update OSM node (will fail without changeset but validates input)
        result = await self.run_test("update_osm_node", update_osm_node,
                                   1, 51.5074, -0.1278,
                                   {"name": "Updated Node"}, 1)
        self.results.append(result)

        # Test 22: Update OSM way (will fail without changeset but validates input)
        result = await self.run_test("update_osm_way", update_osm_way,
                                   1, [1, 2, 3], {"highway": "primary"}, 1)
        self.results.append(result)

        # Test 23: Update OSM relation (will fail without changeset but validates input)
        result = await self.run_test("update_osm_relation", update_osm_relation,
                                   1, members, {"type": "route"}, 1)
        self.results.append(result)

        # Test 24: Delete OSM node (will fail without changeset but validates input)
        result = await self.run_test("delete_osm_node", delete_osm_node, 1, 1)
        self.results.append(result)

        # Test 25: Delete OSM way (will fail without changeset but validates input)
        result = await self.run_test("delete_osm_way", delete_osm_way, 1, 1)
        self.results.append(result)

        # Test 26: Delete OSM relation (will fail without changeset but validates input)
        result = await self.run_test("delete_osm_relation", delete_osm_relation, 1, 1)
        self.results.append(result)

        # Test 27: Close changeset (will fail without changeset but validates input)
        result = await self.run_test("close_changeset", close_changeset, 1)
        self.results.append(result)

    async def test_natural_language_operations(self):
        """Test natural language processing operations"""
        self.logger.info("=== Testing Natural Language Operations ===")

        # Test 28: Create place from description (Belgrade location)
        import random
        cafe_name = f"Bean There {random.randint(1000, 9999)}"
        result = await self.run_test("create_place_from_description",
                                   create_place_from_description,
                                   f"Add a coffee shop called '{cafe_name}' at 44.80366197537814, 20.486398637294773")
        self.results.append(result)

        # Test 29: Find and update place
        result = await self.run_test("find_and_update_place",
                                   find_and_update_place,
                                   "Update the restaurant at Trafalgar Square to be open until 11pm")
        self.results.append(result)

        # Test 30: Delete place from description (Belgrade location)
        result = await self.run_test("delete_place_from_description",
                                   delete_place_from_description,
                                   "Remove the temporary marker at 44.80366197537814, 20.486398637294773")
        self.results.append(result)

        # Test 31: Bulk create places (Belgrade area with unique names)
        import random
        restaurant_name = f"Test Restaurant {random.randint(1000, 9999)}"
        cafe_name = f"Test Cafe {random.randint(1000, 9999)}"
        places_data = [
            {
                "name": restaurant_name,
                "lat": 44.80366197537814,
                "lon": 20.486398637294773,
                "tags": {"amenity": "restaurant", "cuisine": "italian"}
            },
            {
                "name": cafe_name,
                "lat": 44.80376197537814,  # Slightly offset
                "lon": 20.486498637294773,
                "tags": {"amenity": "cafe"}
            }
        ]
        result = await self.run_test("bulk_create_places", bulk_create_places,
                                   places_data)
        self.results.append(result)

    async def run_all_tests(self):
        """Run all test suites"""
        self.logger.info("Starting comprehensive OSM Edit MCP test suite...")
        self.logger.info(f"API Mode: {'Development' if config.is_development else 'Production'}")
        self.logger.info(f"API Base URL: {config.current_api_base_url}")

        start_time = asyncio.get_event_loop().time()

        # Run all test suites
        await self.test_read_operations()
        await self.test_write_operations_simulation()
        await self.test_natural_language_operations()

        total_duration = asyncio.get_event_loop().time() - start_time

        # Generate report
        self.generate_report(total_duration)

    def generate_report(self, total_duration: float):
        """Generate comprehensive test report"""
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.success)
        failed_tests = total_tests - passed_tests

        print("\n" + "="*80)
        print("OSM EDIT MCP SERVER - COMPREHENSIVE TEST REPORT")
        print("="*80)
        print(f"Test Suite Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Configuration: {'Development' if config.is_development else 'Production'}")
        print(f"API Base URL: {config.current_api_base_url}")
        print(f"Total Duration: {total_duration:.2f} seconds")
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")

        # Detailed results
        print("\n" + "="*80)
        print("DETAILED TEST RESULTS")
        print("="*80)

        for i, result in enumerate(self.results, 1):
            status = "✅ PASS" if result.success else "❌ FAIL"
            print(f"{i:2d}. {status} {result.tool_name:<30} ({result.duration:.2f}s)")
            if not result.success:
                print(f"    Error: {result.error}")

        # Failed tests summary
        if failed_tests > 0:
            print(f"\n" + "="*80)
            print("FAILED TESTS SUMMARY")
            print("="*80)

            for result in self.results:
                if not result.success:
                    print(f"❌ {result.tool_name}")
                    print(f"   Error: {result.error}")
                    print(f"   Message: {result.message}")
                    print()

        # Save detailed report to file
        self.save_json_report()

        print(f"\nDetailed report saved to: test_report.json")
        print(f"Logs saved to: test_results.log")

    def save_json_report(self):
        """Save detailed test report to JSON file"""
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "configuration": {
                "is_development": config.is_development,
                "api_base_url": config.current_api_base_url,
                "log_level": config.log_level
            },
            "summary": {
                "total_tests": len(self.results),
                "passed": sum(1 for r in self.results if r.success),
                "failed": sum(1 for r in self.results if not r.success),
                "success_rate": (sum(1 for r in self.results if r.success) / len(self.results)) * 100
            },
            "results": [
                {
                    "tool_name": r.tool_name,
                    "success": r.success,
                    "message": r.message,
                    "duration": r.duration,
                    "error": r.error,
                    "timestamp": r.timestamp
                }
                for r in self.results
            ]
        }

        with open("test_report.json", "w") as f:
            json.dump(report_data, f, indent=2)

async def main():
    """Main test runner"""
    print("OSM Edit MCP Server - Comprehensive Test Suite")
    print("This will test all 31 MCP tools systematically")
    print("=" * 60)

    # Create and run test suite
    test_suite = OSMTestSuite()
    await test_suite.run_all_tests()

    print("\nTest suite completed!")
    print("Review the results above and check the generated files:")
    print("- test_report.json: Detailed JSON report")
    print("- test_results.log: Detailed logs")

if __name__ == "__main__":
    asyncio.run(main())