from datetime import date, timedelta
from pydantic import BaseModel, Field, model_validator
from typing import List
from models.hotel import HotelResult


class TravelDates(BaseModel):
    start: str = Field(min_length=10, max_length=40)
    end: str = ""  # 结束日期


class TravelPlanRequest(BaseModel):
    user_id: str = ""  # 用户标识，用于长期记忆；为空则跳过记忆功能（向后兼容）
    name: str = ""
    destination: str = Field(min_length=1, max_length=100)
    starting_location: str = Field(min_length=1, max_length=100)
    travel_dates: TravelDates
    date_input_type: str = "picker"
    duration: int = Field(default=1, ge=1, le=14)
    traveling_with: str = ""
    adults: int = Field(default=1, ge=1, le=20)
    children: int = Field(default=0, ge=0, le=20)
    age_groups: List[str] = []
    budget: int = Field(default=75000, gt=0, le=10_000_000)
    budget_currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    travel_style: str = ""
    budget_flexible: bool = False
    vibes: List[str] = []
    priorities: List[str] = []
    interests: str = ""
    rooms: int = Field(default=1, ge=1, le=20)
    pace: List[int] = [3]
    been_there_before: str = ""
    loved_places: str = ""
    additional_info: str = ""

    @model_validator(mode="after")
    def check_dates(self):
        start = date.fromisoformat(self.travel_dates.start[:10])
        end = start + timedelta(days=self.duration - 1)
        if (
            self.travel_dates.end
            and date.fromisoformat(self.travel_dates.end[:10]) != end
        ):
            raise ValueError("结束日期与旅行天数不一致")
        self.travel_dates.start = start.isoformat()
        self.travel_dates.end = end.isoformat()
        return self


class TravelPlanAgentRequest(BaseModel):
    trip_plan_id: str
    travel_plan: TravelPlanRequest


class TravelPlanResponse(BaseModel):
    success: bool
    message: str
    trip_plan_id: str


class DayByDayPlan(BaseModel):
    day: int = Field(
        default=0, description="The day number in the itinerary, starting from 0"
    )
    date: str = Field(
        default="", description="The date for this day in YYYY-MM-DD format"
    )
    morning: str = Field(
        default="", description="Description of morning activities and plans"
    )
    afternoon: str = Field(
        default="", description="Description of afternoon activities and plans"
    )
    evening: str = Field(
        default="", description="Description of evening activities and plans"
    )
    notes: str = Field(
        default="",
        description="Additional tips, reminders or important information for the day",
    )


class Attraction(BaseModel):
    name: str = Field(default="", description="Name of the attraction")
    description: str = Field(
        default="", description="Detailed description of the attraction"
    )


class FlightResult(BaseModel):
    duration: str = Field(default="", description="Duration of the flight")
    price: str = Field(
        default="", description="Price of the flight in the local currency"
    )
    departure_time: str = Field(default="", description="Departure time of the flight")
    arrival_time: str = Field(default="", description="Arrival time of the flight")
    airline: str = Field(default="", description="Airline of the flight")
    flight_number: str = Field(default="", description="Flight number of the flight")
    url: str = Field(default="", description="Website or booking URL for the flight")
    stops: int = Field(default=0, description="Number of stops in the flight")


class RestaurantResult(BaseModel):
    name: str = Field(default="", description="Name of the restaurant")
    description: str = Field(default="", description="Description of the restaurant")
    location: str = Field(default="", description="Location of the restaurant")
    url: str = Field(
        default="", description="Website or booking URL for the restaurant"
    )


class TravelPlanTeamResponse(BaseModel):
    day_by_day_plan: List[DayByDayPlan] = Field(
        description="A list of day-by-day plans for the trip"
    )
    hotels: List[HotelResult] = Field(description="A list of hotels for the trip")
    attractions: List[Attraction] = Field(
        description="A list of recommended attractions for the trip"
    )
    flights: List[FlightResult] = Field(description="A list of flights for the trip")
    restaurants: List[RestaurantResult] = Field(
        description="A list of recommended restaurants for the trip"
    )
    budget_insights: List[str] = Field(
        description="A list of budget insights for the trip"
    )
    tips: List[str] = Field(
        description="A list of tips or recommendations for the trip"
    )
