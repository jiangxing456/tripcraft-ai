/**
 * POST /api/plan/submit
 *
 * 行程规划表单提交接口：
 * 1. 接收前端提交的行程表单数据（前端为 camelCase 命名）
 * 2. 将数据写入本地数据库（Prisma / TripPlan 表）
 * 3. 把数据转换为 snake_case 格式，转发给 Python 后端，触发多智能体规划流程
 */

import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

/** 前端提交的行程表单数据结构（C 端字段命名） */
interface TripFormData {
  name: string;                          // 行程名称 / 出行人姓名
  destination: string;                   // 目的地
  startingLocation: string;              // 出发地
  travelDates: { start: string; end: string }; // 出行日期区间
  dateInputType: "picker" | "text";      // 日期输入方式：日期选择器 / 手输文本
  duration: number;                      // 行程天数
  travelingWith: string;                 // 同行人类型（独自 / 情侣 / 家庭 / 朋友等）
  adults: number;                        // 成人数
  children: number;                      // 儿童数
  ageGroups: string[];                   // 年龄段（如 ["0-3", "4-12"]）
  budget: number;                        // 预算金额
  budgetCurrency: string;                // 预算币种
  travelStyle: string;                   // 旅行风格（穷游 / 舒适 / 奢华等）
  budgetFlexible: boolean;               // 预算是否可浮动
  vibes: string[];                       // 出行氛围偏好（如 ["放松", "冒险"]）
  priorities: string[];                  // 优先考虑项（如 ["美食", "住宿"]）
  interests?: string;                    // 兴趣补充说明
  rooms: number;                         // 房间数
  pace: number[];                        // 行程节奏（数组，兼容旧版单值传参）
  beenThereBefore?: string;              // 是否去过该目的地
  lovedPlaces?: string;                  // 喜欢的去过的地方
  additionalInfo?: string;               // 其他补充信息
}

/** 处理行程规划表单提交 */
export async function POST(request: NextRequest) {
  try {
    // 解析前端传来的 JSON 请求体
    const tripData: TripFormData = await request.json();

    // 打印行程数据，便于调试
    console.log('Received trip planning data:', JSON.stringify(tripData, null, 2));

    // 校验必填字段：姓名、目的地、出发地三者缺一不可
    if (!tripData.name || !tripData.destination || !tripData.startingLocation) {
      return NextResponse.json(
        {
          success: false,
          message: 'Missing required fields: name, destination, or starting location'
        },
        { status: 400 }
      );
    }

    // 节奏字段兼容处理：滑块组件历史上可能只传一个裸数字，
    // 而数据库和 Python 后端都要求 Int[] 类型
    const paceValue = Array.isArray(tripData.pace)
      ? tripData.pace
      : typeof (tripData as { pace?: unknown }).pace === 'number'
        ? [(tripData as unknown as { pace: number }).pace]
        : [3]; // 全部缺失时默认给中等节奏 3

    // 写入数据库：保存行程规划记录
    const savedTripPlan = await prisma.tripPlan.create({
      data: {
        name: tripData.name,
        destination: tripData.destination,
        startingLocation: tripData.startingLocation,
        travelDatesStart: tripData.travelDates.start,
        travelDatesEnd: tripData.travelDates.end || null,
        dateInputType: tripData.dateInputType || "picker",
        duration: tripData.duration || null,
        travelingWith: tripData.travelingWith,
        adults: tripData.adults || 1,
        children: tripData.children || 0,
        ageGroups: tripData.ageGroups || [],
        budget: tripData.budget,
        budgetCurrency: tripData.budgetCurrency || "USD",
        travelStyle: tripData.travelStyle,
        budgetFlexible: tripData.budgetFlexible || false,
        vibes: tripData.vibes || [],
        priorities: tripData.priorities || [],
        interests: tripData.interests || null,
        rooms: tripData.rooms || 1,
        pace: paceValue,
        beenThereBefore: tripData.beenThereBefore || null,
        lovedPlaces: tripData.lovedPlaces || null,
        additionalInfo: tripData.additionalInfo || null,
        // 用户体系尚未接入，后续实现鉴权后再补 userId
        userId: null
      }
    });

    console.log('Trip plan saved to database:', savedTripPlan.id);

    // 组装给 Python 后端的请求体：
    // 字段命名由前端的 camelCase 转为后端约定的 snake_case
    const requestBody = {
      trip_plan_id: savedTripPlan.id,   // 回传数据库记录 ID，便于后端关联结果
      travel_plan: {
        name: tripData.name,
        destination: tripData.destination,
        starting_location: tripData.startingLocation,
        travel_dates: {
          start: tripData.travelDates.start,
          end: tripData.travelDates.end || ""
        },
        date_input_type: tripData.dateInputType,
        duration: tripData.duration,
        traveling_with: tripData.travelingWith,
        adults: tripData.adults,
        children: tripData.children,
        age_groups: tripData.ageGroups,
        budget: tripData.budget,
        budget_currency: tripData.budgetCurrency,
        travel_style: tripData.travelStyle,
        budget_flexible: tripData.budgetFlexible,
        vibes: tripData.vibes,
        priorities: tripData.priorities,
        interests: tripData.interests || "",
        rooms: tripData.rooms,
        pace: paceValue,
        been_there_before: tripData.beenThereBefore || "",
        loved_places: tripData.lovedPlaces || "",
        additional_info: tripData.additionalInfo || ""
      }

    }

    console.log('Request body:', JSON.stringify(requestBody, null, 2));

    // 调用后端接口，触发行程规划流程
    // 环境变量 BACKEND_API_URL 未配置时，默认走本地 8000 端口
    const backendBaseUrl = (process.env.BACKEND_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
    const backendResponse = await fetch(`${backendBaseUrl}/api/plan/trigger`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody)
    });

    // 后端返回非 2xx 状态码时，记录错误详情并返回 500
    if (!backendResponse.ok) {
      console.error('Backend API error:', await backendResponse.text());
      return NextResponse.json(
        {
          success: false,
          message: 'Failed to trigger trip planning'
        },
        { status: 500 }
      );
    }

    // 后端触发成功，解析其返回内容
    const responseData = await backendResponse.json();
    console.log('Backend response:', JSON.stringify(responseData, null, 2));

    // 返回成功结果，并带上已落库的行程记录 ID
    return NextResponse.json(
      {
        success: true,
        message: 'Trip planning triggered successfully',
        response: responseData,
        tripPlanId: savedTripPlan.id
      },
      { status: 200 }
    );
  } catch (error) {
    // 兜底异常处理：如请求体解析失败、数据库写入失败、网络请求异常等
    console.error('Error processing trip submission:', error);
    return NextResponse.json(
      {
        success: false,
        message: 'Failed to save trip plan to database'
      },
      { status: 500 }
    );
  }
}
