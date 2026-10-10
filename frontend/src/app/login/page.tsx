"use client";

import Link from "next/link";
import { useState } from "react";

import { isAuth0Configured, useAuth } from "@/components/auth/auth-provider";
import { Brand } from "@/components/brand";

function GoogleIcon() {
  return (
    <svg aria-hidden="true" height="20" viewBox="0 0 24 24" width="20">
      <path d="M21.6 12.23c0-.72-.06-1.42-.19-2.09H12v3.96h5.38a4.6 4.6 0 0 1-1.99 3.02v2.57h3.23c1.89-1.74 2.98-4.31 2.98-7.46Z" fill="#4285F4" />
      <path d="M12 22c2.7 0 4.96-.89 6.62-2.41l-3.23-2.57c-.9.6-2.04.95-3.39.95-2.6 0-4.81-1.76-5.6-4.12H3.07v2.65A10 10 0 0 0 12 22Z" fill="#34A853" />
      <path d="M6.4 13.85A6 6 0 0 1 6.09 12c0-.64.11-1.26.31-1.85V7.5H3.07A10 10 0 0 0 2 12c0 1.61.39 3.14 1.07 4.5l3.33-2.65Z" fill="#FBBC05" />
      <path d="M12 6.03c1.47 0 2.78.5 3.82 1.49l2.87-2.87A9.64 9.64 0 0 0 12 2a10 10 0 0 0-8.93 5.5l3.33 2.65C7.19 7.79 9.4 6.03 12 6.03Z" fill="#EA4335" />
    </svg>
  );
}

const focusStyle = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#8e77e5] focus-visible:ring-offset-4";
const buttonStyle = `flex min-h-14 w-full items-center justify-center gap-3 rounded-xl border border-[#ded8e9] bg-white px-5 text-sm font-semibold text-[#393143] shadow-[0_2px_4px_rgba(40,28,65,0.03)] transition hover:border-[#b5a4d8] hover:bg-[#fcfaff] disabled:cursor-wait disabled:opacity-60 ${focusStyle}`;

function Auth0LoginButton() {
  const { authError, isLoading, login } = useAuth();
  const [redirecting, setRedirecting] = useState(false);
  const [loginFailed, setLoginFailed] = useState(false);
  const busy = isLoading || redirecting;

  async function handleLogin() {
    setLoginFailed(false);
    setRedirecting(true);
    try {
      await login();
    } catch {
      setLoginFailed(true);
      setRedirecting(false);
    }
  }

  return (
    <>
      <button className={buttonStyle} disabled={busy} aria-busy={busy} onClick={() => void handleLogin()} type="button">
        {busy ? <span aria-hidden="true" className="h-5 w-5 animate-spin rounded-full border-2 border-[#e8e1f5] border-t-[#8063d5] motion-reduce:animate-none" /> : <GoogleIcon />}
        <span aria-live="polite">{busy ? "Connecting to Google…" : "Continue with Google"}</span>
      </button>
      {authError || loginFailed ? (
        <p className="mb-0 mt-4 rounded-lg border border-[#eed4da] bg-[#fff8f9] px-3.5 py-3 text-xs leading-5 text-[#a04a5d]" role="alert">
          We couldn’t complete your sign-in. Please try again.
        </p>
      ) : null}
    </>
  );
}

function UnavailableLoginButton() {
  return (
    <>
      <button className={buttonStyle} disabled type="button"><GoogleIcon />Continue with Google</button>
      <p className="mb-0 mt-4 rounded-lg border border-[#ecdcc4] bg-[#fffbf4] px-3.5 py-3 text-xs leading-5 text-[#956c38]" role="alert">
        Google sign-in is temporarily unavailable. Please try again later.
      </p>
    </>
  );
}

const stages = [
  { title: "Clarity in every slide", description: "See what’s working and where your deck can improve.", icon: "slides" as const },
  { title: "Words that sound like you", description: "Build and refine a script you can actually present.", icon: "script" as const },
  { title: "A little more prepared", description: "Rehearse on camera with live delivery feedback.", icon: "live" as const },
];

