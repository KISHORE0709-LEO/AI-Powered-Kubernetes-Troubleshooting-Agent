import { createServerClient } from "@insforge/sdk/ssr";
import { cookies } from "next/headers";

export function isInsForgeConfigured(): boolean {
  return Boolean(
    process.env.NEXT_PUBLIC_INSFORGE_URL &&
      process.env.NEXT_PUBLIC_INSFORGE_ANON_KEY,
  );
}

export async function createInsForgeServerClient() {
  return createServerClient({
    cookies: await cookies(),
  });
}
