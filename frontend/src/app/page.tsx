"use client";

import Link from "next/link";

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
const primaryLink = `inline-flex min-h-12 items-center justify-center gap-3 rounded-xl bg-[#7660df] px-6 text-sm font-semibold text-white no-underline shadow-[0_4px_12px_rgba(118,96,223,0.16)] transition hover:bg-[#6851cd] ${focusStyle}`;
const compactLink = `inline-flex min-h-10 items-center justify-center rounded-lg border border-[#e4deec] bg-white px-4 text-xs font-semibold text-[#736381] no-underline transition hover:border-[#c1b2d6] hover:bg-[#faf7fd] ${focusStyle}`;

function ConfiguredEntryLink({ compact = false }: Readonly<{ compact?: boolean }>) {
  const { isAuthenticated, isLoading } = useAuth();
  const label = isLoading ? "Checking session…" : isAuthenticated ? "Open workspace" : compact ? "Sign in" : "Start rehearsing";

  if (isLoading) return <span className={`${compact ? compactLink : primaryLink} opacity-60`} role="status">{label}</span>;

  return (
    <Link aria-disabled={isLoading} className={compact ? compactLink : primaryLink} href={isAuthenticated ? "/home" : "/login"}>
      {label}
      {!compact && !isLoading ? <ArrowIcon /> : null}
    </Link>
  );
}

function EntryLink({ compact = false }: Readonly<{ compact?: boolean }>) {
  if (isAuth0Configured) return <ConfiguredEntryLink compact={compact} />;

  return (
    <Link className={compact ? compactLink : primaryLink} href="/login">
      {compact ? "Sign in" : "Start rehearsing"}
      {!compact ? <ArrowIcon /> : null}
    </Link>
  );
}

