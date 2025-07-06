#!/usr/bin/env python3
"""
Example client for OSM Edit MCP Web API

This demonstrates how to use the REST API from any application.
"""

import asyncio
import httpx
import json
from typing import Dict, Any, Optional

class OSMEditClient:
    """Client for OSM Edit MCP Web API"""
    
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Check if the server is healthy"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
    
    async def find_nearby_amenities(
        self, 
        lat: float, 
        lon: float, 
        radius_meters: int = 500,
        amenity_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Find amenities near a location"""
        data = {
            "lat": lat,
            "lon": lon,
            "radius_meters": radius_meters
        }
        if amenity_type:
            data["amenity_type"] = amenity_type
            
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/nearby-amenities",
                headers=self.headers,
                json=data
            )
            response.raise_for_status()
            return response.json()
    
    async def search_places(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """Search for places by name"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/search",
                headers=self.headers,
                json={"query": query, "limit": limit}
            )
            response.raise_for_status()
            return response.json()
    
    async def geocode(self, address: str) -> Dict[str, Any]:
        """Convert address to coordinates"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/geocode",
                headers=self.headers,
                json={"query": address}
            )
            response.raise_for_status()
            return response.json()
    
    async def validate_coordinates(self, lat: float, lon: float) -> Dict[str, Any]:
        """Validate coordinates and get location info"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/validate-coordinates",
                headers=self.headers,
                json={"lat": lat, "lon": lon}
            )
            response.raise_for_status()
            return response.json()


async def main():
    """Example usage of the OSM Edit API client"""
    
    # Configure your server URL and API key
    SERVER_URL = "http://localhost:8000"  # or https://your-server.com
    API_KEY = "your-api-key-here"
    
    # Create client
    client = OSMEditClient(SERVER_URL, API_KEY)
    
    print("🌍 OSM Edit MCP Web API Client Example\n")
    
    try:
        # 1. Health check
        print("1️⃣ Checking server health...")
        health = await client.health_check()
        print(f"   Status: {health['status']}")
        print(f"   Mode: {health['api_mode']}")
        print(f"   Version: {health['version']}\n")
        
        # 2. Find restaurants near Big Ben, London
        print("2️⃣ Finding restaurants near Big Ben...")
        lat, lon = 51.5007, -0.1246
        restaurants = await client.find_nearby_amenities(
            lat, lon, 
            radius_meters=500,
            amenity_type="restaurant"
        )
        if restaurants['success']:
            data = restaurants['data']
            print(f"   Found {data['count']} restaurants")
            for rest in data['elements'][:3]:  # Show first 3
                name = rest['tags'].get('name', 'Unnamed')
                cuisine = rest['tags'].get('cuisine', 'Unknown')
                print(f"   - {name} ({cuisine})")
        print()
        
        # 3. Search for places
        print("3️⃣ Searching for 'Central Park'...")
        search_results = await client.search_places("Central Park", limit=5)
        if search_results['success']:
            for result in search_results['data'][:3]:
                print(f"   - {result['display_name']}")
        print()
        
        # 4. Geocode an address
        print("4️⃣ Geocoding '10 Downing Street, London'...")
        geocode_result = await client.geocode("10 Downing Street, London")
        if geocode_result['success']:
            data = geocode_result['data']
            print(f"   Location: {data['display_name']}")
            print(f"   Coordinates: {data['lat']}, {data['lon']}")
        print()
        
        # 5. Validate coordinates
        print("5️⃣ Validating coordinates (48.8584, 2.2945)...")
        validation = await client.validate_coordinates(48.8584, 2.2945)
        if validation['success']:
            data = validation['data']
            print(f"   Valid: {data['valid']}")
            print(f"   Location: {data['display_name']}")
            
    except httpx.HTTPStatusError as e:
        print(f"❌ API Error: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())