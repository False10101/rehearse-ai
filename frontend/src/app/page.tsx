"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import "./landing.css";
import { LandingFeaturePreview } from "@/components/landing-feature-preview";

import { isAuth0Configured, useAuth } from "@/components/auth/auth-provider";
import { Brand } from "@/components/brand";

function ArrowIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="16" viewBox="0 0 16 16" width="16">
      <path d="M3.25 8h9.5M9 4.25 12.75 8 9 11.75" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" />
    </svg>
  );
}

const focusStyle = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#947bdc] focus-visible:ring-offset-4";
const primaryLink = "landing-primary";
const compactLink = "landing-signin";

function ConfiguredEntryLink({ compact = false }: Readonly<{ compact?: boolean }>) {
  const { isAuthenticated, isLoading, login } = useAuth();
  const [connecting, setConnecting] = useState(false);
  const [failed, setFailed] = useState(false);
  const busy = isLoading || connecting;

  async function signIn() {
    setFailed(false);
    setConnecting(true);
    try {
      await login();
    } catch (error) {
      console.error("Google sign-in could not start:", error);
      setFailed(true);
      setConnecting(false);
    }
  }

  if (isAuthenticated) return <Link className={compact ? compactLink : primaryLink} href="/home">Open workspace{!compact && <ArrowIcon />}</Link>;

  return <div className="landing-auth-action">
    <button className={compact ? compactLink : primaryLink} disabled={busy} aria-busy={busy} onClick={() => void signIn()} type="button">
      {isLoading ? "Checking session…" : connecting ? "Connecting to Google…" : compact ? "Sign in" : "Start rehearsing"}
      {!compact && !busy && <ArrowIcon />}
    </button>
    {failed && <p className="landing-auth-error" role="alert">Google sign-in couldn’t start. Please try again.</p>}
  </div>;
}

function EntryLink({ compact = false }: Readonly<{ compact?: boolean }>) {
  if (isAuth0Configured) return <ConfiguredEntryLink compact={compact} />;
  return <div className="landing-auth-action"><button className={compact ? compactLink : primaryLink} disabled type="button">{compact ? "Sign in" : "Start rehearsing"}</button>{!compact && <p className="landing-auth-error" role="status">Google sign-in is temporarily unavailable. Please try again later.</p>}</div>;
}

const landingFeatures = [
  { name: "Slide Analyzer", icon: "slides" as const, text: "Review your content and visual design, with suggestions for each slide." },
  { name: "Transcript Enhancer", icon: "script" as const, text: "Generate an editable script or refine your own words for your audience." },
  { name: "Live Practice", icon: "live" as const, text: "Practise on camera with near-real-time feedback on your delivery." },
  { name: "Upload Practice", icon: "video" as const, text: "Replay moments from a recording with body language and speech feedback." },
];

