"""
flight_tool.py — Flight search & recommendation tool for a multi-agent travel planner.

What it does:
  1. Resolves places ("Tokyo", "Japan", "HYD") to airport codes
  2. Searches fares: Ignav (primary) -> fast-flights / Google Flights (fallback)
  3. Ranks results: cheapest, fastest, best value
  4. Returns clean JSON-friendly data for the supervisor / budget agent

One-way only. For a round trip, call it twice (outbound, then return).

.env:
    IGNAV_API_KEY=...           # https://ignav.com (1,000 free requests)
    FLIGHT_PROVIDER=auto        # auto | ignav | google | mock
    FLIGHT_CURRENCY=USD         # used by the Google fallback

pip install airportsdata python-dotenv requests fast-flights
"""
import json
import os
import re
from datetime import date, timedelta

import airportsdata
import requests
from dotenv import load_dotenv

load_dotenv()

AIRPORTS = airportsdata.load("IATA")
IGNAV_URL = "https://ignav.com/api"
CURRENCY = os.getenv("FLIGHT_CURRENCY", "USD")
TIMEOUT = 25


# --------------------------------------------------------------------------- #
# 1. Place -> airport
# --------------------------------------------------------------------------- #
# Cities/countries with several airports -> the one travellers usually mean.
MAIN_AIRPORT = {
    # India
    "hyderabad": "HYD", "delhi": "DEL", "new delhi": "DEL", "mumbai": "BOM",
    "bangalore": "BLR", "bengaluru": "BLR", "chennai": "MAA", "kolkata": "CCU",
    "goa": "GOI", "kochi": "COK", "pune": "PNQ", "ahmedabad": "AMD", "jaipur": "JAI",
    # World cities
    "tokyo": "HND", "osaka": "KIX", "kyoto": "KIX", "seoul": "ICN", "beijing": "PEK",
    "shanghai": "PVG", "singapore": "SIN", "bangkok": "BKK", "kuala lumpur": "KUL",
    "dubai": "DXB", "doha": "DOH", "istanbul": "IST", "london": "LHR", "paris": "CDG",
    "rome": "FCO", "madrid": "MAD", "frankfurt": "FRA", "new york": "JFK",
    "los angeles": "LAX", "chicago": "ORD", "toronto": "YYZ", "sydney": "SYD",
    # Countries (best-guess main airport)
    "india": "DEL", "japan": "HND", "usa": "JFK", "united states": "JFK",
    "uk": "LHR", "united kingdom": "LHR", "uae": "DXB", "thailand": "BKK",
    "malaysia": "KUL", "indonesia": "CGK", "south korea": "ICN",
    "france": "CDG", "italy": "FCO", "spain": "MAD", "germany": "FRA",
    "australia": "SYD", "canada": "YYZ", "sri lanka": "CMB", "nepal": "KTM",
    "maldives": "MLE", "vietnam": "SGN", "turkey": "IST", "qatar": "DOH",
}
COUNTRY_WORDS = {
    "india", "japan", "usa", "united states", "uk", "united kingdom", "uae", "thailand",
    "malaysia", "indonesia", "south korea", "france", "italy", "spain", "germany",
    "australia", "canada", "sri lanka", "nepal", "maldives", "vietnam", "turkey", "qatar",
}


