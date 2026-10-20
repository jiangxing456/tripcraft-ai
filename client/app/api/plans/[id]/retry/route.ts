import { NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { prisma } from '@/lib/prisma';
import { triggerPlan } from '@/lib/trips';

type Context = { params: Promise<{ id: string }> };

export async function POST(request: Request, { params }: Context) {
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session) {
      return NextResponse.json(
        { success: false, message: 'Sign in required' },
        { status: 401 },
      );
    }

    const { id } = await params;
    const trip = await prisma.tripPlan.findFirst({
      where: { id, userId: session.user.id },
      include: { status: true },
    });
    if (!trip) {
      return NextResponse.json(
        { success: false, message: 'Trip plan not found' },
        { status: 404 },
      );
    }
    if (trip.status?.status === 'processing') {
      return NextResponse.json(
        { success: false, message: 'Already processing' },
        { status: 409 },
      );
    }

    const response = await triggerPlan(trip);
    return NextResponse.json({ success: true, response });
  } catch (error) {
    console.error('Trip retry failed:', error);
    return NextResponse.json(
      { success: false, message: 'Failed to retry trip plan' },
      { status: 500 },
    );
  }
}
