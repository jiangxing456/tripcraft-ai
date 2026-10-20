import { NextRequest, NextResponse } from "next/server";

const BASE_URL = process.env.NEXT_PUBLIC_BASE_URL || "http://localhost:3000"

export async function middleware(request: NextRequest) {



  const url = `${BASE_URL}/api/auth/get-session`;



  const response = await fetch(url, {
    headers: {
      cookie: request.headers.get("cookie") || "",
    },
  });

  if (!response.ok) {
    return NextResponse.redirect(new URL("/auth", request.url));
  }

  const session = await response.json();

  if (!session) {
    return NextResponse.redirect(new URL("/auth", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/plan",],
};