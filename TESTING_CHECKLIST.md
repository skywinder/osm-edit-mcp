# OSM Edit MCP Server - Testing Checklist

This checklist helps you systematically test all 31 MCP tools to ensure everything works correctly.

## Pre-Test Setup

### 1. Configuration Check
- [ ] Copy `.env.example` to `.env` if not already done
- [ ] Update OAuth credentials in `.env` file
- [ ] Verify `OSM_USE_DEV_API=true` for safe testing
- [ ] Check log level is set appropriately (`LOG_LEVEL=INFO` or `DEBUG`)

### 2. Environment Setup
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Verify Python version: `python --version` (should be 3.8+)
- [ ] Test basic server startup: `python main.py` (should show config info)

### 3. Quick Configuration Test
```bash
# Test that configuration is loaded correctly
python -c "from src.osm_edit_mcp.server import config; print(f'API: {config.current_api_base_url}'); print(f'Dev Mode: {config.is_development}')"
```

## Automated Testing

### 1. Run Comprehensive Test Suite
```bash
python test_comprehensive.py
```

**Expected Results:**
- [ ] Test suite runs without crashing
- [ ] All read operations pass (tests 1-15)
- [ ] Write operations show expected errors (tests 16-27) - This is normal without OAuth
- [ ] Natural language operations process correctly (tests 28-31)
- [ ] Test report is generated (`test_report.json`)

### 2. Review Test Results
- [ ] Check `test_report.json` for detailed results
- [ ] Review `test_results.log` for any unexpected errors
- [ ] Note any completely failing tests for manual investigation

## Manual Testing Guide

### Phase 1: Basic Read Operations (Safe)

#### Test 1: Server Information
```bash
# Test with your MCP client or via the test script
# Expected: Server info with correct API URLs
```
- [ ] `get_server_info` returns server configuration
- [ ] API base URL matches your configuration
- [ ] Tool list includes all 31 tools

#### Test 2: Coordinate Validation
```bash
# Test coordinates: London (51.5074, -0.1278)
```
- [ ] `validate_coordinates` accepts valid coordinates
- [ ] Rejects invalid coordinates (lat > 90, lon > 180)
- [ ] Returns location information for valid coordinates

#### Test 3: OSM Element Retrieval
```bash
# Test known OSM elements
# Node: 150537 (Big Ben area)
# Way: 4082988 (Baker Street)
# Relation: 1306 (London bus route)
```
- [ ] `get_osm_node` retrieves node data with tags
- [ ] `get_osm_way` retrieves way data with node references
- [ ] `get_osm_relation` retrieves relation data with members
- [ ] All return proper error messages for non-existent IDs

#### Test 4: Area-based Queries
```bash
# Test small area in London: "-0.1279,-0.1278,51.5074,51.5075"
```
- [ ] `get_osm_elements_in_area` returns elements in bounding box
- [ ] Results include nodes, ways, and relations
- [ ] Proper error handling for invalid bounding boxes

#### Test 5: Search Operations
```bash
# Test various search operations
```
- [ ] `find_nearby_amenities` finds restaurants, cafes, etc.
- [ ] `get_place_info` resolves place names to coordinates
- [ ] `search_osm_elements` finds elements by text query
- [ ] `smart_geocode` converts addresses to coordinates

### Phase 2: Data Processing Operations

#### Test 6: Natural Language Processing
```bash
# Test natural language understanding
```
- [ ] `parse_natural_language_osm_request` correctly parses requests
- [ ] Identifies actions (create, update, delete)
- [ ] Extracts locations and business types
- [ ] Handles various language patterns

#### Test 7: Data Validation
```bash
# Test data validation
```
- [ ] `validate_osm_data` checks node structure
- [ ] Validates coordinate ranges
- [ ] Checks required tag formats
- [ ] Identifies potential data issues

#### Test 8: Export and Statistics
```bash
# Test data export and analysis
```
- [ ] `export_osm_data` exports data in JSON format
- [ ] `get_osm_statistics` provides area statistics
- [ ] Both handle various area sizes appropriately

### Phase 3: Write Operations (Simulation Mode)

⚠️ **NOTE**: These tests will fail at the API level without proper OAuth setup, but should validate input processing.

#### Test 9: Changeset Management
```bash
# Test changeset operations
```
- [ ] `create_changeset` validates changeset parameters
- [ ] `get_changeset` attempts to retrieve changeset info
- [ ] `close_changeset` validates closing parameters
- [ ] All provide meaningful error messages

#### Test 10: Element Creation
```bash
# Test element creation (will fail without OAuth)
```
- [ ] `create_osm_node` validates node parameters
- [ ] `create_osm_way` validates way parameters
- [ ] `create_osm_relation` validates relation parameters
- [ ] All check coordinate validity and tag format

#### Test 11: Element Updates
```bash
# Test element updates (will fail without OAuth)
```
- [ ] `update_osm_node` validates update parameters
- [ ] `update_osm_way` validates node references
- [ ] `update_osm_relation` validates member structure
- [ ] All preserve required fields

#### Test 12: Element Deletion
```bash
# Test element deletion (will fail without OAuth)
```
- [ ] `delete_osm_node` validates deletion parameters
- [ ] `delete_osm_way` validates deletion parameters
- [ ] `delete_osm_relation` validates deletion parameters
- [ ] All check changeset requirements

### Phase 4: Advanced Features

#### Test 13: Bulk Operations
```bash
# Test bulk operations
```
- [ ] `bulk_create_places` processes multiple places
- [ ] Validates all place data before processing
- [ ] Handles mixed valid/invalid data appropriately
- [ ] Returns detailed results for each place

