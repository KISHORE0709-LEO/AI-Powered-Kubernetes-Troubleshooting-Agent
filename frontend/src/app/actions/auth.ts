"use server";

import { createAuthActions } from "@insforge/sdk/ssr";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { isInsForgeConfigured } from "@/lib/insforge/server";

export interface AuthFormState {
  error?: string;
  notice?: string;
}

export async function signInAction(
  _previousState: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  if (!isInsForgeConfigured()) {
    return { error: "InsForge is not configured for this application." };
  }

  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  if (!email || !password) {
    return { error: "Enter your email and password." };
  }

  const auth = createAuthActions({ cookies: await cookies() });
  const { data, error } = await auth.signInWithPassword({ email, password });
  if (error || !data?.user) {
    return { error: error?.message ?? "Sign in failed. Try again." };
  }

  redirect("/dashboard");
}

export async function signUpAction(
  _previousState: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  if (!isInsForgeConfigured()) {
    return { error: "InsForge is not configured for this application." };
  }

  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const name = String(formData.get("name") ?? "").trim();
  if (!email || password.length < 8) {
    return { error: "Enter an email and a password of at least 8 characters." };
  }

  const auth = createAuthActions({ cookies: await cookies() });
  const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";
  const { data, error } = await auth.signUp({
    email,
    password,
    name: name || undefined,
    redirectTo: new URL("/login", appUrl).toString(),
  });
  if (error || !data) {
    return { error: error?.message ?? "Account creation failed. Try again." };
  }
  if (data.requireEmailVerification) {
    return { notice: "Check your email to verify your account, then sign in." };
  }

  redirect("/dashboard");
}

export async function signOutAction(
  _previousState: AuthFormState,
  _formData: FormData,
): Promise<AuthFormState> {
  void _previousState;
  void _formData;

  if (!isInsForgeConfigured()) {
    return { error: "InsForge is not configured for this application." };
  }

  const auth = createAuthActions({ cookies: await cookies() });
  const { error } = await auth.signOut();
  if (error) {
    return { error: error.message };
  }

  redirect("/login");
}
