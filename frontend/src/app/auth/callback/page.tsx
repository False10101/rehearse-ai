"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { isAuth0Configured, useAuth } from "@/components/auth/auth-provider";

function CallbackRedirect() {
  const router = useRouter();
  const { authError, isAuthenticated, isLoading, returnTo } = useAuth();

  useEffect(() => {
    if (authError) console.error("Sign-in callback failed:", authError);
    if (!isLoading && !authError) router.replace(isAuthenticated ? returnTo : "/login");
  }, [authError, isAuthenticated, isLoading, returnTo, router]);

  if (authError) {
    return (
      <div className="w-full max-w-md rounded-2xl border border-[#f0c7ce] bg-white p-7 shadow-[0_20px_50px_rgba(38,31,76,0.10)]">
        <p className="m-0 text-[0.75rem] font-bold uppercase tracking-[0.1em] text-[#c34158]">Sign-in could not finish</p>
        <h1 className="mb-0 mt-3 text-[1.65rem] tracking-[-0.045em]">Please try signing in again.</h1>
        <p className="mb-0 mt-3 text-[0.9rem] leading-6 text-[#625f73]">We couldn’t complete your Google sign-in. Return to sign in and try again.</p>
        <Link className="mt-6 inline-flex rounded-lg bg-[#1d1c2a] px-4 py-2.5 text-[0.85rem] font-bold text-white no-underline" href="/login">
          Return to sign in
        </Link>
      </div>
    );
  }

  return <p className="text-[0.9rem] text-[#625f73]">Completing your secure sign-in…</p>;
}

export default function AuthCallbackPage() {
  return (
    <main className="grid min-h-dvh place-items-center bg-[#f8f7ff] px-6 text-[#1d1c2a]">
      {isAuth0Configured ? <CallbackRedirect /> : <div className="text-center"><p className="text-[0.9rem] text-[#625f73]">Google sign-in is temporarily unavailable. Please try again later.</p><Link className="text-sm font-semibold text-[#6753e9]" href="/login">Return to sign in</Link></div>}
    </main>
  );
}
