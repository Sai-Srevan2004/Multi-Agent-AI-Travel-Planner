from app.tools.flight_tool import search_flights, get_booking_links

res = search_flights("Hyderabad", "London", "2026-11-20")
print(res)
print("\n==========================================\n")
pick = res["data"]["best_value"]
print(get_booking_links(pick["ignav_id"]))