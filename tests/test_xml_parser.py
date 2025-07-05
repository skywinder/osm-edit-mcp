"""Test XML parsing functionality."""
import pytest
from src.osm_edit_mcp.server import parse_osm_xml


def test_parse_node_xml():
    """Test parsing OSM node XML."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <osm version="0.6">
        <node id="123" lat="51.5074" lon="-0.1278" version="1" changeset="456" 
              timestamp="2024-01-01T00:00:00Z" user="testuser" uid="789">
            <tag k="name" v="Test Node"/>
            <tag k="amenity" v="restaurant"/>
        </node>
    </osm>"""
    
    result = parse_osm_xml(xml_content)
    assert "elements" in result
    assert len(result["elements"]) == 1
    
    node = result["elements"][0]
    assert node["type"] == "node"
    assert node["id"] == 123
    assert node["lat"] == 51.5074
    assert node["lon"] == -0.1278
    assert node["tags"]["name"] == "Test Node"
    assert node["tags"]["amenity"] == "restaurant"


def test_parse_way_xml():
    """Test parsing OSM way XML."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <osm version="0.6">
        <way id="456" version="2" changeset="789" 
             timestamp="2024-01-01T00:00:00Z" user="testuser" uid="123">
            <nd ref="100"/>
            <nd ref="101"/>
            <nd ref="102"/>
            <tag k="highway" v="residential"/>
            <tag k="name" v="Test Street"/>
        </way>
    </osm>"""
    
    result = parse_osm_xml(xml_content)
    assert "elements" in result
    assert len(result["elements"]) == 1
    
    way = result["elements"][0]
    assert way["type"] == "way"
    assert way["id"] == 456
    assert way["nodes"] == [100, 101, 102]
    assert way["tags"]["highway"] == "residential"
    assert way["tags"]["name"] == "Test Street"


def test_parse_relation_xml():
    """Test parsing OSM relation XML."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <osm version="0.6">
        <relation id="789" version="1" changeset="123" 
                  timestamp="2024-01-01T00:00:00Z" user="testuser" uid="456">
            <member type="way" ref="100" role="outer"/>
            <member type="way" ref="101" role="inner"/>
            <tag k="type" v="multipolygon"/>
            <tag k="name" v="Test Area"/>
        </relation>
    </osm>"""
    
    result = parse_osm_xml(xml_content)
    assert "elements" in result
    assert len(result["elements"]) == 1
    
    relation = result["elements"][0]
    assert relation["type"] == "relation"
    assert relation["id"] == 789
    assert len(relation["members"]) == 2
    assert relation["members"][0]["type"] == "way"
    assert relation["members"][0]["ref"] == 100
    assert relation["members"][0]["role"] == "outer"
    assert relation["tags"]["type"] == "multipolygon"


def test_parse_invalid_xml():
    """Test parsing invalid XML."""
    xml_content = "This is not valid XML"
    
    result = parse_osm_xml(xml_content)
    assert "error" in result
    assert "Failed to parse XML" in result["error"]


def test_parse_empty_xml():
    """Test parsing empty OSM XML."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <osm version="0.6">
    </osm>"""
    
    result = parse_osm_xml(xml_content)
    assert "elements" in result
    assert len(result["elements"]) == 0