import { NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { prisma } from '@/lib/prisma';
import { tripForm, triggerPlan } from '@/lib/trips';

export async function POST(request: Request) {
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session) {
      return NextResponse.json(
        { success: false, message: 'Sign in required' },
        { status: 401 },
      );
    }

    const parsed = tripForm.safeParse(await request.json());
    if (!parsed.success) {
      return NextResponse.json(
        { success: false, message: parsed.error.issues[0].message },
        { status: 400 },
      );
    }

    const { travelDates, ...fields } = parsed.data;
    // 身份只取服务端会话，忽略请求体伪造的 userId。
    const trip = await prisma.tripPlan.create({
      data: {
        ...fields,
        travelDatesStart: travelDates.start,
        travelDatesEnd: travelDates.end || null,
        userId: session.user.id,
      },
    });
    const response = await triggerPlan(trip);
    return NextResponse.json({ success: true, tripPlanId: trip.id, response });
  } catch (error) {
    if (error instanceof SyntaxError) {
      return NextResponse.json(
        { success: false, message: 'Invalid JSON' },
        { status: 400 },
      );
    }
    console.error('Trip submission failed:', error);
    return NextResponse.json(
      { success: false, message: 'Failed to submit trip plan' },
      { status: 500 },
    );
  }
}
