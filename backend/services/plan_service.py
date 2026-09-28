"""
旅行计划服务层 —— 整个项目的业务主流程。
"""

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone

from loguru import logger

# 6 个专职 Agent
from agents.destination import destination_agent
from agents.flight import flight_agent
from agents.hotel import hotel_agent
from agents.dining import dining_agent
from agents.itinerary import itinerary_agent
from agents.budget import budget_agent
# 结构化转换：把 Markdown 转成 JSON
from agents.structured_output import convert_to_model
# 数据模型
from models.travel_plan import (
    TravelPlanAgentRequest,
    TravelPlanRequest,
    TravelPlanTeamResponse,
)
# 数据库操作
from repository.trip_plan_repository import (
    create_trip_plan_status,
    update_trip_plan_status,
    get_trip_plan_status,
    create_trip_plan_output,
    delete_trip_plan_outputs,
)


def _clip(text: str, limit: int = 1200) -> str:
    """把过长的文本裁到 limit 个字符以内，超出部分用 "..." 结尾。

    兜底逻辑里会把各 Agent 的长篇调研塞进 JSON 字段，不截断的话响应体会非常臃肿。
    """
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _shift_date(start: str, offset_days: int) -> str:
    """把开始日期往后推 offset_days 天；解析不了就原样返回。

    兜底模式下要给每一天一个递增的日期，但 start 是用户自由填写的字符串，
    未必是 "2026-10-01" 这种格式（也可能是 "next week" 或空串），
    所以解析失败时退回原值，保证兜底本身不会抛异常。
    """
    try:
        d = datetime.strptime(start, "%Y-%m-%d")
        return (d + timedelta(days=offset_days)).strftime("%Y-%m-%d")
    except Exception:
        return start


def _fallback_structured_response(
    request: TravelPlanRequest,
    destination_text: str,
    flight_text: str,
    hotel_text: str,
    dining_text: str,
    itinerary_text: str,
    budget_text: str,
) -> str:
    """确定性兜底：完全不依赖 AI 调用，按模板拼出一份合法的结构化 JSON。

    只在前面的 convert_to_model 连续失败时才会走到这里，
    目的是保证接口无论如何都能返回结构正确的数据，而不是直接报错。
    """
    # 天数兜底：确保至少 1 天，防止用户传 0 或 None 导致循环体不执行
    duration = max(int(request.duration or 1), 1)
    start = (request.travel_dates.start or "").strip()

    # ---- 逐日行程：只有第 1 天塞真实调研内容，其余天给通用描述 ----
    day_by_day_plan = []
    for i in range(duration):
        day_by_day_plan.append(
            {
                "day": i + 1,  # 从 1 开始编号
                # 日期按天递增；start 解析不了则退回原值（见 _shift_date）
                "date": _shift_date(start, i),
                # 只有第 1 天把行程调研的原文截断后填进上午
                "morning": _clip(itinerary_text, 400)
                if i == 0
                else f"Explore {request.destination} highlights.",
                "afternoon": f"Continue sightseeing and local experiences in {request.destination}.",
                "evening": f"Dinner and evening walk around {request.destination}.",
                # 第 1 天的备注里放预算摘要，其余天留空
                "notes": _clip(budget_text, 300) if i == 0 else "",
            }
        )

    # ---- 拼装完整 payload（字段必须与 TravelPlanTeamResponse 模型对齐）----
    payload = {
        "day_by_day_plan": day_by_day_plan,
        "hotels": [
            {
                "hotel_name": f"Recommended hotel in {request.destination}",
                "price": "See hotel research",
                "rating": "N/A",
                "address": request.destination or "",
                "amenities": [],
                # 酒店正文直接放调研原文（截断到 800 字）
                "description": _clip(hotel_text, 800),
                "url": "",
            }
        ],
        "attractions": [
            {
                "name": f"Top attractions in {request.destination}",
                # 景点详情放目的地调研原文（截断到 1000 字）
                "description": _clip(destination_text, 1000),
            }
        ],
        # 航班兜底不解析具体航班，只给占位字段
        "flights": [
            {
                "duration": "",
                "price": "See flight research",
                "departure_time": "",
                "arrival_time": "",
                "airline": "",
                "flight_number": "",
                "url": "",
                "stops": 0,
            }
        ],
        # 注意：这个 key 必须叫 restaurants —— 它是 TravelPlanTeamResponse 的字段名，
        # 也是前端 page.tsx 读的键（trip.itinerary.restaurants），属于「对外契约」，不能改
        "restaurants": [
            {
                "name": f"Recommended dining in {request.destination}",
                "description": _clip(dining_text, 800),
                "location": request.destination or "",
                "url": "",
            }
        ],
        # 预算洞察：优先用预算 Agent 的输出，为空时给一句提示语
        "budget_insights": [
            _clip(budget_text, 500) or "Budget details available in research notes."
        ],
        "tips": [
            # 第一条小贴士来自航班调研，第二条是固定的通用建议
            _clip(flight_text, 300) or "Check flight times before booking.",
            "Keep some buffer time between attractions and meals.",
        ],
    }

    # 用 Pydantic 校验一遍，确保下游拿到的永远是合法 JSON
    return TravelPlanTeamResponse.model_validate(payload).model_dump_json()


