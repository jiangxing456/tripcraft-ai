"""plan_service.py 里 4 个「纯函数」的测试。

为什么先挑这几个测？
    它们不连数据库、不调 AI —— 跑一次只要几毫秒，永远不会因为网络抖动、
    模型抽风而失败。补测试要从这种「最确定」的部分开始，先建立信心。

跑法（在 backend 目录下）：
    ./.venv/Scripts/python.exe -m pytest tests -v

每个 `test_` 开头的函数就是一条测试用例；`assert` 不成立 = 这条用例失败。
"""

import json

from models.travel_plan import TravelDates, TravelPlanRequest
from services.plan_service import (
    _clip,
    _fallback_structured_response,
    _shift_date,
    travel_request_to_markdown,
)

# =====================================================================
# 1. _shift_date —— 把开始日期往后推 N 天
#    （这是我们修 bug 时新增的函数：原来 4 天行程的日期全是同一天）
# =====================================================================


def test_shift_date_normal():
    """普通情况：10-01 往后推 1 天 -> 10-02"""
    assert _shift_date("2026-10-01", 1) == "2026-10-02"


def test_shift_date_zero_offset():
    """偏移 0 天 = 原样返回"""
    assert _shift_date("2026-10-01", 0) == "2026-10-01"


def test_shift_date_across_month():
    """跨月：10-31 加一天应该是 11-01，不是 10-32"""
    assert _shift_date("2026-10-31", 1) == "2026-11-01"


def test_shift_date_across_year():
    """跨年：12-31 加一天 -> 次年 01-01"""
    assert _shift_date("2026-12-31", 1) == "2027-01-01"


def test_shift_date_empty_string_does_not_crash():
    """边界：用户没填日期 —— 要原样返回，不许抛异常"""
    assert _shift_date("", 3) == ""


def test_shift_date_free_text_does_not_crash():
    """边界：用户填了 'next week' 这种自由文本 —— 同样不许抛异常"""
    assert _shift_date("next week", 3) == "next week"


# =====================================================================
# 2. _clip —— 把过长文本截到 limit 个字符以内
# =====================================================================


def test_clip_short_text_untouched():
    """没超长就不动它"""
    assert _clip("hello", limit=10) == "hello"


def test_clip_strips_surrounding_whitespace():
    """两端的空白会被去掉"""
    assert _clip("  hello  ", limit=10) == "hello"


def test_clip_long_text_truncated_to_limit():
    """超长则截断，长度正好等于 limit，并以 ... 结尾"""
    result = _clip("a" * 100, limit=10)
    assert len(result) == 10
    assert result.endswith("...")


def test_clip_empty_string():
    """空字符串是合法输入（用户很多字段都可能没填）"""
    assert _clip("", limit=10) == ""


# =====================================================================
# 3. travel_request_to_markdown —— 把用户表单渲染成 Markdown
#    这段 Markdown 是后面 6 个 Agent 提示词的原料
# =====================================================================


def test_markdown_contains_destination_and_origin():
    md = travel_request_to_markdown(
        TravelPlanRequest(destination="Tokyo", starting_location="Beijing")
    )
    # 用 lower() 比较，避免被 .title() / .capitalize() 的大小写处理影响
    assert "tokyo" in md.lower()
    assert "beijing" in md.lower()


def test_markdown_returns_string_for_empty_request():
    """极端情况：用户什么都没填，也要能渲染出骨架，不能崩"""
    md = travel_request_to_markdown(TravelPlanRequest())
    assert isinstance(md, str)
    assert len(md) > 0


# =====================================================================
# 4. _fallback_structured_response —— 模板兜底（完全不依赖 AI）
#    只有 convert_to_model 连续失败 3 次才会走到这里
# =====================================================================


def _make_fallback_output(duration=4, start="2026-10-01"):
    """构造一份兜底输出，供下面几个测试共用。

    注意：函数名不以 test_ 开头，pytest 不会把它当成一条用例。
    """
    request = TravelPlanRequest(
        destination="Tokyo",
        duration=duration,
        travel_dates=TravelDates(start=start, end="2026-10-04"),
    )
    return _fallback_structured_response(
        request=request,
        destination_text="目的地调研内容",
        flight_text="航班内容",
        hotel_text="酒店内容",
        restaurant_text="餐厅内容",
        itinerary_text="行程内容",
        budget_text="预算内容",
    )


def test_fallback_returns_valid_json_string():
    """最重要的一条：兜底产物必须是合法 JSON，否则下游全崩"""
    output = _make_fallback_output()
    assert isinstance(output, str)
    assert isinstance(json.loads(output), dict)


def test_fallback_has_all_expected_fields():
    """7 个字段一个都不能少（前端按这 7 个字段渲染）"""
    data = json.loads(_make_fallback_output())
    assert set(data.keys()) == {
        "day_by_day_plan",
        "hotels",
        "attractions",
        "flights",
        "restaurants",
        "budget_insights",
        "tips",
    }


def test_fallback_day_number_starts_from_one():
    """天数从 1 开始编号"""
    data = json.loads(_make_fallback_output(duration=4))
    assert [d["day"] for d in data["day_by_day_plan"]] == [1, 2, 3, 4]


def test_fallback_dates_increment_each_day():
    """回归测试 —— 修 bug 之前，4 天的 date 全是 '2026-10-01'。

    这条用例存在的意义就是：以后谁再动这段代码，一旦日期不再递增，
    跑一下测试立刻就能发现。
    """
    data = json.loads(_make_fallback_output(duration=4))
    assert [d["date"] for d in data["day_by_day_plan"]] == [
        "2026-10-01",
        "2026-10-02",
        "2026-10-03",
        "2026-10-04",
    ]


def test_fallback_duration_zero_still_produces_one_day():
    """duration=0 时兜底会兜到 1 天，不会产出空列表"""
    data = json.loads(_make_fallback_output(duration=0))
    assert len(data["day_by_day_plan"]) == 1


def test_fallback_start_date_is_free_text():
    """用户填的不是标准日期时，兜底同样不能崩（日期退回原值）"""
    data = json.loads(_make_fallback_output(duration=3, start="下个月"))
    assert [d["date"] for d in data["day_by_day_plan"]] == ["下个月", "下个月", "下个月"]
