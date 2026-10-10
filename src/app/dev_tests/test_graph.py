from app.workflow.graph import run_travel_agent

res = run_travel_agent(
    "Plan a 5 day budget trip from Hyderabad to Amsterdam, leaving 9 Nov 2026 and returning 25 Nov 2026"
)

print("thread_id  :", res["thread_id"])
print("llm_calls  :", res["llm_calls"])
print("\n--- FLIGHTS ---\n", res["flight_results"])
print("\n--- HOTELS ---\n", res["hotel_results"])
print("\n--- ITINERARY ---\n", res["itinerary"])
print("\n--- FINAL ANSWER ---\n", res["answer"])