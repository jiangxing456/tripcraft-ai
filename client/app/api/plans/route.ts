import { NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { prisma } from '@/lib/prisma';

export async function GET(request: Request) {
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session) {
      return NextResponse.json(
        { success: false, message: 'Sign in required' },
        { status: 401 },
      );
    }

    const tripPlans = await prisma.tripPlan.findMany({
      where: { userId: session.user.id },
      orderBy: { createdAt: 'desc' },
    });
    return NextResponse.json({ success: true, tripPlans });
  } catch (error) {
    console.error('Trip list failed:', error);
    return NextResponse.json(
      { success: false, message: 'Failed to fetch trip plans' },
      { status: 500 },
    );
  }
}
