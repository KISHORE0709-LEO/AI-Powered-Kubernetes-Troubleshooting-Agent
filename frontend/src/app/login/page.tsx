import { redirect } from "next/navigation";
import { LoginForm } from "@/components/login-form";
import {
  createInsForgeServerClient,
  isInsForgeConfigured,
} from "@/lib/insforge/server";

export default async function LoginPage() {
  if (isInsForgeConfigured()) {
    const client = await createInsForgeServerClient();
    const { data } = await client.auth.getCurrentUser();
    if (data.user) {
      redirect("/dashboard");
    }
  }

  return <LoginForm configured={isInsForgeConfigured()} />;
}
