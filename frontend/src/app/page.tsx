import { redirect } from "next/navigation";
import {
  createInsForgeServerClient,
  isInsForgeConfigured,
} from "@/lib/insforge/server";

export default async function Home() {
  if (!isInsForgeConfigured()) {
    redirect("/login?setup=required");
  }

  const client = await createInsForgeServerClient();
  const { data } = await client.auth.getCurrentUser();
  redirect(data.user ? "/dashboard" : "/login");
}
