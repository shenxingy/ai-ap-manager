import { NextRequest, NextResponse } from "next/server";

const ADMIN_ROUTES = [
  "/admin/users",
  "/admin/exception-routing",
  "/admin/approval-matrix",
  "/admin/ai-insights",
  "/admin/fraud",
  "/admin/rules",
  "/admin/settings",
];

const ANALYST_ROUTES = ["/analytics", "/admin/recurring-patterns"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const role = request.cookies.get("user_role")?.value ?? "";

  const isAdminRoute = ADMIN_ROUTES.some((r) => pathname.startsWith(r));
  const isAnalystRoute = ANALYST_ROUTES.some((r) => pathname.startsWith(r));

  if (isAdminRoute && role !== "ADMIN") {
    return NextResponse.redirect(new URL("/unauthorized", request.url));
  }

  if (isAnalystRoute && role !== "ADMIN" && role !== "AP_ANALYST") {
    return NextResponse.redirect(new URL("/unauthorized", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/admin/:path*", "/analytics/:path*"],
};
