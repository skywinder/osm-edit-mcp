"""Public place-discovery contracts, also used to generate MCP JSON schemas."""

from typing import Annotated, Literal

from pydantic import Field
from typing_extensions import NotRequired, TypedDict

Latitude = Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False, strict=True)]
Longitude = Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False, strict=True)]
Radius = Annotated[int, Field(ge=1, le=10000, strict=True)]
Limit = Annotated[int, Field(ge=1, le=100, strict=True)]
GeocodeLimit = Annotated[int, Field(ge=1, le=10, strict=True)]
Viewbox = Annotated[list[float], Field(min_length=4, max_length=4)]
CountryCodes = Annotated[
    list[Annotated[str, Field(pattern=r"^[A-Za-z]{2}$")]],
    Field(min_length=1, max_length=10),
]
PlaceRef = Annotated[str, Field(pattern=r"^osm:(node|way|relation):[1-9][0-9]{0,18}$")]
Text = Annotated[str, Field(min_length=1, max_length=255)]
Category = Literal[
    "restaurant",
    "cafe",
    "bar",
    "pub",
    "hospital",
    "pharmacy",
    "bank",
    "atm",
    "toilets",
    "drinking_water",
    "school",
    "library",
    "parking",
    "place_of_worship",
    "museum",
    "gallery",
    "attraction",
    "viewpoint",
    "hotel",
    "hostel",
    "information",
    "artwork",
    "hackerspace",
    "park",
    "garden",
    "playground",
    "sports_centre",
    "swimming_pool",
    "monument",
    "memorial",
    "castle",
    "ruins",
    "archaeological_site",
    "supermarket",
    "convenience",
    "bakery",
    "books",
    "clothes",
]
Categories = Annotated[list[Category], Field(max_length=20)]
Tags = Annotated[dict[Text, Text], Field(max_length=10)]


class Location(TypedDict):
    lat: float
    lon: float


class ErrorDetails(TypedDict):
    code: str
    retryable: bool
    retry_after_seconds: float | None


class Place(TypedDict):
    type: Literal["node", "way", "relation"]
    id: int
    place_ref: str
    name: str | None
    tags: dict[str, str]
    location: Location | None
    location_source: str
    distance_meters: float | None
    osm_url: str
    source: Literal["openstreetmap"]
    address: dict[str, str]
    website: str | None
    opening_hours: str | None
    open_status: Literal["open", "closed", "unknown"]
    matched_reasons: list[str]
    unknown_features: list[str]
    preference_matches: int


class SearchData(TypedDict):
    places: list[Place]
    total: int
    count: int
    truncated: bool
    distance_type: str
    query_location: Location
    radius_meters: int
    distance_reference: str
    attribution: str
    retrieved_at: str
    data_timestamp: str | None
    evaluated_at: str | None
    unknown_opening_hours: int
    candidates_total: int


class SearchResult(TypedDict):
    success: bool
    message: str
    data: NotRequired[SearchData]
    error: NotRequired[str]
    error_details: NotRequired[ErrorDetails]


class LocationCandidate(TypedDict):
    place_ref: str | None
    display_name: str
    location: Location
    bbox: list[float]
    category: str | None
    place_type: str | None
    address: dict[str, str]
    importance: float
    osm_url: str | None


class ResolveData(TypedDict):
    query: str
    candidates: list[LocationCandidate]
    count: int
    ambiguous: bool
    attribution: str


class ResolveResult(TypedDict):
    success: bool
    message: str
    data: NotRequired[ResolveData]
    error: NotRequired[str]
    error_details: NotRequired[ErrorDetails]


class DetailsData(TypedDict):
    place: Place
    attribution: str
    data_timestamp: str | None


class DetailsResult(TypedDict):
    success: bool
    message: str
    data: NotRequired[DetailsData]
    error: NotRequired[str]
    error_details: NotRequired[ErrorDetails]
