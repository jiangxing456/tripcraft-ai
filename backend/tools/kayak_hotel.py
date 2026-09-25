from config.logger import logger_hook   # 工具调用钩子，签名 (function_name, function_call, arguments)，负责打印入参/返回值
from agno.tools import tool             # Agno 的工具装饰器，把普通函数注册成 Agent 可调用的 tool
from models.hotel import HotelSearchRequest  # 请求体校验模型（Pydantic），保证入参类型与格式合法
from loguru import logger               # 日志器，本文件内直接输出请求与生成的 URL

# 注册为 Agent 可调用的工具：
# - name：暴露给大模型的工具名，模型按此名称发起调用
# - show_result：把工具返回结果一并展示在 Agent 输出中
# - tool_hooks：调用前后执行 logger_hook，用于打印/记录工具调用日志
@tool(
    name="kayak_hotel_url_generator",
    show_result=True,
    tool_hooks=[logger_hook]
)
def kayak_hotel_url_generator(
    destination: str, check_in: str, check_out: str, adults: int = 1, children: int = 0, rooms: int = 1, sort: str = "recommended"
) -> str:
    """
    Generates a Kayak URL for hotels in the specified destination between check_in and check_out dates.

    该工具不做真实的爬取，只是按 Kayak 的 URL 规则拼出一条可直接打开的酒店搜索链接。

    :param destination: The destination city or area (e.g. "Berlin", "City Center, Singapore", "Red Fort, Delhi")
    :param check_in: The date of check-in in the format 'YYYY-MM-DD'
    :param check_out: The date of check-out in the format 'YYYY-MM-DD'
    :param adults: The number of adults (default 1)
    :param children: The number of children (default 0)
    :param rooms: The number of rooms (default 1)
    :param sort: The sort order (recommended, distance, price, rating)
    :return: The Kayak URL for the hotel search
    """
    # 组装请求对象（Pydantic 模型），便于校验与统一日志输出
    request = HotelSearchRequest(
        destination=destination,
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        children=children,
        rooms=rooms,
        sort=sort)

    logger.info(f"Request: {request}")

    logger.info(f"Generating Kayak URL for {destination} on {check_in} to {check_out}")
    # 基础路径：/hotels/{目的地}/{入住日期}/{退房日期}
    URL = f"https://www.kayak.com/hotels/{destination}/{check_in}/{check_out}"
    # 人数段：成人必填，儿童/房间数仅在大于阈值时拼接
    URL += f"/{adults}adults"
    if children > 0:
        URL += f"/{children}children"

    if rooms > 1:
        URL += f"/{rooms}rooms"


    # 查询参数：固定美元计价
    URL += "?currency=USD"
    # 排序参数映射：Kayak 的排序取值与入参不同名，需做一次转换
    if sort.lower() == "price":
        URL += "&sort=price_a"       # 价格从低到高
    elif sort.lower() == "rating":
        URL += "&sort=userrating_b"  # 用户评分优先
    elif sort.lower() == "distance":
        URL += "&sort=distance_a"    # 距离由近到远
    # "recommended"（推荐）为 Kayak 默认排序，无需追加参数
    logger.info(f"URL: {URL}")
    return URL