#### Test 14: Natural Language Place Management
```bash
# Test natural language place operations
```
- [ ] `create_place_from_description` parses descriptions
- [ ] `find_and_update_place` locates existing places
- [ ] `delete_place_from_description` identifies places to delete
- [ ] All extract relevant information from natural language

#### Test 15: Historical Data
```bash
# Test historical data access
```
- [ ] `get_changeset_history` retrieves recent changesets
- [ ] Supports various query parameters
- [ ] Handles pagination appropriately
- [ ] Returns meaningful data structure

## Configuration Testing

### Dev/Prod Switching
- [ ] Set `OSM_USE_DEV_API=true` - verify dev API is used
- [ ] Set `OSM_USE_DEV_API=false` - verify prod API is used
- [ ] Check that API URLs change appropriately
- [ ] Verify log messages show correct API mode

### Log Level Testing
- [ ] Set `LOG_LEVEL=DEBUG` - verify debug messages appear
- [ ] Set `LOG_LEVEL=INFO` - verify info messages appear
- [ ] Set `LOG_LEVEL=WARNING` - verify only warnings/errors appear
- [ ] Set `LOG_LEVEL=ERROR` - verify only errors appear

## Error Handling Testing

### Network Errors
- [ ] Test with invalid API URLs
- [ ] Test with network connectivity issues
- [ ] Verify graceful error handling
- [ ] Check that error messages are informative

### Input Validation
- [ ] Test with invalid coordinates
- [ ] Test with missing required parameters
- [ ] Test with malformed data structures
- [ ] Verify all validation errors are caught

### Rate Limiting
- [ ] Test rapid successive requests
- [ ] Verify rate limiting is respected
- [ ] Check that retry logic works appropriately
- [ ] Test behavior when rate limits are exceeded

## Performance Testing

### Response Times
- [ ] Measure response times for read operations
- [ ] Check that complex queries complete reasonably
- [ ] Verify no unusual delays in simple operations
- [ ] Test with various data sizes

### Memory Usage
- [ ] Monitor memory usage during testing
- [ ] Check for memory leaks in long-running tests
- [ ] Verify cleanup after operations
- [ ] Test with large data sets

## Security Testing

### Configuration Security
- [ ] Verify credentials are not logged
- [ ] Check that .env is not committed to git
- [ ] Test with invalid OAuth credentials
- [ ] Verify secure credential storage

### API Security
- [ ] Test with malicious input data
- [ ] Verify SQL injection protection
- [ ] Check XSS protection in responses
- [ ] Test parameter tampering protection

## Documentation Testing

### README Accuracy
- [ ] Follow README setup instructions exactly
- [ ] Verify all code examples work
- [ ] Check that all configuration options are documented
- [ ] Test example use cases

### API Documentation
- [ ] Verify all 31 tools are documented
- [ ] Check that parameter descriptions are accurate
- [ ] Test example API calls
- [ ] Verify return value documentation

## Deployment Testing

### Environment Compatibility
- [ ] Test on different Python versions (3.8, 3.9, 3.10, 3.11)
- [ ] Test on different operating systems
- [ ] Verify dependency compatibility
- [ ] Check for platform-specific issues

### Integration Testing
- [ ] Test with different MCP clients
- [ ] Verify Claude Desktop integration
- [ ] Test with other AI assistants
- [ ] Check for integration-specific issues

## Test Results Documentation

### Create Test Report
- [ ] Document all test results
- [ ] Note any failing tests with error details
- [ ] Create issue reports for problems found
- [ ] Document workarounds for known issues

### Test Environment Details
- [ ] Record Python version used
- [ ] Record operating system details
- [ ] Record dependency versions
- [ ] Record test execution time

## Known Issues Checklist

Mark any issues you encounter during testing:

### Common Issues
- [ ] OAuth authentication failures (expected without setup)
- [ ] Rate limiting errors (expected with rapid testing)
- [ ] Network timeout errors (infrastructure dependent)
- [ ] Large data set processing delays (expected)

### Unexpected Issues
- [ ] Server crashes or hangs
- [ ] Incorrect data processing
- [ ] Configuration not loading
- [ ] Memory leaks or excessive usage

## Post-Test Actions

### Cleanup
- [ ] Remove test-generated files
- [ ] Clean up log files if needed
- [ ] Reset configuration to production values
- [ ] Clear any temporary data

### Documentation
- [ ] Update test results in project documentation
- [ ] Report any bugs found
- [ ] Update README with any discovered issues
- [ ] Create improvement suggestions

---

## Quick Test Commands

```bash
# Run full test suite
python test_comprehensive.py

# Test specific functionality
python -c "from src.osm_edit_mcp.server import get_server_info; import asyncio; print(asyncio.run(get_server_info()))"

# Test configuration
python -c "from src.osm_edit_mcp.server import config; print(f'Dev Mode: {config.is_development}'); print(f'API: {config.current_api_base_url}')"

# Test with MCP client
python main.py  # In one terminal
# Then connect with your MCP client

# Monitor logs
tail -f test_results.log
```

## Testing Tips

1. **Start with read operations** - they're safe and don't modify data
2. **Test configuration changes** - ensure dev/prod switching works
3. **Use small test areas** - don't overwhelm the API
4. **Check error messages** - they should be informative
5. **Test edge cases** - invalid coordinates, missing data, etc.
6. **Document everything** - note what works and what doesn't
7. **Test incrementally** - don't run everything at once initially

Remember: The goal is to verify that all tools work as expected and handle errors gracefully. Some failures are expected (like OAuth-protected operations without proper setup), but the tools should fail gracefully with informative error messages.