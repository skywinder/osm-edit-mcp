"""
Web API wrapper for OSM Edit MCP Server

This allows remote access to the MCP server via HTTP endpoints.
"""

import os
import json
import asyncio
import logging
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from contextlib import asynccontextmanager

# Import the MCP server components
from osm_edit_mcp.server import (
    find_nearby_amenities,
    get_place_info,
    search_osm_elements,
    smart_geocode,
    validate_coordinates,
    get_osm_elements_in_area,
    get_osm_statistics,
    get_osm_node,
    get_osm_way,
    get_osm_relation,
    create_changeset,
    create_osm_node,
    create_place_from_description,
    parse_natural_language_osm_request,
    config
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Security
security = HTTPBearer()

# Simple API key authentication (you should use a more secure method in production)
API_KEY = os.getenv("API_KEY", "your-secret-api-key-here")

def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verify API key for authentication"""
    if credentials.credentials != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return credentials.credentials

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle"""
    logger.info(f"Starting OSM Edit Web API")
    logger.info(f"API Mode: {'Development' if config.is_development else 'Production'}")
    logger.info(f"API Base URL: {config.current_api_base_url}")
    yield
    logger.info("Shutting down OSM Edit Web API")

# Create FastAPI app
app = FastAPI(
    title="OSM Edit API",
    description="Web API for OpenStreetMap data access and editing",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class NearbyAmenitiesRequest(BaseModel):
    lat: float
    lon: float
    radius_meters: int = 500
    amenity_type: Optional[str] = None

class PlaceInfoRequest(BaseModel):
    query: str

class SearchRequest(BaseModel):
    query: str
    limit: int = 10

class GeocodeRequest(BaseModel):
    query: str

class CoordinatesRequest(BaseModel):
    lat: float
    lon: float

class AreaRequest(BaseModel):
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float

class NaturalLanguageRequest(BaseModel):
    query: str

class CreateNodeRequest(BaseModel):
    lat: float
    lon: float
    tags: Dict[str, str]
    changeset_id: str

class CreatePlaceRequest(BaseModel):
    description: str
    changeset_id: str

# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "api_mode": "development" if config.is_development else "production",
        "version": "1.0.0"
    }

@app.post("/api/nearby-amenities")
async def api_find_nearby_amenities(
    request: NearbyAmenitiesRequest,
    api_key: str = Depends(verify_api_key)
):
    """Find nearby amenities"""
    try:
        result = await find_nearby_amenities(
            lat=request.lat,
            lon=request.lon,
            radius_meters=request.radius_meters,
            amenity_type=request.amenity_type
        )
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error finding nearby amenities: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/place-info")
async def api_get_place_info(
    request: PlaceInfoRequest,
    api_key: str = Depends(verify_api_key)
):
    """Get information about a place"""
    try:
        result = await get_place_info(query=request.query)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error getting place info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search")
async def api_search_osm_elements(
    request: SearchRequest,
    api_key: str = Depends(verify_api_key)
):
    """Search for OSM elements"""
    try:
        result = await search_osm_elements(
            query=request.query,
            limit=request.limit
        )
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error searching OSM elements: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/geocode")
async def api_smart_geocode(
    request: GeocodeRequest,
    api_key: str = Depends(verify_api_key)
):
    """Convert address to coordinates"""
    try:
        result = await smart_geocode(query=request.query)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error geocoding: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/validate-coordinates")
async def api_validate_coordinates(
    request: CoordinatesRequest,
    api_key: str = Depends(verify_api_key)
):
    """Validate coordinates"""
    try:
        result = await validate_coordinates(
            lat=request.lat,
            lon=request.lon
        )
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error validating coordinates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/elements-in-area")
async def api_get_osm_elements_in_area(
    request: AreaRequest,
    api_key: str = Depends(verify_api_key)
):
    """Get all OSM elements in an area"""
    try:
        result = await get_osm_elements_in_area(
            min_lat=request.min_lat,
            min_lon=request.min_lon,
            max_lat=request.max_lat,
            max_lon=request.max_lon
        )
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error getting elements in area: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/natural-language")
async def api_parse_natural_language(
    request: NaturalLanguageRequest,
    api_key: str = Depends(verify_api_key)
):
    """Parse natural language OSM request"""
    try:
        result = await parse_natural_language_osm_request(request=request.query)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error parsing natural language: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/node/{node_id}")
async def api_get_osm_node(
    node_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Get OSM node by ID"""
    try:
        result = await get_osm_node(node_id=node_id)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error getting node: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/way/{way_id}")
async def api_get_osm_way(
    way_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Get OSM way by ID"""
    try:
        result = await get_osm_way(way_id=way_id)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error getting way: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/relation/{relation_id}")
async def api_get_osm_relation(
    relation_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Get OSM relation by ID"""
    try:
        result = await get_osm_relation(relation_id=relation_id)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error getting relation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Write operations (require authentication)
@app.post("/api/changeset")
async def api_create_changeset(
    comment: str,
    api_key: str = Depends(verify_api_key)
):
    """Create a new changeset (requires OAuth)"""
    try:
        result = await create_changeset(comment=comment)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error creating changeset: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/node")
async def api_create_osm_node(
    request: CreateNodeRequest,
    api_key: str = Depends(verify_api_key)
):
    """Create a new OSM node (requires OAuth)"""
    try:
        result = await create_osm_node(
            lat=request.lat,
            lon=request.lon,
            tags=request.tags,
            changeset_id=request.changeset_id
        )
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error creating node: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/place-from-description")
async def api_create_place_from_description(
    request: CreatePlaceRequest,
    api_key: str = Depends(verify_api_key)
):
    """Create a place from natural language description (requires OAuth)"""
    try:
        result = await create_place_from_description(
            description=request.description,
            changeset_id=request.changeset_id
        )
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error creating place: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # Run the server
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)