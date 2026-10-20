from pydantic import BaseModel, Field
from typing import List


class HotelResult(BaseModel):
    hotel_name: str = Field(description="The name of the hotel")
    price: str = Field(description="The price of the hotel")
    rating: str = Field(description="The rating of the hotel")
    address: str = Field(description="The address of the hotel")
    amenities: List[str] = Field(description="The amenities of the hotel")
    description: str = Field(description="The description of the hotel")
    url: str = Field(description="The url of the hotel")