function ProductPreview() {
  return (
    <div className="relative mx-auto w-full max-w-[47rem]" aria-label="Illustrative Slide Analyzer preview">
      <div className="absolute -left-7 top-14 h-28 w-28 rounded-full bg-[#b9adff]/35 blur-3xl" />
      <div className="absolute -right-8 bottom-8 h-36 w-36 rounded-full bg-[#9ad9e8]/30 blur-3xl" />

      <div className="relative overflow-hidden rounded-[22px] border border-white/90 bg-white shadow-[0_24px_55px_rgba(64,46,94,0.12)] ring-1 ring-[#dcd8ed]">
        <div className="flex h-11 items-center justify-between border-b border-[#ebe9f1] bg-[#fbfaff] px-4">
          <div className="flex items-center gap-1.5" aria-hidden="true">
            <span className="h-2.5 w-2.5 rounded-full bg-[#ff8f96]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#f5c660]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#61c98a]" />
          </div>
          <span className="text-[0.61rem] font-bold tracking-[0.02em] text-[#888493]">Rehearse AI · Deck review</span>
          <span className="h-5 w-5 rounded-md border border-[#e5e2ed] bg-white" />
        </div>

        <div className="grid min-h-[21rem] grid-cols-[12%_minmax(0,1fr)_32%] bg-[#f7f7fa]">
          <aside className="border-r border-[#e8e6ee] bg-white px-2.5 py-4 sm:px-3" aria-label="Slide thumbnails">
            <p className="mb-3 mt-0 text-[0.51rem] font-extrabold uppercase tracking-[0.12em] text-[#8b8795]">Slides</p>
            {["#dceee4", "#eeeaff", "#e9f2ff", "#fff0df"].map((colour, index) => (
              <div className={`mb-2.5 rounded-lg border p-1.5 ${index === 1 ? "border-[#8b77ff] bg-[#f5f2ff]" : "border-[#e5e3ea] bg-white"}`} key={colour}>
                <div className="aspect-video rounded-[4px] border border-black/5 bg-white p-1.5 shadow-sm">
                  <span className="block h-1 w-1/2 rounded-full bg-[#252238]" />
                  <div className="mt-2 grid grid-cols-3 gap-1">
                    {[0, 1, 2].map((column) => <span className="h-4 rounded-[2px]" key={column} style={{ backgroundColor: colour }} />)}
                  </div>
                </div>
              </div>
            ))}
          </aside>

          <section className="min-w-0 px-3 py-4 sm:px-5 sm:py-5">
            <div className="flex items-end justify-between gap-3">
              <div>
                <p className="m-0 text-[0.49rem] font-extrabold uppercase tracking-[0.11em] text-[#85818f]">Slide 02 of 04</p>
                <h2 className="mb-0 mt-1 text-[0.9rem] tracking-[-0.04em] text-[#1d1b29] sm:text-[1rem]">System overview</h2>
              </div>
              <span className="rounded-md border border-[#e2dfea] bg-white px-2 py-1 text-[0.52rem] font-bold text-[#656171]">100%</span>
            </div>

            <div className="mt-4 aspect-[16/10] overflow-hidden rounded-[11px] border border-[#dfdde6] bg-[#eeedf2] p-[5%] shadow-inner">
              <div className="relative h-full overflow-hidden rounded-[5px] bg-white px-[8%] py-[7%] shadow-[0_12px_25px_rgba(38,35,58,0.12)]">
                <p className="m-0 text-[0.42rem] font-extrabold uppercase tracking-[0.13em] text-[#735fff]">System overview</p>
                <h3 className="mb-0 mt-2 max-w-[84%] text-[clamp(0.72rem,1.4vw,1.18rem)] leading-[1.05] tracking-[-0.045em] text-[#1d1b2c]">A clearer path from deck to confident delivery.</h3>
                <p className="mb-0 mt-2 text-[0.45rem] leading-[1.5] text-[#777386]">One workspace for every stage of presentation preparation.</p>
                <div className="absolute bottom-[12%] left-[8%] right-[8%] grid grid-cols-[1fr_auto_1fr_auto_1fr] items-center gap-[3%]">
                  {["Review", "→", "Refine", "→", "Rehearse"].map((item, index) => index % 2 === 0
                    ? <div className="rounded-[5px] border border-[#cfc7ff] bg-[#f7f5ff] px-1 py-2 text-center text-[0.43rem] font-extrabold text-[#4f447e]" key={item}>{item}</div>
                    : <span className="text-[0.65rem] text-[#837b9d]" key={`${item}-${index}`}>{item}</span>)}
                </div>
              </div>
            </div>
          </section>

          <aside className="border-l border-[#e8e6ee] bg-white px-3 py-4 sm:px-4" aria-label="Slide feedback preview">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="m-0 text-[0.48rem] font-extrabold uppercase tracking-[0.1em] text-[#85818f]">Slide analysis</p>
                <p className="mb-0 mt-1 text-[0.7rem] font-extrabold text-[#252232]">Feedback</p>
              </div>
              <p className="m-0 text-[0.92rem] font-black tracking-[-0.05em] text-[#22a461]">8.4<span className="ml-0.5 text-[0.48rem] text-[#85818f]">/10</span></p>
            </div>
            <div className="mt-4 rounded-[8px] border border-[#ccebd9] bg-[#f4fff8] p-2.5">
              <p className="m-0 text-[0.55rem] font-extrabold text-[#178e51]">Clear and well structured</p>
              <p className="mb-0 mt-1.5 text-[0.5rem] leading-[1.45] text-[#607067]">The main flow is easy to follow at presentation distance.</p>
            </div>
            <p className="mb-0 mt-4 text-[0.54rem] font-extrabold text-[#373343]">Improve first</p>
            <div className="mt-2.5 grid gap-2">
              {["Strengthen the transition labels", "Reduce supporting copy", "Keep icon styles consistent"].map((item, index) => (
                <div className="grid grid-cols-[18px_1fr] gap-2" key={item}>
                  <span className="grid h-[18px] w-[18px] place-items-center rounded-[5px] bg-[#f0edff] text-[0.46rem] font-extrabold text-[#6651e8]">0{index + 1}</span>
                  <p className="m-0 pt-0.5 text-[0.5rem] leading-[1.4] text-[#5f5b6c]">{item}</p>
                </div>
              ))}
            </div>
          </aside>
        </div>
      </div>


    </div>
  );
}

