from typing import List, Dict, Optional, Tuple
import os
import requests
from requests import Timeout, RequestException


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"


def _headers() -> Dict[str, str]:
    contact = os.getenv("CONTACT_EMAIL", "hos-emergency-bot/0.1")
    return {"User-Agent": f"hos-emergency-bot/0.1 ({contact})"}


def geocode_place(place: str) -> Optional[Dict[str, float]]:
    if not place:
        return None
    # Quick local hints to avoid network when possible
    QUICK: Dict[str, Tuple[float, float]] = {
        "shibuya": (35.661777, 139.704051),
        "tokyo": (35.676203, 139.650311),
        "japan": (36.204824, 138.252924),
    }
    key = (place or "").strip().lower()
    if key in QUICK:
        lat, lon = QUICK[key]
        return {"lat": lat, "lon": lon}
    params = {
        "q": place,
        "format": "json",
        "limit": 1,
        "addressdetails": 0,
    }
    try:
        r = requests.get(NOMINATIM_URL, params=params, headers=_headers(), timeout=6)
        if not r.ok:
            return None
        arr = r.json()
        if not arr:
            return None
        lat = float(arr[0]["lat"])  # type: ignore
        lon = float(arr[0]["lon"])  # type: ignore
        return {"lat": lat, "lon": lon}
    except Timeout:
        return QUICK.get("tokyo") and {"lat": QUICK["tokyo"][0], "lon": QUICK["tokyo"][1]}
    except RequestException:
        return None


def reverse_geocode(lat: float, lon: float) -> str:
    try:
        params = {"format": "json", "lat": lat, "lon": lon, "zoom": 18, "addressdetails": 1}
        r = requests.get(REVERSE_URL, params=params, headers=_headers(), timeout=6)
        if not r.ok:
            return ""
        data = r.json()
        address = data.get("display_name") or ""
        return address or ""
    except (Timeout, RequestException, Exception):
        return ""


def build_address_from_tags(tags: Dict[str, str]) -> str:
    parts: List[str] = []
    # Common OSM address tags in Japan
    for key in [
        "addr:prefecture",
        "addr:city",
        "addr:ward",
        "addr:district",
        "addr:suburb",
        "addr:neighbourhood",
        "addr:street",
        "addr:block",
        "addr:housenumber",
        "addr:postcode",
    ]:
        val = tags.get(key)
        if val:
            parts.append(val)
    if not parts:
        # fallback single fields
        for key in ["addr:full", "addr:place", "addr:hamlet"]:
            val = tags.get(key)
            if val:
                parts.append(val)
                break
    return " ".join(parts)


def search_hospitals(lat: float, lon: float, radius_m: int = 2000) -> List[Dict]:
    query = f"""
    [out:json][timeout:6];
    (
      node["amenity"~"hospital|clinic"](around:{radius_m},{lat},{lon});
      way["amenity"~"hospital|clinic"](around:{radius_m},{lat},{lon});
      relation["amenity"~"hospital|clinic"](around:{radius_m},{lat},{lon});
    );
    out center 20;
    """
    r = None
    for endpoint in OVERPASS_URLS:
        try:
            r = requests.post(endpoint, data={"data": query}, timeout=7)
            if r.ok:
                break
        except (Timeout, RequestException):
            r = None
            continue
    if r is None:
        return []
    results: List[Dict] = []
    if r.ok:
        data = r.json()
        for el in data.get("elements", [])[:20]:
            tags = el.get("tags", {})
            name = tags.get("name") or tags.get("name:en") or tags.get("name:ja") or "Unknown"
            lat_out = el.get("lat") or (el.get("center") or {}).get("lat")
            lon_out = el.get("lon") or (el.get("center") or {}).get("lon")
            addr = build_address_from_tags(tags)
            if (not addr) and lat_out and lon_out:
                addr = reverse_geocode(lat_out, lon_out)
            results.append({
                "name": name,
                "address": addr,
                "lat": lat_out,
                "lon": lon_out,
            })
    return results


def search_pharmacies(lat: float, lon: float, radius_m: int = 1500) -> List[Dict]:
    query = f"""
    [out:json][timeout:7];
    (
      node["amenity"="pharmacy"](around:{radius_m},{lat},{lon});
      way["amenity"="pharmacy"](around:{radius_m},{lat},{lon});
      relation["amenity"="pharmacy"](around:{radius_m},{lat},{lon});
    );
    out center 30;
    """
    r = None
    for endpoint in OVERPASS_URLS:
        try:
            r = requests.post(endpoint, data={"data": query}, timeout=7)
            if r.ok:
                break
        except (Timeout, RequestException):
            r = None
            continue
    if r is None:
        return []
    results: List[Dict] = []
    if r.ok:
        data = r.json()
        for el in data.get("elements", [])[:30]:
            tags = el.get("tags", {})
            name = tags.get("name") or tags.get("name:en") or tags.get("name:ja") or "Unknown"
            lat_out = el.get("lat") or (el.get("center") or {}).get("lat")
            lon_out = el.get("lon") or (el.get("center") or {}).get("lon")
            addr = build_address_from_tags(tags)
            if (not addr) and lat_out and lon_out:
                addr = reverse_geocode(lat_out, lon_out)
            results.append({
                "name": name,
                "address": addr,
                "lat": lat_out,
                "lon": lon_out,
            })
    return results