export default function HomePage() {
  const [activeFeature, setActiveFeature] = useState(0);
  const [paused, setPaused] = useState(false);
  const [interacting, setInteracting] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (paused || interacting || reducedMotion) return;
    const timer = window.setInterval(() => setActiveFeature(value => (value + 1) % landingFeatures.length), 6500);
    return () => window.clearInterval(timer);
  }, [paused, interacting, reducedMotion, activeFeature]);
  const active = landingFeatures[activeFeature];
  const previewCaptions = ["Feedback beside your slides", "A script you can make your own", "Coaching as you present", "Replay the moments that matter"];
  return (
    <main className="landing-page">
      <nav className="landing-nav" aria-label="Primary navigation">
        <Link className={`rounded-lg no-underline ${focusStyle}`} href="/"><Brand /></Link>
        <div className="landing-nav-actions"><a href="#ways-to-prepare">Explore the tools</a><EntryLink compact /></div>
      </nav>
      <div className="landing-scroll">
        <div className="landing-content">
          <section className="landing-hero" aria-labelledby="hero-title">
            <div className="landing-copy">
              <p className="landing-eyebrow">Your presentation coach</p>
              <h1 id="hero-title">Clearer slides.<br />Stronger words.<br /><span>Better delivery.</span></h1>
              <p className="landing-description">Work on what you say, what you show, and how you present. Bring your slides or a recorded rehearsal, and leave with something to practise.</p>
              <div className="landing-entry"><EntryLink /><span>Continue with your Google account</span></div>
              <p className="landing-support">From your first draft to your next rehearsal.</p>
            </div>
            <div className="landing-product" role="region" aria-label="Feature showcase" aria-roledescription="carousel" onMouseEnter={() => setInteracting(true)} onMouseLeave={() => setInteracting(false)} onFocusCapture={() => setInteracting(true)} onBlurCapture={event => { if (!event.currentTarget.contains(event.relatedTarget)) setInteracting(false); }}>
              <div className="landing-product-heading"><span>{active.name}</span><span>{previewCaptions[activeFeature]}</span></div>
              <div id="landing-feature-preview" role="tabpanel" aria-labelledby={`landing-feature-${activeFeature}`}><LandingFeaturePreview index={activeFeature} /></div>
              <div className="landing-carousel-footer"><span>Example interface · {activeFeature + 1} of 4</span><button type="button" onClick={() => setPaused(value => !value)} disabled={reducedMotion} aria-label={paused || reducedMotion ? "Resume feature rotation" : "Pause feature rotation"}>{paused || reducedMotion ? "▶ Play" : "Ⅱ Pause"}</button></div>
            </div>
          </section>
          <section className="landing-tools" id="ways-to-prepare" aria-labelledby="landing-tools-title">
            <div className="landing-tools-heading"><h2 id="landing-tools-title">Four ways to get ready.</h2><p>One workspace, from preparation to practice.</p></div>
            <div className="landing-tools-grid" role="tablist" aria-label="Explore presentation tools" onMouseEnter={() => setInteracting(true)} onMouseLeave={() => setInteracting(false)} onFocusCapture={() => setInteracting(true)} onBlurCapture={event => { if (!event.currentTarget.contains(event.relatedTarget)) setInteracting(false); }}>{landingFeatures.map((feature, index) => <button type="button" role="tab" id={`landing-feature-${index}`} aria-controls="landing-feature-preview" aria-selected={activeFeature === index} tabIndex={activeFeature === index ? 0 : -1} className={activeFeature === index ? "is-active" : ""} key={feature.name} onClick={() => setActiveFeature(index)} onKeyDown={event => {
              const next = event.key === "ArrowRight" ? (index + 1) % 4 : event.key === "ArrowLeft" ? (index + 3) % 4 : event.key === "Home" ? 0 : event.key === "End" ? 3 : null;
              if (next !== null) { event.preventDefault(); setActiveFeature(next); document.getElementById(`landing-feature-${next}`)?.focus(); }
            }}>
              <span className="landing-tool-icon"><FeatureIcon kind={feature.icon} /></span>
              <h3>{feature.name}</h3><p>{feature.text}</p>
            </button>)}</div>
          </section>
          <footer className="landing-footer"><span>Rehearse AI</span><span>Built for a more prepared presentation.</span></footer>
        </div>
      </div>
    </main>
  );
}

function FeatureIcon({ kind }: { kind: "slides" | "script" | "live" | "video" }) {
  const paths = {
    video: <><rect x="3" y="5" width="18" height="14" rx="3" /><path d="m10 9 5 3-5 3z" /></>,
    slides: <><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21l4-4 4 4M7 9h10M7 13h6" /></>,
    script: <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h5" /></>,
    live: <><rect x="3" y="5" width="18" height="14" rx="3" /><circle cx="12" cy="11" r="2.5" /><path d="M7 19v-1a5 5 0 0 1 10 0v1" /></>,
  };
  return <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">{paths[kind]}</svg>;
}