def resolve_airport(place: str):
    """Return {'iata','name','city','guessed'} or None.

    guessed=True means the place was a country or fuzzy match; the supervisor
    should confirm the airport with the user.
    """
    if not place or not place.strip():
        return None
    raw = place.strip()
    q = re.sub(r"\s+", " ", re.sub(r"[^a-z\s]", " ", raw.lower())).strip()

    def out(code, guessed=False):
        a = AIRPORTS[code]
        return {"iata": code, "name": a["name"], "city": a["city"], "guessed": guessed}

    # "NRT" typed in caps = IATA code ("Goa" is a city, "GOA" is Genoa)
    if raw.isupper() and len(raw) == 3 and raw in AIRPORTS:
        return out(raw)
    if q in MAIN_AIRPORT and MAIN_AIRPORT[q] in AIRPORTS:
        return out(MAIN_AIRPORT[q], guessed=q in COUNTRY_WORDS)
    if len(raw) == 3 and raw.upper() in AIRPORTS:
        return out(raw.upper())

    # City match from the airport database (prefer "international")
    best, best_score = None, -1
    for code, a in AIRPORTS.items():
        city, name = a["city"].lower(), a["name"].lower()
        score = 100 if city == q else 60 if (len(q) >= 4 and q in name) else 0
        if score:
            score += 20 if "international" in name else 0
            score -= 80 if any(w in name for w in ("heliport", "airfield", "air base")) else 0
            if score > best_score:
                best, best_score = code, score
    return out(best, guessed=True) if best else None


# --------------------------------------------------------------------------- #
# 2. Providers — each returns a list of offers (plain dicts)
#    offer = {price, currency, airline, flight_numbers, departure, arrival,
#             duration_min, stops, booking_url}
# --------------------------------------------------------------------------- #
class ProviderError(Exception):
    pass


def _first(d, *keys):
    if isinstance(d, dict):
        for k in keys:
            if d.get(k) not in (None, "", []):
                return d[k]
    return None


