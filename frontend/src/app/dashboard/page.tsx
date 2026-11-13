import { redirect } from "next/navigation";
import { Dashboard } from "@/components/dashboard";
import {
  createInsForgeServerClient,
  isInsForgeConfigured,
} from "@/lib/insforge/server";

export default async function DashboardPage() {
  if (!isInsForgeConfigured()) {
    redirect("/login?setup=required");
  }

  const client = await createInsForgeServerClient();
  const { data, error } = await client.auth.getCurrentUser();
  if (error || !data.user) {
    redirect("/login?session=expired");
  }

  return (
    <Dashboard
      userId={data.user.id}
      email={data.user.email ?? "Signed-in user"}
    />
  );
}
