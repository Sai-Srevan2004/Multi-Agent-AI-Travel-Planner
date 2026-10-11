import asyncio

from app.workflow.graph import init_graph, run_travel_agent


async def main():
    travel_graph, pool = await init_graph()

    res = await run_travel_agent(
        travel_graph,
        "Plan a 5 day budget trip from Hyderabad to Dubai, leaving 20 Nov 2026 and returning 25 Nov 2026",
    )

    print("thread_id  :", res["thread_id"])
    print("llm_calls  :", res["llm_calls"])
    print("\n--- FLIGHTS ---\n", res["flight_results"])
    print("\n--- HOTELS ---\n", res["hotel_results"])
    print("\n--- ITINERARY ---\n", res["itinerary"])
    print("\n--- FINAL ANSWER ---\n", res["answer"])

    pool.close()
    await pool.wait_closed()


asyncio.run(main())