export default function HomePage() {
  return (
    <main className="flex h-dvh flex-col overflow-hidden bg-[#faf9fc] text-[#292333]">
      <nav className="relative z-20 flex h-[4.5rem] flex-none items-center justify-between border-b border-[#e8e4ee] bg-white px-[clamp(1.25rem,4vw,4.5rem)]" aria-label="Primary navigation">
        <Link className={`rounded-lg no-underline ${focusStyle}`} href="/"><Brand /></Link>
        <div className="flex items-center gap-6">
          <span className="hidden text-xs text-[#91839c] sm:block">A little practice goes a long way.</span>
          <EntryLink compact />
        </div>
      </nav>

      <section className="mx-auto grid min-h-0 w-full max-w-[100rem] flex-1 items-center gap-8 px-[clamp(1.25rem,4vw,4.5rem)] py-[clamp(1rem,4vh,3rem)] lg:grid-cols-[0.86fr_1.14fr] lg:gap-[clamp(2rem,4vw,4rem)] [@media(max-height:600px)]:grid-cols-1" aria-labelledby="hero-title">
        <div className="mx-auto w-full max-w-[38rem] lg:mx-0">
          <p className="m-0 flex items-center gap-2.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8c73ad] sm:text-[11px]">
            <span className="h-px w-6 bg-[#ad99c9]" /> Your presentation, a little more prepared
          </p>
          <h1 className="mb-0 mt-6 text-[clamp(2.3rem,5vw,4.75rem)] font-semibold leading-[1.07] tracking-[-0.055em] [@media(max-height:650px)]:mt-4 [@media(max-height:650px)]:text-[clamp(2rem,7vh,3.5rem)]" id="hero-title">
            Clearer slides.<br />
            Stronger words.<br />
            <span className="text-[#9573bd]">Better delivery.</span>
          </h1>
          <p className="mb-0 mt-6 max-w-[28rem] text-[15px] leading-7 text-[#7e6f89] sm:text-base [@media(max-height:650px)]:mt-4 [@media(max-height:650px)]:text-sm [@media(max-height:650px)]:leading-6">
            Turn your deck into a presentation you’re ready to give. Get thoughtful slide feedback, shape your script, and practice on camera.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-x-4 gap-y-3 [@media(max-height:650px)]:mt-5">
            <EntryLink />
            <span className="text-xs text-[#8d7e99]">Sign in with Google to get started</span>
          </div>

          <div className="mt-10 flex flex-wrap gap-x-5 gap-y-3 border-t border-[#e7e0ee] pt-5 text-xs font-medium text-[#82718e] [@media(max-height:650px)]:mt-5 [@media(max-height:500px)]:hidden">
            <span className="inline-flex items-center gap-2"><FeatureIcon kind="slides" />Slide feedback</span>
            <span className="inline-flex items-center gap-2"><FeatureIcon kind="script" />Editable scripts</span>
            <span className="inline-flex items-center gap-2"><FeatureIcon kind="live" />Live practice</span>
          </div>
        </div>

        <div className="relative hidden h-full max-h-[44rem] min-h-0 flex-col justify-center rounded-[24px] border border-[#e8e0f1] bg-[#f0ebf7] px-5 py-8 lg:flex xl:px-7 [@media(max-height:650px)]:py-4 [@media(max-height:600px)]:hidden">
          <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden rounded-[24px]">
            <div className="absolute -right-28 -top-28 h-80 w-80 rounded-full border border-white/65" />
            <div className="absolute -bottom-36 -left-24 h-96 w-96 rounded-full border border-[#e3d8ee]" />
          </div>
          <div className="relative mb-6 flex items-center justify-between px-1 [@media(max-height:650px)]:mb-3">
            <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#8b72a8]">A closer look at your slides</span>
            <span className="grid h-7 w-7 place-items-center rounded-lg border border-white/70 bg-white/50 text-[#967caf]"><FeatureIcon kind="slides" /></span>
          </div>
          {/* Temporary illustration: replace with an actual Slide Analyzer screenshot. */}
          <ProductPreview />
          <div className="relative mt-6 flex items-start justify-between gap-4 px-1 [@media(max-height:650px)]:mt-3 [@media(max-height:550px)]:hidden">
            <p className="m-0 max-w-[18rem] text-xs leading-5 text-[#826b91]">Useful feedback, right beside the slide.<br />Know what to improve and where to begin.</p>
            <span className="flex-none pt-0.5 text-[10px] text-[#93809e]">Example preview</span>
          </div>
        </div>
      </section>
    </main>
  );
}

function FeatureIcon({ kind }: { kind: "slides" | "script" | "live" }) {
  const paths = {
    slides: <><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21l4-4 4 4M7 9h10M7 13h6" /></>,
    script: <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h5" /></>,
    live: <><rect x="3" y="5" width="18" height="14" rx="3" /><circle cx="12" cy="11" r="2.5" /><path d="M7 19v-1a5 5 0 0 1 10 0v1" /></>,
  };
  return <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">{paths[kind]}</svg>;
}
