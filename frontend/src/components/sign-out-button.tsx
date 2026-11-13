"use client";

import { useActionState } from "react";
import { signOutAction, type AuthFormState } from "@/app/actions/auth";

const initialState: AuthFormState = {};

export function SignOutButton() {
  const [state, action, pending] = useActionState(signOutAction, initialState);

  return (
    <div>
      <form action={action}>
        <button
          type="submit"
          disabled={pending}
          className="rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
        >
          {pending ? "Signing out..." : "Sign out"}
        </button>
      </form>
      {state.error && (
        <p role="alert" className="mt-2 text-xs text-rose-700">
          {state.error}
        </p>
      )}
    </div>
  );
}
