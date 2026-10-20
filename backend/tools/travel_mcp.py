"""旅行 MCP 服务。演示使用固定样本；真实查询使用现有 Exa / Google Flights。"""

import asyncio
from datetime import datetime, timezone
from typing import Literal

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pathlib import Path
import os

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
mcp = FastMCP("TripCraft travel tools")


@mcp.tool()
async def travel_search(
    kind: Literal["destination", "flight", "hotel", "dining"],
    destination: str,
    start: str,
    end: str,
    adults: int = 1,
    children: int = 0,
    rooms: int = 1,
    affordable: bool = False,
    departure: str = "",
) -> dict:
    """查询旅行资料。flight 的 departure/destination 应为 IATA 代码；价格须注明币种与来源。"""
    if min(adults, rooms) < 1 or children < 0:
        raise ValueError("人数和房间数不合法")
    now = datetime.now(timezone.utc).isoformat()
    if os.getenv("TRIPCRAFT_DEMO") == "1":
        samples = {
            "flight": {"name": "演示往返航班", "unit_price": 900, "currency": "CNY"},
            "hotel": {
                "name": "演示经济酒店" if affordable else "演示高档酒店",
                "unit_price": 550 if affordable else 1400,
                "currency": "CNY",
            },
            "dining": {"name": "演示每日餐饮", "unit_price": 120, "currency": "CNY"},
            "destination": {"name": "演示景点", "unit_price": 180, "currency": "CNY"},
        }
        return {
            **samples[kind],
            "source": f"fixture://{kind}",
            "queried_at": now,
            "demo": True,
            "destination": destination,
        }

    if kind == "flight":
        from fast_flights import FlightData, Passengers, get_flights

        def search():
            result = get_flights(
                flight_data=[
                    FlightData(
                        date=start, from_airport=departure, to_airport=destination
                    )
                ],
                trip="one-way",
                seat="economy",
                passengers=Passengers(
                    adults=adults,
                    children=children,
                    infants_in_seat=0,
                    infants_on_lap=0,
                ),
                fetch_mode="fallback",
            )
            return str(result.flights)

        content = await asyncio.wait_for(asyncio.to_thread(search), 30)
        return {
            "content": content,
            "source": "https://www.google.com/travel/flights",
            "queried_at": now,
        }

    from exa_py import Exa

    price_filter = "budget affordable" if affordable else ""
    query = f"{destination} {kind} {start} {end} {price_filter} prices currency sources"
    result = await asyncio.wait_for(
        asyncio.to_thread(
            Exa(api_key=os.environ["EXA_API_KEY"]).search_and_contents,
            query,
            num_results=4,
            text={"max_characters": 1800},
        ),
        30,
    )
    places = []
    for place in result.results:
        places.append({"title": place.title, "url": place.url, "text": place.text})
    return {"results": places, "queried_at": now, "demo": False}


if __name__ == "__main__":
    mcp.run(transport="stdio")