def travel_request_to_markdown(data: TravelPlanRequest) -> str:
    """把结构化的用户需求渲染成 Markdown，作为所有 Agent 的公共提示词上下文。

    关键设计：把 "relaxing"、"luxury" 这类生硬的枚举值翻译成自然语言描述，
    相当于帮模型「补充语义」，比直接丢 JSON 效果好很多。
    """

    # 旅行氛围（vibe）枚举 → 自然语言描述
    travel_vibes = {
        "relaxing": "a peaceful retreat focused on wellness, spa experiences, and leisurely activities",
        "adventure": "thrilling experiences including hiking, water sports, and adrenaline activities",
        "romantic": "intimate experiences with private dining, couples activities, and scenic spots",
        "cultural": "immersive experiences with local traditions, museums, and historical sites",
        "food-focused": "culinary experiences including cooking classes, food tours, and local cuisine",
        "nature": "outdoor experiences with national parks, wildlife, and scenic landscapes",
        "photography": "photogenic locations with scenic viewpoints, cultural sites, and natural wonders",
    }

    # 旅行档次（style）枚举 → 自然语言描述
    travel_styles = {
        "backpacker": "budget-friendly accommodations, local transportation, and authentic experiences",
        "comfort": "mid-range hotels, convenient transportation, and balanced comfort-value ratio",
        "luxury": "premium accommodations, private transfers, and exclusive experiences",
        "eco-conscious": "sustainable accommodations, eco-friendly activities, and responsible tourism",
    }

    # 行程节奏（pace，取值 0-5）→ 每天活动量的自然语言描述
    pace_levels = {
        0: "1-2 activities per day with plenty of free time and flexibility",
        1: "2-3 activities per day with significant downtime between activities",
        2: "3-4 activities per day with balanced activity and rest periods",
        3: "4-5 activities per day with moderate breaks between activities",
        4: "5-6 activities per day with minimal downtime",
        5: "6+ activities per day with back-to-back scheduling",
    }

    def format_date(date_str: str, is_picker: bool) -> str:
        """格式化日期：日期选择器传的是 ISO 字符串，需要转成 "June 01, 2025"；
        其余情况是用户手打的自由文本，直接返回。解析失败时安全降级，不让渲染崩掉。"""
        if not date_str:
            return "Not specified"
        if is_picker:
            try:
                # Python 3.11 之前的 fromisoformat 不认结尾的 "Z"，先换成 "+00:00"
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                return dt.strftime("%B %d, %Y")
            except ValueError:
                return date_str
        return date_str.strip()

    is_picker = data.date_input_type == "picker"
    start_date = format_date(data.travel_dates.start, is_picker)
    end_date = format_date(data.travel_dates.end, is_picker)
    # 有结束日期就渲染成 "between A and B"，否则只写开始日期
    date_range = (
        f"between {start_date} and {end_date}"
        if end_date and end_date != "Not specified"
        else start_date
    )

    # 把用户选的每个 vibe 枚举翻译成自然语言（未知值用 .get 兜底原样保留）
    vibes_descriptions = [travel_vibes.get(v, v) for v in data.vibes]

    # ---- 逐行拼装 Markdown（基础信息部分）----
    lines = [
        "# 🧳 Travel Plan Request",
        "",
        "## 📍 Trip Overview",
        # .title() 让姓名/城市名首字母大写，更符合英文书写习惯
        f"- **Traveler:** {data.name.title() if data.name else 'Unnamed Traveler'}",
        f"- **Route:** {data.starting_location.title()} → {data.destination.title()}",
        f"- **Duration:** {data.duration} days ({date_range})",
        "",
        "## 👥 Travel Group",
        f"- **Group Size:** {data.adults} adults, {data.children} children",
        f"- **Traveling With:** {data.traveling_with or 'Not specified'}",
        # 年龄组是列表，用逗号连接；空列表时给 "Not specified"
        f"- **Age Groups:** {', '.join(data.age_groups) or 'Not specified'}",
        f"- **Rooms Needed:** {data.rooms or 'Not specified'}",
        "",
        "## 💰 Budget & Preferences",
        f"- **Budget per person:** {data.budget} {data.budget_currency} ({'Flexible' if data.budget_flexible else 'Fixed'})",
        f"- **Travel Style:** {travel_styles.get(data.travel_style, data.travel_style or 'Not specified')}",
        # 节奏可能多选，逐个翻译后连接
        f"- **Preferred Pace:** {', '.join([pace_levels.get(p, str(p)) for p in data.pace]) or 'Not specified'}",
        "",
        "## ✨ Trip Preferences",
    ]

    # 旅行氛围：选了就用嵌套列表逐条列出，否则标注未指定
    if vibes_descriptions:
        lines.append("- **Travel Vibes:**")
        for vibe in vibes_descriptions:
            lines.append(f"  - {vibe}")
    else:
        lines.append("- **Travel Vibes:** Not specified")

    # 下面两个是可选的自由文本，用户填了才追加
    if data.priorities:
        lines.append(f"- **Top Priorities:** {', '.join(data.priorities)}")
    if data.interests:
        lines.append(f"- **Interests:** {data.interests}")

    # ---- 追加「目的地背景」板块 ----
    lines.extend(
        [
            "",
            "## 🗺️ Destination Context",
            # 注意：.capitalize() 会把其余字母全部小写（"New York" → "New york"），
            # 想保留原样可以改用 .title()
            f"- **Previous Visit:** {data.been_there_before.capitalize() if data.been_there_before else 'Not specified'}",
            f"- **Loved Places:** {data.loved_places or 'Not specified'}",
            f"- **Additional Info:** {data.additional_info or 'Not specified'}",
        ]
    )

    return "\n".join(lines)


