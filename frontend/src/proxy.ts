import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import {
  AUTH_COOKIE_NAME,
  PUBLIC_ROUTES,
} from "@/lib/firebase/firebase-config";
import { verifyIdToken } from "@/lib/firebase/verify-token";

function isPublicRoute(pathname: string) {
  return PUBLIC_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(`${route}/`),
  );
}

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname.startsWith("/api/auth")) {
    return NextResponse.next();
  }

  const token = request.cookies.get(AUTH_COOKIE_NAME)?.value;
  const isAuthenticated = token ? await verifyIdToken(token) : false;
  const publicRoute = isPublicRoute(pathname);

  if (token && !isAuthenticated) {
    const response = NextResponse.redirect(new URL("/login", request.url));
    response.cookies.set(AUTH_COOKIE_NAME, "", { maxAge: 0, path: "/" });
    return response;
  }

  if (!isAuthenticated && !publicRoute) {
    const loginUrl = new URL("/login", request.url);
    if (pathname !== "/") {
      loginUrl.searchParams.set("from", pathname);
    }
    return NextResponse.redirect(loginUrl);
  }

  if (isAuthenticated && publicRoute) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
