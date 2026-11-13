import { createServerClient } from "@insforge/sdk/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { cookies } from "next/headers";

export const maxDuration = 180;

export async function POST(request: NextRequest) {
  const baseUrl = process.env.FASTAPI_BASE_URL ?? "http://localhost:8000";
  const cookieStore = await cookies();
  const accessToken = cookieStore.get("insforge_access_token")?.value;
  if (!accessToken) {
    return NextResponse.json(
      { status: "error", error: "Sign in before starting an investigation." },
      { status: 401 },
    );
  }

  const client = createServerClient({ cookies: cookieStore });
  const { data, error } = await client.auth.getCurrentUser();
  if (error || !data.user) {
    return NextResponse.json(
      { status: "error", error: "Your session has expired. Sign in again." },
      { status: 401 },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { status: "error", error: "A valid investigation request is required." },
      { status: 400 },
    );
  }
  if (
    typeof body !== "object" ||
    body === null ||
    !("investigation_id" in body) ||
    typeof body.investigation_id !== "string"
  ) {
    return NextResponse.json(
      { status: "error", error: "A valid investigation ID is required." },
      { status: 400 },
    );
  }

  let response: Response;
  try {
    response = await fetch(new URL("/investigate", baseUrl), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ investigation_id: body.investigation_id }),
      signal: AbortSignal.timeout(175_000),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      return NextResponse.json(
        { status: "error", error: "The investigation timed out." },
        { status: 504 },
      );
    }
    if (error instanceof TypeError) {
      return NextResponse.json(
        { status: "error", error: "The troubleshooting API is unavailable." },
        { status: 502 },
      );
    }
    throw error;
  }

  try {
    const result: unknown = await response.json();
    return NextResponse.json(result, { status: response.status });
  } catch {
    return NextResponse.json(
      { status: "error", error: "The troubleshooting API returned an invalid response." },
      { status: 502 },
    );
  }
}
