import { NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { prisma } from '@/lib/prisma';

type Context = { params: Promise<{ id: string }> };

export async function GET(request: Request, { params }: Context) {
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session) {
      return NextResponse.json(
        { success: false, message: 'Sign in required' },
        { status: 401 },
      );
    }

    const { id } = await params;
    const tripPlan = await prisma.tripPlan.findFirst({
      where: { id, userId: session.user.id },
      include: { status: true, output: true },
    });
    if (!tripPlan) {
      return NextResponse.json(
        { success: false, message: 'Trip plan not found' },
        { status: 404 },
      );
    }
    return NextResponse.json({ success: true, tripPlan });
  } catch (error) {
    console.error('Trip lookup failed:', error);
    return NextResponse.json(
      { success: false, message: 'Failed to fetch trip plan' },
      { status: 500 },
    );
  }
}

export async function DELETE(request: Request, { params }: Context) {
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session) {
      return NextResponse.json(
        { success: false, message: 'Sign in required' },
        { status: 401 },
      );
    }

    const { id } = await params;
    const deleted = await prisma.tripPlan.deleteMany({
      where: { id, userId: session.user.id },
    });
    if (!deleted.count) {
      return NextResponse.json(
        { success: false, message: 'Trip plan not found' },
        { status: 404 },
      );
    }
    // 关联状态与产物由现有外键 ON DELETE CASCADE 原子删除。
    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Trip deletion failed:', error);
    return NextResponse.json(
      { success: false, message: 'Failed to delete trip plan' },
      { status: 500 },
    );
  }
}
