import { updateSession } from "@insforge/sdk/ssr/middleware";
import { NextResponse, type NextRequest } from "next/server";

export async function proxy(request: NextRequest) {
  const response = NextResponse.next({ request });
  await updateSession({
    requestCookies: request.cookies,
    responseCookies: response.cookies,
  });
  return response;
}

export const config = {
  matcher: ["/((?!api/auth/refresh|_next/static|_next/image|favicon.ico).*)"],
};