export default function LoginPage() {
  return (
    <main className="flex h-dvh flex-col overflow-hidden bg-[#faf9fc] text-[#292333]">
      <nav className="flex h-[4.5rem] flex-none items-center justify-between border-b border-[#e8e4ee] bg-white px-[clamp(1.25rem,4vw,4.5rem)]" aria-label="Primary navigation">
        <Link className={`rounded-lg no-underline ${focusStyle}`} href="/"><Brand /></Link>
        <Link className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-[#82778f] no-underline transition hover:bg-[#f6f3fa] hover:text-[#564366] ${focusStyle}`} href="/">
          <svg aria-hidden="true" width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12.5 8h-9m4-4-4 4 4 4" /></svg>
          Back to home
        </Link>
      </nav>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto grid min-h-full max-w-[100rem] lg:grid-cols-2">
          <section className="relative m-5 hidden flex-col justify-center overflow-hidden rounded-[24px] border border-[#e9e2f3] bg-[#f0ebf8] px-[clamp(2rem,4.5vw,5rem)] py-12 lg:flex" aria-label="Prepare with Rehearse AI">
            <div aria-hidden="true" className="pointer-events-none absolute -right-44 -top-44 h-[32rem] w-[32rem] rounded-full border border-white/60" />
            <div aria-hidden="true" className="pointer-events-none absolute -bottom-60 -left-36 h-[38rem] w-[38rem] rounded-full border border-[#e3daf1]" />
            <div className="relative mx-auto w-full max-w-[31rem]">
              <p className="m-0 flex items-center gap-2.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8b73b1]">
                <span className="h-px w-6 bg-[#ad99c9]" /> A little practice. A better presentation.
              </p>
              <h2 className="mb-0 mt-7 text-[clamp(2.5rem,3.8vw,4rem)] font-semibold leading-[1.08] tracking-[-0.05em]">
                Good ideas deserve<br />
                <span className="text-[#8a6abb]">a clear delivery.</span>
              </h2>
              <p className="mb-0 mt-5 max-w-[26rem] text-[15px] leading-7 text-[#776482]">
                A thoughtful space to work on your slides, find your words, and get comfortable presenting.
              </p>
              <div className="mt-10 space-y-6 border-t border-[#ded4eb] pt-8">
                {stages.map((stage) => (
                  <div className="flex items-start gap-4" key={stage.title}>
                    <span className="grid h-10 w-10 flex-none place-items-center rounded-xl border border-white/80 bg-white/60 text-[#9477ba]"><FeatureIcon kind={stage.icon} /></span>
                    <div className="pt-0.5">
                      <h3 className="m-0 text-sm font-semibold text-[#62506f]">{stage.title}</h3>
                      <p className="mb-0 mt-1 text-[13px] leading-5 text-[#7e6c89]">{stage.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className="flex min-w-0 flex-col bg-[#faf9fc] px-6 sm:px-12 lg:px-14" aria-labelledby="login-title">
            <div className="flex flex-1 items-center justify-center py-12 sm:py-16">
              <div className="w-full max-w-[24rem]">
                <span className="mb-7 grid h-12 w-12 place-items-center rounded-2xl border border-[#e9e0f4] bg-[#f3edf9] text-[#9676ba]"><FeatureIcon kind="door" /></span>
                <p className="m-0 text-[11px] font-semibold uppercase tracking-[0.13em] text-[#9a83b2]">Your workspace awaits</p>
                <h1 className="mb-0 mt-3 text-[clamp(2rem,3.2vw,2.75rem)] font-semibold leading-tight tracking-[-0.045em]" id="login-title">Ready when you are.</h1>
                <p className="mb-0 mt-4 text-sm leading-6 text-[#796b85]">
                  Sign in to work on your next presentation.<br className="hidden sm:block" /> New here? Your first sign-in gets you started.
                </p>

                <div className="mt-8">
                  {isAuth0Configured ? <Auth0LoginButton /> : <UnavailableLoginButton />}
                </div>
                <p className="mb-0 mt-4 text-center text-xs leading-5 text-[#82758e]">One Google account. All your preparation in one place.</p>

                <div className="mt-8 flex items-start gap-2.5 border-t border-[#eae5ef] pt-5">
                  <svg aria-hidden="true" className="mt-0.5 flex-none text-[#a494b4]" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3" /></svg>
                  <p className="m-0 text-xs leading-5 text-[#81748b]">You sign in securely with Google. Your Google password is never shared with Rehearse AI.</p>
                </div>
              </div>
            </div>
            <p className="mb-0 flex-none pb-6 text-center text-[11px] tracking-wide text-[#887b94]">From your first draft to your next presentation.</p>
          </section>
        </div>
      </div>
    </main>
  );
}

function FeatureIcon({ kind }: { kind: "slides" | "script" | "live" | "door" }) {
  const paths = {
    slides: <><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21l4-4 4 4M7 9h10M7 13h6" /></>,
    script: <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h5" /></>,
    live: <><rect x="3" y="5" width="18" height="14" rx="3" /><circle cx="12" cy="11" r="2.5" /><path d="M7 19v-1a5 5 0 0 1 10 0v1" /></>,
    door: <><path d="M13 4h6v16h-6M3 12h11m-4-4 4 4-4 4" /></>,
  };
  return <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">{paths[kind]}</svg>;
}
