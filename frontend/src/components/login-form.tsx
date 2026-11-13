"use client";

import { useActionState, useState } from "react";
import {
  signInAction,
  signUpAction,
  type AuthFormState,
} from "@/app/actions/auth";

const initialState: AuthFormState = {};

export function LoginForm({ configured }: { configured: boolean }) {
  const [mode, setMode] = useState<"sign-in" | "sign-up">("sign-in");
  const [signInState, signIn, signInPending] = useActionState(
    signInAction,
    initialState,
  );
  const [signUpState, signUp, signUpPending] = useActionState(
    signUpAction,
    initialState,
  );
  const state = mode === "sign-in" ? signInState : signUpState;
  const pending = mode === "sign-in" ? signInPending : signUpPending;
  const action = mode === "sign-in" ? signIn : signUp;

  return (
    <main className="flex min-h-screen items-center justify-center px-5 py-12">
      <section className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-7 shadow-sm sm:p-9">
        <div className="mb-8 flex items-center gap-3">
          <span className="flex size-11 items-center justify-center rounded-xl bg-blue-700 text-sm font-bold text-white">
            AI
          </span>
          <div>
            <p className="font-semibold tracking-tight text-slate-900">
              AI Kubernetes Agent
            </p>
            <p className="text-sm text-slate-500">Secure cluster troubleshooting</p>
          </div>
        </div>

        <h1 className="text-2xl font-semibold tracking-tight text-slate-950">
          {mode === "sign-in" ? "Welcome back" : "Create your account"}
        </h1>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          {mode === "sign-in"
            ? "Sign in to investigate your Kubernetes cluster."
            : "Create an account to save and review investigations."}
        </p>

        {!configured && (
          <p
            role="alert"
            className="mt-5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
          >
            Add the InsForge URL and anon key to the frontend environment before
            signing in.
          </p>
        )}

        <form action={action} className="mt-7 space-y-4">
          {mode === "sign-up" && (
            <label className="block text-sm font-medium text-slate-700">
              Name <span className="font-normal text-slate-400">(optional)</span>
              <input
                name="name"
                type="text"
                autoComplete="name"
                className="mt-2 w-full rounded-lg border border-slate-300 px-3.5 py-3 text-slate-900 outline-none transition focus:border-blue-600 focus:ring-4 focus:ring-blue-100"
              />
            </label>
          )}
          <label className="block text-sm font-medium text-slate-700">
            Email
            <input
              name="email"
              type="email"
              autoComplete="email"
              required
              className="mt-2 w-full rounded-lg border border-slate-300 px-3.5 py-3 text-slate-900 outline-none transition focus:border-blue-600 focus:ring-4 focus:ring-blue-100"
            />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Password
            <input
              name="password"
              type="password"
              autoComplete={
                mode === "sign-in" ? "current-password" : "new-password"
              }
              minLength={mode === "sign-up" ? 8 : undefined}
              required
              className="mt-2 w-full rounded-lg border border-slate-300 px-3.5 py-3 text-slate-900 outline-none transition focus:border-blue-600 focus:ring-4 focus:ring-blue-100"
            />
          </label>

          {(state.error || state.notice) && (
            <p
              role={state.error ? "alert" : "status"}
              className={`rounded-lg px-4 py-3 text-sm ${
                state.error
                  ? "border border-rose-200 bg-rose-50 text-rose-800"
                  : "border border-emerald-200 bg-emerald-50 text-emerald-800"
              }`}
            >
              {state.error ?? state.notice}
            </p>
          )}

          <button
            type="submit"
            disabled={pending || !configured}
            className="flex w-full items-center justify-center rounded-lg bg-blue-700 px-4 py-3 text-sm font-semibold text-white transition hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pending
              ? "Please wait..."
              : mode === "sign-in"
                ? "Sign in"
                : "Create account"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-600">
          {mode === "sign-in" ? "New to the dashboard?" : "Already have an account?"}{" "}
          <button
            type="button"
            onClick={() =>
              setMode((current) =>
                current === "sign-in" ? "sign-up" : "sign-in",
              )
            }
            className="font-semibold text-blue-700 hover:text-blue-800"
          >
            {mode === "sign-in" ? "Create an account" : "Sign in"}
          </button>
        </p>
      </section>
    </main>
  );
}
