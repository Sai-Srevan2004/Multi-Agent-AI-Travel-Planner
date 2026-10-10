
"""
graph.py — Builds and compiles the graph, and exposes run_travel_agent() for FastAPI.
"""

import uuid

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage

from app.workflow.state import TravelState
from app.workflow.nodes import flight_node
from app.workflow.nodes import hotel_node
from app.workflow.nodes import itinerary_node
from app.workflow.nodes import final_node
from app.db import get_checkpointer


# =========================
# Build Graph
# =========================

graph = StateGraph(TravelState)

graph.add_node("flight_agent", flight_node)
graph.add_node("hotel_agent", hotel_node)
graph.add_node("itinerary_agent", itinerary_node)
graph.add_node("final_agent", final_node)
 
graph.add_edge(START, "flight_agent")
graph.add_edge("flight_agent", "hotel_agent")
graph.add_edge("hotel_agent", "itinerary_agent")
graph.add_edge("itinerary_agent", "final_agent")
graph.add_edge("final_agent", END)


# =========================
# Database Checkpointer
# =========================

checkpointer = get_checkpointer()

travel_graph = graph.compile(checkpointer=checkpointer)


# =========================
# Run Travel Agent
# =========================

def run_travel_agent(user_input: str, thread_id: str | None = None):
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    result = travel_graph.invoke(
        {
            "messages": [
                HumanMessage(content=user_input)
            ],
            "user_query": user_input,
            "flight_results": "",
            "hotel_results": "",
            "itinerary": "",
            "llm_calls": 0
        },
        config=config
    )

    final_answer = result["messages"][-1].content

    return {
        "thread_id": thread_id,
        "answer": final_answer,
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "itinerary": result.get("itinerary", ""),
        "llm_calls": result.get("llm_calls", 0),
    }
