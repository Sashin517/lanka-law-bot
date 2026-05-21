import { NextResponse } from "next/server";

import { AUTH_COOKIE_NAME } from "@/lib/firebase/firebase-config";

export async function POST() {
  const response = NextResponse.json({ status: "ok" });
  response.cookies.set(AUTH_COOKIE_NAME, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 0,
    path: "/",
  });

  return response;
}
