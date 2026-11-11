"use client";

import Link from "next/link";

import "./home.css";

import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/auth-provider";
import { Brand } from "@/components/brand";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type PresentationListItem = {
  kind?: "presentation" | "recording";
  id: string;
  title: string;
  original_filename: string;
  status: string;
  slide_count: number | null;
  created_at: string;
};

function UploadIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="17" viewBox="0 0 18 18" width="17">
      <path d="M9 12.75V3.5m0 0L5.75 6.75M9 3.5l3.25 3.25M3 11.75v1.5A1.75 1.75 0 0 0 4.75 15h8.5A1.75 1.75 0 0 0 15 13.25v-1.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="15" viewBox="0 0 16 16" width="15">
      <path d="M3.25 8h9.5M9 4.25 12.75 8 9 11.75" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.55" />
    </svg>
  );
}

function statusStyle(status: string) {
  if (status === "completed") return { label: "Ready", className: "bg-[#e8f8ef] text-[#168b50]", dot: "bg-[#20a762]" };
  if (status === "failed") return { label: "Needs attention", className: "bg-[#fff0f2] text-[#bd4050]", dot: "bg-[#d74b5b]" };
  if (status === "processing") return { label: "Analyzing", className: "bg-[#f0edff] text-[#6652dd]", dot: "bg-[#735ef1] animate-pulse" };
  return { label: "Queued", className: "bg-[#fff3df] text-[#a76510]", dot: "bg-[#df8c22]" };
}

function presentationDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Recently added";
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" }).format(date);
}

