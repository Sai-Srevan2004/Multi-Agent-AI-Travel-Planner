"""
graph.py — Builds and compiles the graph, and exposes run_travel_agent() for FastAPI.
"""
import uuid

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.mysql.aio import AIOMySQLSaver
from langchain_core.messages import HumanMessage

from app.workflow.state import TravelState
from app.workflow.nodes import (
    flight_node,
    hotel_node,
    itinerary_node,
    final_node,
)
from app.db import create_pool


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
# Compile (async; state is saved to MySQL through a connection pool)
# =========================

async def init_graph():
    """Call once at app startup. Returns (compiled_graph, pool). Close the pool on shutdown."""
    pool = await create_pool()
    checkpointer = AIOMySQLSaver(pool)
    await checkpointer.setup()  # creates the checkpoint tables if they don't exist
    return graph.compile(checkpointer=checkpointer), pool


# =========================
# Function for FastAPI
# =========================

async def run_travel_agent(travel_graph, user_input: str, thread_id: str | None = None):
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    result = await travel_graph.ainvoke(
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