async def generate_travel_plan(request: TravelPlanAgentRequest) -> str:
    """【核心入口】生成旅行计划并落库，由 API 层在后台任务中调用。

    流程：确保状态记录存在 → 标为 processing → 渲染需求 Markdown
         → 依次跑完 6 个 Agent → 结构化转换（失败则兜底）
         → 覆盖式落库 → 标记 completed。

    任何异常都会把状态标为 failed 并记录错误信息，然后原样抛出。
    """
    trip_plan_id = request.trip_plan_id
    logger.info(f"Generating travel plan for tripPlanId: {trip_plan_id}")

    # ---- 第 1 步：确保状态记录存在（幂等处理，避免重复生成时报错）----
    if not await get_trip_plan_status(trip_plan_id):
        await create_trip_plan_status(trip_plan_id=trip_plan_id, status="pending")

    # ---- 第 2 步：状态推进到 processing，并记录开始时间 ----
    await update_trip_plan_status(
        trip_plan_id=trip_plan_id,
        status="processing",
        current_step="Initializing travel plan generation",
        started_at=datetime.now(timezone.utc),
    )

    try:
        # 渲染公共上下文：所有 Agent 的提示词里都会带上它
        travel_request_md = travel_request_to_markdown(request.travel_plan)
        logger.info(f"Travel request markdown:\n{travel_request_md}")

        await update_trip_plan_status(
            trip_plan_id=trip_plan_id,
            status="processing",
            current_step="Generating plan with TripCraft AI agents",
        )

        # 累积变量：存放所有 Agent 输出的拼接结果（后面的 Agent 依赖它）
        last_response_content = ""
        # 记录开始时间，最后统计整个流程耗时
        time_start = time.time()

        # =====================================================================
        # 第 3 步：调用 6 个 Agent
        #   前 4 个（目的地 / 航班 / 酒店 / 餐厅）只依赖同一份用户需求，彼此互不依赖
        #       → 用 asyncio.gather 同时跑，省掉互相等待的时间
        #   后 2 个（逐日行程 / 预算）要吃前面累积的结果
        #       → 必须等前面全部跑完，保持串行
        # =====================================================================

        # ---- 3.1~3.4 前 4 个 Agent：并发执行 ----
        # 先把 4 段提示词准备好（内容与原来完全一致，只是提前存成变量，
        # 这样它们能一起被 gather 发出去）
        destination_prompt = f"""
            Please research about the destination {request.travel_plan.destination}

            Below are user's travel request:
            {travel_request_md}

            Provide a very detailed research about the destination, its attractions, activities, and other relevant information that user might be interested in.

            Give 10 attractions/activities that user might be interested in.
            """
        flight_prompt = f"""
            Please find flights according to the user's travel request:
            {travel_request_md}

            If user has not specified the exact flight date, please consider it by yourself based on the user's travel request.

            Provide a very detailed research about the flights, its price, duration, and other relevant information that user might be interested in.

            Give top 5 flights.
            """
        hotel_prompt = f"""
            Please find hotels according to the user's travel request:
            {travel_request_md}

            If user has not specified the exact hotel dates, please consider it by yourself based on the user's travel request.

            Provide a very detailed research about the hotels, its price, amenities, and other relevant information that user might be interested in.

            Give top 5 hotels.
            """
        dining_prompt = f"""
            Please find restaurants according to the user's travel request:
            {travel_request_md}

            If user has not specified the exact restaurant dates, please consider it by yourself based on the user's travel request.

            Provide a very detailed research about the restaurants, its price, menu, and other relevant information that user might be interested in.

            Give top 5 restaurants.
            """

        # 进度只更新一次：4 个是同时在跑的，没法再细分到「正在搜航班」
        # （这是并发的代价：用速度换掉了细粒度进度显示）
        await update_trip_plan_status(
            trip_plan_id=trip_plan_id,
            status="processing",
            current_step="Researching destination, flights, hotels and restaurants",
        )

        # asyncio.gather：同时把 4 个请求发出去，等它们全部跑完
        # 返回值按括号里的先后顺序装成一个元组，所以左边能一一对应接住
        (
            destination_search_response,
            flight_search_response,
            hotel_search_response,
            dining_search_response,
        ) = await asyncio.gather(
            destination_agent.arun(destination_prompt),
            flight_agent.arun(flight_prompt),
            hotel_agent.arun(hotel_prompt),
            dining_agent.arun(dining_prompt),
        )

        # 4 个都跑完之后，再按固定顺序拼进累积文本
        # （顺序必须固定，因为后面的行程/预算 Agent 要读这段累积结果）
        logger.info(
            f"Destination research response: {destination_search_response.messages[-1].content}"
        )
        last_response_content = f"""
        ## Destination Attractions:
        ---
        {destination_search_response.messages[-1].content}
        ---
        """

        logger.info(
            f"Flight search response: {flight_search_response.messages[-1].content}"
        )
        last_response_content += f"""
        ## Flight recommendations:
        ---
        {flight_search_response.messages[-1].content}
        ---
        """

        logger.info(
            f"Hotel search response: {hotel_search_response.messages[-1].content}"
        )
        last_response_content += f"""
        ## Hotel recommendations:
        ---
        {hotel_search_response.messages[-1].content}
        ---
        """

        logger.info(
            f"Restaurant search response: {dining_search_response.messages[-1].content}"
        )
        last_response_content += f"""
        ## Restaurant recommendations:
        ---
        {dining_search_response.messages[-1].content}
        ---
        """

        # ---- 3.5 生成逐日行程 ----
        # 关键点：这里把前面 4 个 Agent 的累积输出（last_response_content）作为输入，
        # 保证行程是基于真实调研结果编排的，而不是模型凭空生成
        await update_trip_plan_status(
            trip_plan_id=trip_plan_id,
            status="processing",
            current_step="Creating the day-by-day itinerary",
        )
        itinerary_response = await itinerary_agent.arun(
            f"""
            Please create a detailed day-by-day itinerary for a trip to {request.travel_plan.destination}  for user's travel request:
            {travel_request_md}

            Based on the following information:
            {last_response_content}
            """
        )
        logger.info(f"Itinerary response: {itinerary_response.messages[-1].content}")

        last_response_content += f"""
        ## Day-by-day itinerary:
        ---
        {itinerary_response.messages[-1].content}
        ---
        """

        # ---- 3.6 预算优化 ----
        # 同样依赖前面所有 Agent 的累积输出（尤其是行程与航班酒店价格）
        await update_trip_plan_status(
            trip_plan_id=trip_plan_id,
            status="processing",
            current_step="Optimizing the budget",
        )
        budget_response = await budget_agent.arun(
            f"""
            Please optimize the budget according to the user's travel request:
            {travel_request_md}

            Based on the following information:
            {last_response_content}
            """
        )
        logger.info(f"Budget response: {budget_response.messages[-1].content}")

        last_response_content += f"""
        ## Budget optimization:
        ---
        {budget_response.messages[-1].content}
        ---
        """

        # 统计并记录整个 Agent 编排阶段的总耗时
        time_end = time.time()
        logger.info(f"Total time taken: {time_end - time_start:.2f} seconds")

        # ---- 第 4 步：结构化转换（Markdown → JSON）----
        await update_trip_plan_status(
            trip_plan_id=trip_plan_id,
            status="processing",
            current_step="Adding finishing touches",
        )

        try:
            # 调用 LLM 把累积的大段 Markdown 转成符合 TravelPlanTeamResponse 结构的 JSON
            json_response_output = await convert_to_model(
                last_response_content, TravelPlanTeamResponse
            )
            logger.info(
                f"Converted Structured Response: {json_response_output[:500]}..."
            )
        except Exception:#convert_to_model三次重试，都不行进入兜底
            # 转换失败时走确定性兜底，保证接口不会因为这一步而完全不可用
            logger.exception("Structured conversion failed, using fallback")
            json_response_output = _fallback_structured_response(
                request=request.travel_plan,
                destination_text=destination_search_response.messages[-1].content,
                flight_text=flight_search_response.messages[-1].content,
                hotel_text=hotel_search_response.messages[-1].content,
                dining_text=dining_search_response.messages[-1].content,
                itinerary_text=itinerary_response.messages[-1].content,
                budget_text=budget_response.messages[-1].content,
            )

        # ---- 第 5 步：持久化输出（先删旧记录，实现「覆盖式更新」）----
        await delete_trip_plan_outputs(trip_plan_id=trip_plan_id)

        # 最终响应既包含结构化行程，也保留每个 Agent 的原始 Markdown 回答
        final_response = json.dumps(
            {
                "itinerary": json_response_output,
                "budget_agent_response": budget_response.messages[-1].content,
                "destination_agent_response": destination_search_response.messages[-1].content,
                "flight_agent_response": flight_search_response.messages[-1].content,
                "hotel_agent_response": hotel_search_response.messages[-1].content,
                "restaurant_agent_response": dining_search_response.messages[-1].content,
                "itinerary_agent_response": itinerary_response.messages[-1].content,
            },
            indent=2,  # 缩进 2 格，方便人类直接阅读存储的 JSON
        )
        await create_trip_plan_output(
            trip_plan_id=trip_plan_id, itinerary=final_response, summary=""
        )

        # ---- 第 6 步：标记完成，并记录完成时间 ----
        await update_trip_plan_status(
            trip_plan_id=trip_plan_id,
            status="completed",
            current_step="Plan generated and saved",
            completed_at=datetime.now(timezone.utc),
        )
        return final_response

    except Exception as e:
        # 任何未捕获的异常：记录堆栈 → 标记 failed → 原样抛出让上层感知
        logger.exception(f"Error generating travel plan for {trip_plan_id}")
        await update_trip_plan_status(
            trip_plan_id=trip_plan_id,
            status="failed",
            error=str(e),
            completed_at=datetime.now(timezone.utc),
        )
        raise