export default function WorkspaceHomePage() {
  const { getAccessToken, logout, isGuest } = useAuth();
  const [presentations, setPresentations] = useState<PresentationListItem[]>([]);
  const [loadingPresentations, setLoadingPresentations] = useState(true);
  const [presentationsError, setPresentationsError] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [search, setSearch] = useState("");

  useEffect(() => {
    let active = true;
    let refreshing = false;

    async function loadPresentations(silent = false) {
      if (refreshing) return;
      refreshing = true;
      if (!silent) setLoadingPresentations(true);
      try {
        const accessToken = await getAccessToken();
        const response = await fetch(`${apiBaseUrl}/api/v1/presentations`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        const result: unknown = await response.json().catch(() => null);
        if (!response.ok || !Array.isArray(result)) throw new Error("Your presentations could not be loaded.");
        const recordingsResponse = await fetch(apiBaseUrl + "/api/v1/practice/upload/sessions", { headers: { Authorization: "Bearer " + accessToken } });
        const recordings: unknown = await recordingsResponse.json().catch(() => null);
        if (!recordingsResponse.ok || !Array.isArray(recordings)) throw new Error("Your recordings could not be loaded. Please retry.");
        const combined = [...(result as PresentationListItem[]).map(item => ({ ...item, kind: "presentation" as const })), ...(recordings as PresentationListItem[]).map(item => ({ ...item, kind: "recording" as const }))];
        combined.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
        if (active) { setPresentations(combined); setPresentationsError(null); setRefreshError(null); }
      } catch (error) {
        if (active) {
          const message = error instanceof Error ? error.message : "Your recent work could not be loaded.";
          if (silent) setRefreshError(message); else setPresentationsError(message);
        }
      } finally {
        refreshing = false;
        if (active) setLoadingPresentations(false);
      }
    }

    void loadPresentations();
    const refresh = () => { if (document.visibilityState === "visible") void loadPresentations(true); };
    const timer = window.setInterval(refresh, 5000);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => { active = false; window.clearInterval(timer); window.removeEventListener("focus", refresh); document.removeEventListener("visibilitychange", refresh); };
  }, [getAccessToken, reloadKey]);

  const filteredPresentations = presentations.filter((presentation) =>
    presentation.original_filename.toLowerCase().includes(search.trim().toLowerCase()),
  );
  const focusStyle = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7661ef] focus-visible:ring-offset-2";
  const featureStyle = "home-tool";
  const features = [
    { name: "Slide Analyzer", icon: "slides" as const, description: "Find what works in your deck and what needs a second look.", action: "Analyze a deck", href: "/slide" },
    { name: "Transcript Enhancer", icon: "script" as const, description: "Turn your slides into a script that sounds like you.", action: "Work on your script", href: "/transcript" },
    { name: "Live Practice", icon: "live" as const, description: "Practice on camera with feedback as you present.", action: "Start a session", href: "/live" },
    { name: "Upload Practice", icon: "video" as const, description: "Review your delivery with feedback on a recorded rehearsal.", action: "Upload a rehearsal", href: "/upload-practice" },
  ];

  return (
    <main className="home-workspace">
      <nav className="home-nav" aria-label="Workspace navigation">
        <div className="flex items-center gap-7">
          <Link className={`rounded-lg no-underline ${focusStyle}`} href="/home"><Brand /></Link>
          <span className="hidden border-l border-[#e6e3ed] pl-7 text-sm font-medium text-[#797383] sm:block">Workspace</span>
        </div>
        <button className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-[#777180] transition hover:bg-[#f5f3fa] hover:text-[#302b40] ${focusStyle}`} onClick={logout} type="button">
          <WorkspaceIcon kind="logout" /> {isGuest ? "Leave guest workspace" : "Log out"}
        </button>
      </nav>

      <div className="home-scroll">
        <div className="home-content">
          <header className="home-intro">
            <div>
              <p className="home-kicker">Your workspace</p><h1>Ready for your next presentation.</h1>
              <p className="home-intro-description">Refine your slides, find your words, and practice your delivery.</p>
            </div>
            <div className="home-workspace-note"><span>Prepare. Practise. Improve.</span><span>Everything for your next presentation, in one place.</span></div>
          </header>


          <section className="home-tools" aria-labelledby="features-title">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="m-0 text-sm font-semibold text-[#575063]" id="features-title">Start something new</h2>
              <span className="hidden text-xs text-[#8b8496] sm:block">Four ways to prepare</span>
            </div>
            <div className="home-tool-grid">
              {features.map((feature) => {
                const content = <>
                  <div className="flex items-center justify-between">
                    <span className="home-tool-icon"><WorkspaceIcon kind={feature.icon} /></span>
                  </div>
                  <h3 className="home-tool-title">{feature.name}</h3>
                  <p className="home-tool-description">{isGuest && feature.icon === "video" ? "Explore body language and speech feedback from our sample recording." : feature.description}</p>
                  <span className="home-tool-action">
                    {isGuest && feature.icon === "video" ? "Explore sample report" : feature.action}<ArrowIcon />
                  </span>
                </>;
                return <Link className={featureStyle} href={feature.href} key={feature.name}>{content}</Link>;
              })}
            </div>
          </section>

          <section className="home-library" aria-labelledby="recent-title">
            <div className="home-library-toolbar">
              <div>
                <div className="flex items-center gap-2.5">
                  <h2 className="m-0 text-[15px] font-semibold tracking-[-0.02em]" id="recent-title">Recent work</h2>
                  {!loadingPresentations && !presentationsError ? <span className="text-xs tabular-nums text-[#9b93a7]">{presentations.length}</span> : null}
                </div>
                <p className="mb-0 mt-1 text-xs text-[#8a8296]">Pick up where you left off.</p>
              </div>
              <label className="home-search">
                <WorkspaceIcon kind="search" />
                <input aria-label="Search recent work" className="min-w-0 flex-1 border-0 bg-transparent py-2 text-xs text-[#47404f] outline-none placeholder:text-[#a29aaa]" placeholder="Search recent work…" value={search} onChange={(event) => setSearch(event.target.value)} type="search" />
              </label>
            </div>

            <div className="home-table-heading">
              <span>Presentation / recording</span><span>Status</span><span>Added</span><span className="text-right">Open in</span>
            </div>
            {refreshError && <p role="status" className="m-0 border-b border-[#eeeaf3] px-6 py-2 text-xs text-[#a76510]">Status refresh failed. Your last loaded work is shown; retrying automatically.</p>}
            <div className="home-library-scroll">
              {loadingPresentations ? (
                <div className="space-y-5 px-6 py-6" role="status" aria-label="Loading presentations">
                  {[0, 1, 2].map((item) => <div className="flex animate-pulse items-center gap-4 motion-reduce:animate-none" key={item}><span className="h-11 w-11 rounded-xl bg-[#f0edf5]" /><div className="flex-1 space-y-2"><div className="h-3 w-2/5 rounded bg-[#f0edf5]" /><div className="h-2 w-1/5 rounded bg-[#f5f3f8]" /></div></div>)}
                </div>
              ) : presentationsError ? (
                <div className="grid min-h-52 place-items-center px-6 py-8 text-center" role="alert">
                  <div><h3 className="m-0 text-sm font-semibold">We couldn’t load your recent work</h3><p className="mt-2 text-sm text-[#8a8095]">{presentationsError}</p><button className={`rounded-lg border border-[#ded7ee] px-4 py-2 text-xs font-semibold text-[#7259d3] ${focusStyle}`} onClick={() => setReloadKey((value) => value + 1)} type="button">Try again</button></div>
                </div>
              ) : presentations.length === 0 ? (
                <div className="grid min-h-56 place-items-center px-6 py-8 text-center">
                  <div className="max-w-sm">
                    <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-[#f3efff] text-[#856de3]"><WorkspaceIcon kind="slides" /></span>
                    <h3 className="mb-0 mt-4 text-base font-semibold">A fresh start for your next presentation</h3>
                    <p className="mb-0 mt-2 text-sm leading-6 text-[#8a8196]">Add a PowerPoint deck to start working on your slides.</p>
                    <Link className={`mt-4 inline-flex items-center gap-2 rounded-lg bg-[#7660df] px-4 py-2.5 text-xs font-semibold text-white ${focusStyle}`} href="/slide"><UploadIcon />Upload a presentation</Link>
                    <p className="mb-0 mt-3 text-[11px] text-[#a39aaa]">PPTX · up to 30 MB</p>
                  </div>
                </div>
              ) : filteredPresentations.length === 0 ? (
                <div className="px-6 py-12 text-center"><p className="m-0 text-sm text-[#807589]">No items match “{search}”.</p><button className={`mt-3 rounded px-2 py-1 text-xs font-semibold text-[#7259d3] ${focusStyle}`} onClick={() => setSearch("")} type="button">Clear search</button></div>
              ) : (
                <ul className="m-0 list-none divide-y divide-[#f0ecf5] p-0">
                  {filteredPresentations.map((presentation) => {
                    const status = statusStyle(presentation.status);
                    return (
                      <li className="home-work-row" key={`${presentation.kind}-${presentation.id}`}>
                        <div className="flex min-w-0 items-center gap-3">
                          <span className="home-file-icon"><WorkspaceIcon kind={presentation.kind === "recording" ? "video" : "slides"} /></span>
                          <div className="min-w-0">
                            <p className="m-0 truncate text-[13px] leading-5 font-medium text-[#3c334b]" title={presentation.original_filename}>{presentation.original_filename}</p>
                            <p className="mb-0 mt-1 text-[11px] leading-4 text-[#9b90a7]">{presentation.kind === "recording" ? "Recording" : `Presentation · ${presentation.slide_count ?? "—"} slides`}<span className="md:hidden"> · {status.label} · {presentationDate(presentation.created_at)}</span></p>
                          </div>
                        </div>
                        <div className="hidden md:block"><span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium ${status.className}`}><span className={`h-1.5 w-1.5 rounded-full ${status.dot}`} />{status.label}</span></div>
                        <span className="hidden text-[11px] text-[#94889f] md:block">{presentationDate(presentation.created_at)}</span>
                        <div className="flex items-center gap-2 pl-14 sm:justify-end sm:pl-0">
                          {presentation.kind === "recording" ? <Link className="home-open-button" href={"/upload-practice?session=" + presentation.id}>Report</Link> : <>
                            <Link className="home-open-button" href={"/slide?presentation=" + presentation.id}>Slides</Link>
                            <Link className="home-open-button" href={"/transcript?presentation=" + presentation.id}>Script</Link>
                          </>}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}

function WorkspaceIcon({ kind }: { kind: "slides" | "script" | "live" | "video" | "search" | "logout" }) {
  const paths = {
    slides: <><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21l4-4 4 4M7 9h10M7 13h6" /></>,
    script: <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h5" /></>,
    live: <><rect x="3" y="5" width="18" height="14" rx="3" /><circle cx="12" cy="11" r="2.5" /><path d="M7 19v-1a5 5 0 0 1 10 0v1" /></>,
    video: <><rect x="3" y="5" width="18" height="14" rx="3" /><path d="m10 9 5 3-5 3z" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>,
    logout: <><path d="M9 4H5v16h4M9 12h12m-4-4 4 4-4 4" /></>,
  };
  return <svg aria-hidden="true" width={kind === "search" || kind === "logout" ? 16 : 21} height={kind === "search" || kind === "logout" ? 16 : 21} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{paths[kind]}</svg>;
}
