"""
agent.py — All the agents live here.

Each run_*_agent() function does one agent's job: it takes plain inputs
(strings) and returns plain output (a string). It knows nothing about the
graph or state. nodes.py wraps these for LangGraph.
"""
import os
import certifi
from dotenv import load_dotenv

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from app.tools.tavily_tool import tavily_search
from app.tools.flight_tool import search_flights


# =========================
# LLM
# =========================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is missing. Please add it to your .env file.")

llm = ChatGroq(
    model="openai/gpt-oss-120b",
    api_key=GROQ_API_KEY
)


# =========================
# Flight Agent
# =========================

class TripParams(BaseModel):
    """Trip details extracted from the user's message. Leave a field null if the user didn't say it."""
    origin: Optional[str] = Field(None, description="City or airport the user departs from")
    destination: Optional[str] = Field(None, description="City or country the user travels to")
    departure_date: Optional[str] = Field(None, description="Outbound date as YYYY-MM-DD")
    return_date: Optional[str] = Field(None, description="Return date as YYYY-MM-DD, null if one-way or not given")


def _fmt_offer(label: str, o: dict | None) -> str:
    if not o:
        return f"- {label}: not available"
    mins = o.get("duration_min")
    dur = f"{mins // 60}h{mins % 60:02d}m" if mins else "duration unknown"
    stops = "nonstop" if o.get("stops") == 0 else f"{o.get('stops')} stop(s)"
    flight = ", ".join(o.get("flight_numbers") or []) or "n/a"
    return (f"- {label}: {o.get('airline') or 'Unknown airline'} ({flight}), "
            f"{o['price']:.0f} {o.get('currency') or ''} per person, {dur}, {stops}, "
            f"departs {o.get('departure') or 'n/a'}")


def _summarize_flights(title: str, res: dict) -> str:
    """Turn the flight tool's dict into short text for the LLM prompts (saves tokens)."""
    if not res["ok"]:
        return f"{title}: no flight data. Reason: {res['error']}"
    d = res["data"]
    lines = [f"{title}: {d['route']['from']['iata']} -> {d['route']['to']['iata']} on {d['date']}"]
    lines += [
        _fmt_offer("Cheapest", d["cheapest"]),
        _fmt_offer("Fastest", d["fastest"]),
        _fmt_offer("Best value", d["best_value"]),
    ]
    lines += [f"- Note: {n}" for n in res["notes"]]
    return "\n".join(lines)


def run_flight_agent(user_query: str) -> str:
    # 1) LLM extracts structured trip details from the user's message
    extractor = llm.with_structured_output(TripParams)
    trip = extractor.invoke([
        SystemMessage(content=(
            f"Extract trip details. Today's date is {date.today().isoformat()}. "
            "Convert relative dates to YYYY-MM-DD. Never guess missing values; use null."
        )),
        HumanMessage(content=user_query),
    ])

    # 2) Plain Python calls the flight tool (no LLM needed here)
    missing = [k for k in ("origin", "destination", "departure_date") if not getattr(trip, k)]
    if missing:
        return (
            "No flights searched. Missing details: " + ", ".join(missing) +
            ". Ask the user for them."
        )

    parts = [_summarize_flights(
        "Outbound", search_flights(trip.origin, trip.destination, trip.departure_date)
    )]
    if trip.return_date:  # the tool is one-way, so search the return leg separately
        parts.append(_summarize_flights(
            "Return", search_flights(trip.destination, trip.origin, trip.return_date)
        ))
    return "\n\n".join(parts)




# =========================
# Hotel Agent
# =========================
 
def run_hotel_agent(user_query: str) -> str:
    return tavily_search(f"Best hotels for {user_query}")
 
 
# =========================
# Itinerary Agent
# =========================
 
def run_itinerary_agent(user_query: str, flight_results: str, hotel_results: str) -> str:
    prompt = f"""
Create a complete travel itinerary.
 
User Query:
{user_query}
 
Flight Results:
{flight_results}
 
Hotel Results:
{hotel_results}
 
Make the itinerary practical, budget-aware, and easy to follow.
"""
 
    response = llm.invoke([
        SystemMessage(content="You are an expert travel planner."),
        HumanMessage(content=prompt)
    ])
    return response.content
 
 
# =========================
# Final Response Agent
# =========================
 
def run_final_agent(user_query: str, flight_results: str, hotel_results: str, itinerary: str) -> str:
    final_prompt = f"""
Generate the final travel response for the user.
 
User Request:
{user_query}
 
Flights:
{flight_results}
 
Hotels:
{hotel_results}
 
Itinerary:
{itinerary}
 
Format the final answer beautifully using these sections:
 
1. Trip Summary
2. Flight Information
3. Hotel Suggestions
4. Day-by-Day Itinerary
5. Estimated Budget
6. Final Recommendations
 
Important:
- Be clear and practical.
- Flight prices are per person and can change; tell the user to confirm before booking.
- If flight data is missing or shows an error, say so and ask for the missing details.
  Never invent flights or prices.
- Keep the response useful for real travel planning.
"""
 
    response = llm.invoke([
        SystemMessage(content="You are a professional AI travel booking assistant."),
        HumanMessage(content=final_prompt)
    ])
    return response.content
 