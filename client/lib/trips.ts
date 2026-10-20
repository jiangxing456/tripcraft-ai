import type { TripPlan } from '@/lib/generated/prisma';
import { prisma } from '@/lib/prisma';
import { z } from 'zod';

const text = z.string().trim().min(1).max(100);
export const tripForm = z.object({
  name: text,
  destination: text,
  startingLocation: text,
  travelDates: z.object({
    start: z.string().min(10),
    end: z.string().optional().default(''),
  }),
  dateInputType: z.enum(['picker', 'text']).default('picker'),
  duration: z.number().int().min(1).max(14),
  adults: z.number().int().min(1).max(20).default(1),
  children: z.number().int().min(0).max(20).default(0),
  rooms: z.number().int().min(1).max(20).default(1),
  budget: z.number().int().positive().max(10000000),
  budgetCurrency: z.string().regex(/^[A-Z]{3}$/).default('USD'),
  travelingWith: z.string().default(''),
  travelStyle: z.string().default(''),
  budgetFlexible: z.boolean().default(false),
  ageGroups: z.array(z.string()).default([]),
  vibes: z.array(z.string()).default([]),
  priorities: z.array(z.string()).default([]),
  pace: z.array(z.number().int().min(0).max(5)).default([3]),
  interests: z.string().max(2000).default(''),
  beenThereBefore: z.string().default(''),
  lovedPlaces: z.string().max(2000).default(''),
  additionalInfo: z.string().max(2000).default(''),
}).superRefine((data, context) => {
  const value = data.travelDates.start.slice(0, 10);
  const start = new Date(value + 'T00:00:00Z');
  const hasDateFormat = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const isInvalidDate = Number.isNaN(start.getTime());
  if (!hasDateFormat || isInvalidDate || start.toISOString().slice(0, 10) !== value) {
    context.addIssue({
      code: 'custom',
      path: ['travelDates', 'start'],
      message: 'Use a valid YYYY-MM-DD date',
    });
    return;
  }
  start.setUTCDate(start.getUTCDate() + data.duration - 1);
  const end = data.travelDates.end.slice(0, 10);
  const expectedEnd = start.toISOString().slice(0, 10);
  if (end && end !== expectedEnd) {
    context.addIssue({
      code: 'custom',
      path: ['travelDates', 'end'],
      message: 'End date must match trip duration',
    });
  }
});

export async function triggerPlan(trip: TripPlan) {
  const base = (process.env.BACKEND_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
  const travel_plan = {
    user_id: trip.userId || '',
    name: trip.name,
    destination: trip.destination,
    starting_location: trip.startingLocation,
    travel_dates: {
      start: trip.travelDatesStart,
      end: trip.travelDatesEnd || '',
    },
    date_input_type: trip.dateInputType,
    duration: trip.duration,
    adults: trip.adults,
    children: trip.children,
    rooms: trip.rooms,
    budget: trip.budget,
    budget_currency: trip.budgetCurrency,
    traveling_with: trip.travelingWith,
    travel_style: trip.travelStyle,
    budget_flexible: trip.budgetFlexible,
    age_groups: trip.ageGroups,
    vibes: trip.vibes,
    priorities: trip.priorities,
    pace: trip.pace,
    interests: trip.interests || '',
    been_there_before: trip.beenThereBefore || '',
    loved_places: trip.lovedPlaces || '',
    additional_info: trip.additionalInfo || '',
  };
  let response: Response | undefined;
  try {
    response = await fetch(`${base}/api/plan/trigger`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trip_plan_id: trip.id, travel_plan }),
    });
    if (!response.ok) {
      throw new Error(`Planning backend returned ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    if (response?.status !== 409) {
      await prisma.tripPlanStatus.upsert({
        where: { tripPlanId: trip.id },
        create: {
          tripPlanId: trip.id,
          status: 'failed',
          currentStep: 'Backend request failed',
        },
        update: {
          status: 'failed',
          currentStep: 'Backend request failed',
        },
      });
    }
    throw error;
  }
}
