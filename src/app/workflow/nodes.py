"""
nodes.py — All LangGraph nodes.

A node reads the state, calls an agent from agent.py,
and returns the part of the state it wants to update.
"""
from langchain_core.messages import AIMessage

from app.workflow.state import TravelState
from app.workflow.agents import (
    run_flight_agent,
    run_hotel_agent,
    run_itinerary_agent,
    run_final_agent
)


# =========================
# Nodes
# =========================

def flight_node(state: TravelState):
    flight_results = run_flight_agent(state["user_query"])

    return {
        "flight_results": flight_results,
        "messages": [AIMessage(content="Flight results fetched.")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }



def hotel_node(state: TravelState):
    hotel_results = run_hotel_agent(state["user_query"])
 
    return {
        "hotel_results": hotel_results,
        "messages": [AIMessage(content="Hotel information fetched.")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }
 
 
def itinerary_node(state: TravelState):
    itinerary = run_itinerary_agent(
        state["user_query"],
        state["flight_results"],
        state["hotel_results"],
    )
 
    return {
        "itinerary": itinerary,
        "messages": [AIMessage(content=itinerary)],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }
 
 
def final_node(state: TravelState):
    answer = run_final_agent(
        state["user_query"],
        state["flight_results"],
        state["hotel_results"],
        state["itinerary"],
    )
 
    return {
        "messages": [AIMessage(content=answer)],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }
 