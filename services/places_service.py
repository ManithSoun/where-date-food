import math
import re
import requests
from config import GOOGLE_PLACES_API_KEY, SEARCH_RADIUS, MAX_RESULTS

DEFAULT_RADIUS = float(SEARCH_RADIUS)

DRINK_WORDS = [
    "coffee", "cafe", "latte", "espresso", "cappuccino",
    "boba", "bubble tea", "milk tea", "matcha",
    "tea", "iced tea", "teh", "drink", "drinks",
    "juice", "smoothie", "frappe", "chocolate", "cocoa",
    "lemonade", "soda", "refreshment"
]
BAR_WORDS = ["bar", "beer", "cocktail", "pub", "wine", "alcohol", "whiskey", "liquor"]
BAKERY_WORDS = ["bakery", "bread", "pastry", "cake", "dessert", "donut", "waffle"]


def build_query(keyword: str) -> str:
    k = keyword.lower().strip()
    if any(w in k for w in BAR_WORDS):
        return f"{keyword} bar"
    if any(w in k for w in DRINK_WORDS):
        return f"{keyword} cafe"
    if any(w in k for w in BAKERY_WORDS):
        return f"{keyword} bakery"
    return f"{keyword} restaurant"


def calculate_distance(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def format_distance(d: float) -> str:
    return f"{int(d * 1000)}m" if d < 1 else f"{d:.1f}km"


def parse_radius(text: str) -> float:
    t = text.lower()

    # "2-3 km", "2 to 3 km"
    range_km = re.search(r'(\d+(?:\.\d+)?)\s*[-–—to]+\s*(\d+(?:\.\d+)?)\s*(?:km|kilometer|k\b)', t)
    if range_km:
        return min(float(range_km.group(2)) * 1000, 50000)

    # "below 1 km", "under 500m", "within 2km", "less than 3km"
    below_km = re.search(r'(?:below|under|within|less than)\s*(\d+(?:\.\d+)?)\s*(?:km|kilometer|k\b)', t)
    if below_km:
        return min(float(below_km.group(1)) * 1000, 50000)

    below_m = re.search(r'(?:below|under|within|less than)\s*(\d+)\s*(?:meters?|m\b)', t)
    if below_m:
        return min(float(below_m.group(1)), 50000)

    # "2 km", "1.5km"
    km = re.search(r'(\d+(?:\.\d+)?)\s*(?:km|kilometer|k\b)', t)
    if km:
        return min(float(km.group(1)) * 1000, 50000)

    # "500m", "800 meters"
    m = re.search(r'(\d+)\s*(?:meters?|m\b)', t)
    if m:
        return min(float(m.group(1)), 50000)

    # natural language proximity
    if any(p in t for p in ["near me", "nearby", "close by", "around me", "closest", "nearest"]):
        return 1000.0

    return DEFAULT_RADIUS


def find_restaurants(lat: float, lng: float, keyword: str, radius: float = None, page_token: str = None) -> tuple[list[dict], str | None]:
    if radius is None:
        radius = DEFAULT_RADIUS

    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.priceLevel,places.location,places.googleMapsUri,nextPageToken"
    }

    body = {
        "textQuery": build_query(keyword),
        "pageSize": int(MAX_RESULTS),
        "languageCode": "en",
        "locationBias": {
            "circle": {
                "center": {"latitude": float(lat), "longitude": float(lng)},
                "radius": float(radius)
            }
        }
    }

    if page_token:
        body["pageToken"] = page_token

    try:
        r = requests.post(url, headers=headers, json=body, timeout=10)
        r.raise_for_status()
        data = r.json()
        raw_places = data.get("places", [])
        next_token = data.get("nextPageToken", None)
    except requests.exceptions.HTTPError as e:
        print(f"Places API HTTP error: {e.response.status_code} - {e.response.text}")
        return [], None
    except Exception as e:
        print(f"Places API error: {e}")
        return [], None

    seen = set()
    places = []
    for r in raw_places:
        name = r.get("displayName", {}).get("text", "Unknown")
        if name in seen:
            continue
        seen.add(name)
        place_lat = r.get("location", {}).get("latitude", lat)
        place_lng = r.get("location", {}).get("longitude", lng)
        dist_km = calculate_distance(lat, lng, place_lat, place_lng)

        maps_link = r.get("googleMapsUri")
        if not maps_link:
            continue  # skip places with no maps link

        places.append({
            "name": name,
            "address": r.get("formattedAddress", "N/A"),
            "rating": r.get("rating", "N/A"),
            "price_level": r.get("priceLevel", "N/A"),
            "distance_km": dist_km,
            "distance": format_distance(dist_km),
            "maps_link": maps_link
        })

    places.sort(key=lambda x: x["distance_km"])
    return places, next_token