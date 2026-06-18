import math
import requests
from config import GOOGLE_PLACES_API_KEY, SEARCH_RADIUS, MAX_RESULTS

def calculate_distance(lat1, lng1, lat2, lng2) -> str:
    R = 6371
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    distance = 2 * R * math.asin(math.sqrt(a))
    if distance < 1:
        return f"{int(distance * 1000)}m"
    return f"{distance:.1f}km"

def find_restaurants(lat: float, lng: float, keyword: str) -> list[dict]:
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.priceLevel,places.location,places.googleMapsUri"
    }
    body = {
        "textQuery": f"{keyword} restaurant near me",
        "locationBias": {
            "circle": {
                "center": {
                    "latitude": lat,
                    "longitude": lng
                },
                "radius": float(SEARCH_RADIUS)
            }
        },
        "maxResultCount": MAX_RESULTS,
        "languageCode": "en"
    }

    response = requests.post(url, headers=headers, json=body)
    results = response.json().get("places", [])

    return [{
        "name": r.get("displayName", {}).get("text", "Unknown"),
        "address": r.get("formattedAddress", "N/A"),
        "rating": r.get("rating", "N/A"),
        "price_level": r.get("priceLevel", "N/A"),
        "distance": calculate_distance(
            lat, lng,
            r.get("location", {}).get("latitude", lat),
            r.get("location", {}).get("longitude", lng)
        ),
        "maps_link": r.get("googleMapsUri", "N/A")
    } for r in results]