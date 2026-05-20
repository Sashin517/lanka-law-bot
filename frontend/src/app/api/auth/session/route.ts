import { NextResponse } from "next/server";

import { AUTH_COOKIE_NAME } from "@/lib/firebase/firebase-config";
import { verifyIdToken } from "@/lib/firebase/verify-token";

export async function POST(request: Request) {
  const { idToken } = (await request.json()) as { idToken?: string };

  if (!idToken || !(await verifyIdToken(idToken))) {
    return NextResponse.json({ error: "Invalid token" }, { status: 401 });
  }

  const response = NextResponse.json({ status: "ok" });
  response.cookies.set(AUTH_COOKIE_NAME, idToken, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 60 * 60,
    path: "/",
  });

  return response;
}
