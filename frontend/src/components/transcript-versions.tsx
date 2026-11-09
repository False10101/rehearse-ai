"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export type TranscriptVersion = {
  id: string; revision: number; change_type: string; created_at: string;
  paragraphs: string[]; settings: { tone?: string | null; style?: string | null; audience_level?: string | null; duration_seconds?: number | null };
  is_current: boolean; legacy: boolean; restored_from_id: string | null;
};

const labels: Record<string, string> = {
  generated: "AI generation", edited: "Manual edit", enhanced: "AI enhancement",
  restored: "Restored version", saved: "Saved script",
};
const settingLabels: Record<string, string> = {
  auto: "Automatic", informative: "Informative", persuasive: "Persuasive", conversational: "Conversational",
  natural: "Natural", formal: "Formal", beginner: "Beginner", general: "General", specialist: "Specialist",
};
function settingLabel(value: string) {
  return settingLabels[value] ?? value.replace(/[_-]/g, " ").replace(/^./, (letter) => letter.toUpperCase());
}
function savedDate(value: string) {
  return new Date(value).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

export function TranscriptVersions({ slideNumber, entries, current, loading, busy, dirty, error, onRetry, onRestore, onClose }: {
  slideNumber: number; entries: TranscriptVersion[]; current: string[]; loading: boolean; busy: boolean; dirty: boolean; error: string;
  onRetry: () => void; onRestore: (entry: TranscriptVersion) => void; onClose: () => void;
}) {
  const [filter, setFilter] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const filtered = entries.filter((entry) => filter === "all" || entry.change_type === filter);
  const selected = filtered.find((entry) => entry.id === selectedId) ?? filtered[0];

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    close.current?.focus();
    return () => { document.body.style.overflow = overflow; previous?.focus({ preventScroll: true }); };
  }, []);

  if (typeof document === "undefined") return null;
  const sameText = Boolean(selected && JSON.stringify(selected.paragraphs) === JSON.stringify(current));
  const settings = selected ? [
    selected.settings.tone && { name: "Tone", value: settingLabel(selected.settings.tone) },
    selected.settings.style && { name: "Style", value: settingLabel(selected.settings.style) },
    selected.settings.audience_level && { name: "Audience", value: settingLabel(selected.settings.audience_level) },
    selected.settings.duration_seconds && {
      name: "Length",
      value: `${({ 45: "Short", 75: "Standard", 105: "Detailed" } as Record<number, string>)[selected.settings.duration_seconds] ?? `${selected.settings.duration_seconds} sec`}`,
    },
  ].filter((item): item is { name: string; value: string } => Boolean(item)) : [];
  const focusStyle = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#8e7cf4]";

  return createPortal(
    <div className="fixed inset-0 z-[100] grid place-items-center bg-[#191724]/45 p-4 font-sans text-[#302b3b] backdrop-blur-[4px] sm:p-8">
      <div ref={dialog} role="dialog" aria-modal="true" aria-labelledby="transcript-versions-title" className="flex h-[min(700px,calc(100dvh-2rem))] w-full max-w-[1160px] flex-col overflow-hidden rounded-2xl border border-white/70 bg-white shadow-[0_28px_90px_-24px_rgba(25,20,50,0.4)] sm:h-[min(700px,calc(100dvh-4rem))]" onKeyDown={(event) => {
        if (event.key === "Escape" && !busy) { event.preventDefault(); onClose(); }
        if (event.key !== "Tab") return;
        const controls = Array.from(dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled), select:not(:disabled), [tabindex='0']") ?? []);
        const first = controls[0], last = controls.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }}>
        <header className="flex shrink-0 items-center justify-between gap-4 border-b border-[#eeecf2] px-6 py-5">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl border border-[#e6e1fa] bg-[#f7f5ff] text-[#7157dc]" aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round"><path d="M3 11a9 9 0 1 1 2.6 7M3 5v6h6m3-4v5l3 2" /></svg>
            </span>
            <div>
              <h2 id="transcript-versions-title" className="m-0 text-[1.125rem] font-semibold leading-6 tracking-[-0.025em]">Version history</h2>
              <p className="mb-0 mt-1 text-xs text-[#8a8394]">Slide {slideNumber}<span className="mx-2 text-[#c8c3d0]">·</span>Compare and restore a saved script</p>
            </div>
          </div>
          <button ref={close} type="button" disabled={busy} aria-label="Close version history" onClick={onClose} className={`grid h-8 w-8 place-items-center rounded-lg text-[#8b8595] transition-colors hover:bg-[#f3f1f8] hover:text-[#393243] disabled:opacity-40 ${focusStyle}`}>
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
          </button>
        </header>

        <div className="flex min-h-0 flex-1 flex-col sm:flex-row">
          <aside className="flex max-h-44 shrink-0 flex-col border-b border-[#eeecf2] bg-[#faf9fc] sm:max-h-none sm:w-[236px] sm:border-b-0 sm:border-r" aria-label="Saved versions">
            <div className="shrink-0 px-4 pb-3 pt-4">
              <label htmlFor="version-filter" className="mb-2 flex items-center justify-between text-xs font-medium text-[#797181]">Saved versions<span className="text-[0.6875rem] font-normal tabular-nums text-[#a19aa9]">{entries.length}</span></label>
              <select id="version-filter" value={filter} onChange={(event) => setFilter(event.target.value)} className={`transcript-select w-full rounded-lg border border-[#e4dfea] bg-white px-3 py-2 text-xs text-[#62596e] ${focusStyle}`}>
                <option value="all">All changes</option>
                {Object.entries(labels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
              </select>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3" aria-busy={loading}>
              {loading ? <p className="px-3 text-xs text-[#8a8394]">Loading versions…</p> : filtered.length ? filtered.map((entry) => {
                const active = selected?.id === entry.id;
                return <button key={entry.id} type="button" disabled={busy} aria-pressed={active} onClick={() => setSelectedId(entry.id)} className={`mb-1 block w-full rounded-lg border px-3 py-3 text-left transition-colors disabled:opacity-60 ${focusStyle} ${active ? "border-[#ded6fa] bg-white shadow-[0_2px_5px_rgba(45,28,95,0.04)]" : "border-transparent hover:bg-[#f0edf5]"}`}>
                  <span className="flex items-center justify-between gap-2">
                    <span className={`text-[0.8125rem] font-semibold ${active ? "text-[#6546ce]" : "text-[#51485d]"}`}>Version {entry.revision}</span>
                    {entry.is_current && <span className="rounded-full bg-[#eaf6ef] px-2 py-0.5 text-[0.625rem] font-medium text-[#38805a]">Current</span>}
                  </span>
                  <span className="mt-1 block text-xs text-[#7f758c]">{labels[entry.change_type] ?? "Saved script"}</span>
                  <time className="mt-2 block text-[0.6875rem] text-[#a19aa9]" dateTime={entry.created_at} title={new Date(entry.created_at).toLocaleString()}>{savedDate(entry.created_at)}</time>
                </button>;
              }) : <p className="px-3 text-xs text-[#8a8394]">No versions in this category.</p>}
            </div>
          </aside>

          <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            {selected && !loading ? <>
              <div className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-b border-[#eeecf2] px-5 py-3">
                {settings.map((item) => <div key={item.name} className="flex items-center gap-1.5 text-[0.6875rem]"><span className="text-[#9a92a5]">{item.name}</span><span className="font-medium text-[#62566f]">{item.value}</span></div>)}
                {!settings.length && <span className="text-xs text-[#8a8394]">{labels[selected.change_type] ?? "Saved script"}</span>}
                {(selected.legacy || selected.change_type === "saved") && <span className="ml-auto text-[0.6875rem] text-[#a19aa9]" title="This earlier saved script is available, but its individual edits were not recorded.">Earlier saved script</span>}
              </div>
              <div className="grid min-h-0 flex-1 grid-cols-2 divide-x divide-[#eeecf2]">
                {[{ title: "Current script", text: current, badge: "Saved" }, { title: `Version ${selected.revision}`, text: selected.paragraphs, badge: "Selected" }].map(({ title, text, badge }, index) => <section key={title} className={`flex min-h-0 min-w-0 flex-col ${index ? "bg-[#fdfcff]" : "bg-white"}`}>
                  <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-[#eeecf2] px-5 py-3.5">
                    <h3 className={`m-0 text-[0.8125rem] font-semibold leading-5 ${index ? "text-[#6850c9]" : "text-[#62596e]"}`}>{title}</h3>
                    <span className={`rounded px-1.5 py-0.5 text-[0.625rem] ${index ? "bg-[#f0ebfc] text-[#8872c5]" : "bg-[#f3f2f5] text-[#9a92a5]"}`}>{badge}</span>
                  </div>
                  <div role="region" aria-label={title} tabIndex={0} className="min-h-0 flex-1 overflow-y-auto overscroll-contain break-words px-5 py-5 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[#8e7cf4] sm:px-6">
                    {text.some((part) => part.trim()) ? text.map((part, position) => <p key={position} className="mb-5 mt-0 whitespace-pre-wrap text-[0.875rem] leading-[1.85] text-[#534a60] last:mb-0">{part || "\u00a0"}</p>) : <p className="m-0 text-sm italic text-[#a19aa9]">Empty script</p>}
                  </div>
                </section>)}
              </div>
            </> : <div className="grid flex-1 place-items-center p-6"><p className="text-sm text-[#8a8394]">{loading ? "Loading saved scripts…" : "Choose a version to compare."}</p></div>}
          </div>
        </div>

        <footer className="shrink-0 border-t border-[#eeecf2] bg-white px-6 py-4">
          {error && <p role="alert" className="mb-3 mt-0 text-xs text-[#b33c50]">{error} <button type="button" disabled={busy || loading} onClick={onRetry} className="underline">Reload history</button></p>}
          <div className="flex items-center justify-between gap-5">
            <p role="status" className="m-0 max-w-md text-xs leading-5 text-[#92899e]">{dirty ? "Save your edits before restoring a version." : busy ? "Restoring your script…" : selected?.is_current ? "You’re viewing the current version." : sameText ? "Same script text, with this version’s saved settings." : "Restoring creates a new version. Your current script stays in history."}</p>
            <div className="flex shrink-0 items-center gap-2">
              <button type="button" disabled={busy} onClick={onClose} className={`rounded-lg border border-[#e4dfea] bg-white px-4 py-2 text-[0.8125rem] font-medium text-[#796d89] transition-colors hover:bg-[#faf9fc] disabled:opacity-40 ${focusStyle}`}>Cancel</button>
              <button type="button" disabled={!selected || selected.is_current || dirty || busy || loading || Boolean(error)} onClick={() => selected && onRestore(selected)} className={`rounded-lg border border-[#6850db] bg-[#6850db] px-4 py-2 text-[0.8125rem] font-semibold text-white shadow-[0_1px_2px_rgba(69,38,153,0.12)] transition-colors hover:bg-[#5941ca] disabled:border-[#eae6f4] disabled:bg-[#eae6f4] disabled:text-[#aaa0be] disabled:shadow-none ${focusStyle}`}>{busy ? "Restoring…" : "Restore version"}</button>
            </div>
          </div>
        </footer>
      </div>
    </div>, document.body,
  );
}