def search_ignav(o: str, d: str, day: str, limit: int):
    key = os.getenv("IGNAV_API_KEY")
    if not key:
        raise ProviderError("IGNAV_API_KEY not set")
    try:
        r = requests.post(
            f"{IGNAV_URL}/fares/one-way",
            headers={"X-Api-Key": key},
            json={"origin": o, "destination": d, "departure_date": day},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise ProviderError(f"Ignav unreachable: {e}")
    if r.status_code != 200:
        raise ProviderError(f"Ignav HTTP {r.status_code}: {r.text[:150]}")

    body = r.json()
    items = body if isinstance(body, list) else next(
        (body[k] for k in ("itineraries", "fares", "offers", "results", "data")
         if isinstance(body.get(k), list)), [])
    if items and os.getenv("FLIGHT_DEBUG"):
        print("RAW IGNAV ITEM:", json.dumps(items[0])[:1500])

    # Schema: https://ignav.com/docs/response-format
    offers = []
    for it in items:
        price = it.get("price") or {}
        amount = price.get("amount")
        if not amount:  # missing or 0 = placeholder, not a real fare
            continue
        out = it.get("outbound") or {}
        segs = out.get("segments") or []
        offers.append({
            "price": float(amount),
            "currency": price.get("currency"),
            "airline": out.get("carrier"),
            "flight_numbers": [
                f"{s.get('marketing_carrier_code') or ''}{s.get('flight_number') or ''}".strip()
                for s in segs
            ],
            "departure": segs[0].get("departure_time_local") if segs else None,
            "arrival": segs[-1].get("arrival_time_local") if segs else None,
            "duration_min": out.get("duration_minutes"),
            "stops": max(len(segs) - 1, 0),
            "cabin": it.get("cabin_class"),
            "self_transfer": it.get("requires_self_transfer", False),
            "price_status": price.get("status"),
            "booking_url": None,  # call get_booking_links(ignav_id) for the picked flight
            "ignav_id": it.get("ignav_id"),
        })
    return offers


def get_booking_links(ignav_id: str):
    """Booking URLs for one itinerary (costs 1 Ignav request). Returns a list of
    {provider, type, price, url}. Call it only for the flight the user picks."""
    key = os.getenv("IGNAV_API_KEY")
    if not key:
        return {"ok": False, "error": "IGNAV_API_KEY not set", "links": []}
    try:
        r = requests.post(f"{IGNAV_URL}/fares/booking-links", headers={"X-Api-Key": key},
                          json={"ignav_id": ignav_id}, timeout=TIMEOUT)
    except requests.RequestException as e:
        return {"ok": False, "error": f"Ignav unreachable: {e}", "links": []}
    if r.status_code != 200:
        return {"ok": False, "error": f"Ignav HTTP {r.status_code}: {r.text[:150]}", "links": []}
    links = []
    for opt in r.json().get("booking_options", []):
        for l in opt.get("links", []):
            links.append({
                "provider": l.get("provider_name"),
                "type": l.get("provider_type"),
                "price": (l.get("price") or {}).get("amount"),
                "url": l.get("url"),
            })
    return {"ok": True, "error": None, "links": links}


def search_google(o: str, d: str, day: str, limit: int, cabin: str, adults: int):
    """Fallback: Google Flights via the `fast-flights` library (unofficial, may break)."""
    try:
        from fast_flights import FlightQuery, Passengers, create_query, get_flights
    except ImportError:
        raise ProviderError("fast-flights not installed (pip install fast-flights)")

    q = create_query(
        flights=[FlightQuery(date=day, from_airport=o, to_airport=d)],
        seat=cabin,
        trip="one-way",
        passengers=Passengers(adults=adults),
        currency=CURRENCY,
    )
    try:
        results = get_flights(q)
    except Exception as e:  # library raises several kinds of errors
        raise ProviderError(f"Google Flights fallback failed: {e}")

    offers = []
    for r in results:
        legs = r.flights
        if not legs:
            continue
        fmt = lambda s: f"{s.date[0]:04d}-{s.date[1]:02d}-{s.date[2]:02d}T{s.time[0]:02d}:{s.time[1]:02d}"
        offers.append({
            "price": float(r.price),
            "currency": CURRENCY,
            "airline": ", ".join(r.airlines),
            "flight_numbers": [],
            "departure": fmt(legs[0].departure),
            "arrival": fmt(legs[-1].arrival),
            "duration_min": sum(l.duration for l in legs),
            "stops": len(legs) - 1,
            "booking_url": q.url(),
        })
    return offers[:limit * 3]


def search_mock(o: str, d: str, day: str, limit: int):
    """Fake data so you can build/test your graph without API calls."""
    base = 150 + sum(map(ord, o + d)) % 300
    airlines = ["IndiGo", "Air India", "Emirates", "Singapore Airlines", "Qatar Airways", "ANA"]
    # (extra price, duration in minutes, stops): cheap+slow ... fast+pricey
    shapes = [(0, 780, 2), (60, 480, 1), (160, 330, 0), (90, 420, 1), (40, 600, 2), (120, 360, 0)]
    return [{
        "price": float(base + extra),
        "currency": "USD",
        "airline": airlines[i % len(airlines)],
        "flight_numbers": [f"XX{100 + i}"],
        "departure": f"{day}T{5 + i * 3:02d}:30",
        "arrival": None,
        "duration_min": dur,
        "stops": stops,
        "booking_url": None,
    } for i, (extra, dur, stops) in enumerate(shapes)]


# --------------------------------------------------------------------------- #
# 3. Ranking
# --------------------------------------------------------------------------- #
def rank_offers(offers: list, top_n: int = 3) -> dict:
    """cheapest / fastest / best_value + a short list of options."""
    offers = [o for o in offers if o.get("price") is not None]
    if not offers:
        return {}
    timed = [o for o in offers if o.get("duration_min")]
    min_price = min(o["price"] for o in offers)
    min_dur = min((o["duration_min"] for o in timed), default=None)

    def value_score(o):  # lower is better: price matters most, then time, then stops
        score = o["price"] / min_price
        if min_dur and o.get("duration_min"):
            score += 0.5 * o["duration_min"] / min_dur
        score += 0.3 * (o.get("stops") or 0)
        return score

    cheapest = min(offers, key=lambda o: o["price"])
    fastest = min(timed, key=lambda o: (o["duration_min"], o["price"])) if timed else None
    best_value = min(offers, key=value_score)

    shortlist, seen = [], set()
    for o in sorted(offers, key=lambda o: o["price"]):
        k = (o["airline"], o["departure"], o["price"])
        if k not in seen:
            seen.add(k)
            shortlist.append(o)
    return {
        "cheapest": cheapest,
        "fastest": fastest,
        "best_value": best_value,
        "options": shortlist[:top_n],
    }


# --------------------------------------------------------------------------- #
# 4. The tool your agent calls
# --------------------------------------------------------------------------- #
def search_flights(origin: str, destination: str, departure_date: str,
                   adults: int = 1, cabin: str = "economy", top_n: int = 3) -> dict:
    """
    Find and rank one-way flights.

    origin / destination: city, country, airport name or IATA code
    departure_date: YYYY-MM-DD
    cabin: economy | premium-economy | business | first
    Returns {"ok", "data", "error", "notes"}. For a round trip, call twice.
    """
    notes = []

    try:
        day = date.fromisoformat(departure_date)
    except (ValueError, TypeError):
        return _fail("departure_date must be YYYY-MM-DD")
    if day < date.today():
        return _fail("departure_date is in the past")

    o, d = resolve_airport(origin), resolve_airport(destination)
    if not o:
        return _fail(f"Could not find an airport for origin '{origin}'. Ask the user for a city or IATA code.")
    if not d:
        return _fail(f"Could not find an airport for destination '{destination}'. Ask the user for a city or IATA code.")
    if o["iata"] == d["iata"]:
        return _fail("Origin and destination are the same airport.")
    for label, raw, p in (("origin", origin, o), ("destination", destination, d)):
        if p["guessed"]:
            notes.append(f"{label} '{raw}' -> {p['iata']} ({p['name']}); confirm with the user if another airport is preferred.")

    # Pick provider(s) in order
    mode = os.getenv("FLIGHT_PROVIDER", "auto").lower()
    attempts = {
        "ignav": [("ignav", lambda: search_ignav(o["iata"], d["iata"], departure_date, top_n))],
        "google": [("google", lambda: search_google(o["iata"], d["iata"], departure_date, top_n, cabin, adults))],
        "mock": [("mock", lambda: search_mock(o["iata"], d["iata"], departure_date, top_n))],
        "auto": [
            ("ignav", lambda: search_ignav(o["iata"], d["iata"], departure_date, top_n)),
            ("google", lambda: search_google(o["iata"], d["iata"], departure_date, top_n, cabin, adults)),
        ],
    }.get(mode)
    if attempts is None:
        return _fail("FLIGHT_PROVIDER must be auto, ignav, google or mock")

    offers, source = [], None
    for name, run in attempts:
        try:
            offers = run()
            if offers:
                source = name
                break
            notes.append(f"{name}: no results")
        except ProviderError as e:
            notes.append(f"{name} failed: {e}")
    if not offers:
        return _fail("No flights found. " + " | ".join(notes))

    ranked = rank_offers(offers, top_n)
    if not ranked:
        return _fail("Flights were found but none had a usable price. " + " | ".join(notes))
    if adults > 1:
        notes.append("Prices are per person; multiply by passengers for the total.")

    return {
        "ok": True,
        "error": None,
        "notes": notes,
        "data": {
            "route": {"from": o, "to": d},
            "date": departure_date,
            "source": source,
            **ranked,
        },
    }


def _fail(msg):
    return {"ok": False, "data": None, "error": msg, "notes": []}


# --------------------------------------------------------------------------- #
# Optional: LangChain / LangGraph tool (works only if langchain-core is installed)
# --------------------------------------------------------------------------- #
try:
    from langchain_core.tools import tool

    @tool
    def flight_search_tool(origin: str, destination: str, departure_date: str,
                           adults: int = 1, cabin: str = "economy") -> str:
        """Find the cheapest, fastest and best-value one-way flights.
        origin/destination: city, country or IATA code. departure_date: YYYY-MM-DD.
        For a round trip call this twice (outbound, then return)."""
        return json.dumps(search_flights(origin, destination, departure_date, adults, cabin))

    FLIGHT_TOOLS = [flight_search_tool]
except ImportError:
    FLIGHT_TOOLS = []