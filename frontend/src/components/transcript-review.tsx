"use client";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

export type EnhancementPreview = {
  slide_number: number; base_revision: number; before: string[]; after: string[]; changed: boolean;
};
export type EnhancementHistory = {
  id: string; created_at: string; base_revision: number; result_revision: number;
  before: string | null; after: string; tone: string | null; style: string | null; audience_level: string | null;
};

export function TranscriptReview({ preview, settings, busy, error, onAccept, onCancel }: {
  preview: EnhancementPreview; settings: string; busy: boolean; error: string;
  onAccept: () => void; onCancel: () => void;
}) {
  const dialog = useRef<HTMLDivElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    cancel.current?.focus();
    return () => {
      document.body.style.overflow = overflow;
      previous?.focus({ preventScroll: true });
    };
  }, []);
  if (typeof document === "undefined") return null;
  return createPortal(
    <div className="fixed inset-0 z-[100] grid place-items-center bg-[#171724]/40 p-4 backdrop-blur-[3px] sm:p-8">
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="enhancement-review-title"
        className="flex max-h-[min(680px,calc(100dvh-2rem))] w-full max-w-[1080px] flex-col overflow-hidden rounded-xl border border-[#e6e4ed] bg-white shadow-[0_24px_80px_-20px_rgba(25,20,50,0.3)] sm:max-h-[min(680px,calc(100dvh-4rem))]"
        onKeyDown={(event) => {
          if (event.key === "Escape" && !busy) { event.preventDefault(); onCancel(); }
          if (event.key !== "Tab") return;
          if (busy) { event.preventDefault(); return; }
          const controls = Array.from(dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled), [tabindex='0']") ?? []);
          const first = controls[0], last = controls.at(-1);
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        }}
      >
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-[#e9e7ef] px-5 py-4 sm:px-6">
          <div className="min-w-0">
            <h2 id="enhancement-review-title" className="m-0 text-[1.125rem] font-semibold leading-6 tracking-[-0.025em] text-[#292533]">Review enhancement</h2>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="mr-1 text-xs text-[#807a8c]">Slide {preview.slide_number}</span>
              {settings.split(" · ").map((setting) => <span key={setting} className="rounded bg-[#f3f1f8] px-2 py-0.5 text-[0.6875rem] font-medium capitalize leading-5 text-[#716781]">{setting}</span>)}
            </div>
          </div>
          <button type="button" aria-label="Close enhancement review" disabled={busy} onClick={onCancel} className="-mr-1 grid h-8 w-8 shrink-0 place-items-center rounded-md text-[#8b8595] transition-colors hover:bg-[#f4f2f8] hover:text-[#393243] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#8e7cf4] disabled:opacity-40">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
          </button>
        </header>
        <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-2 divide-y divide-[#e9e7ef] overflow-hidden sm:grid-cols-2 sm:grid-rows-1 sm:divide-x sm:divide-y-0">
          <section className="flex min-h-0 min-w-0 flex-col bg-[#fafafb]" aria-labelledby="enhancement-previous-title">
            <h3 id="enhancement-previous-title" className="m-0 shrink-0 border-b border-[#eeecf2] px-5 py-2.5 text-[0.6875rem] font-semibold uppercase tracking-[0.07em] text-[#8b8594] sm:px-6">Current text</h3>
            <div tabIndex={0} role="region" aria-label="Previous selected text" className="min-h-0 flex-1 overflow-y-auto overscroll-contain break-words px-5 py-5 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[#8e7cf4] sm:px-6">
              {preview.before.map((part, index) => <p className="mb-4 mt-0 whitespace-pre-wrap text-sm leading-6 text-[#625b6b] last:mb-0" key={index}>{part}</p>)}
            </div>
          </section>
          <section className="flex min-h-0 min-w-0 flex-col bg-white" aria-labelledby="enhancement-new-title">
            <h3 id="enhancement-new-title" className="m-0 shrink-0 border-b border-[#eeecf2] bg-[#fcfbff] px-5 py-2.5 text-[0.6875rem] font-semibold uppercase tracking-[0.07em] text-[#6b52db] sm:px-6">Suggested text</h3>
            <div tabIndex={0} role="region" aria-label="New suggested text" className="min-h-0 flex-1 overflow-y-auto overscroll-contain break-words px-5 py-5 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[#8e7cf4] sm:px-6">
              {preview.after.map((part, index) => <p className="mb-4 mt-0 whitespace-pre-wrap text-sm leading-6 text-[#393442] last:mb-0" key={index}>{part}</p>)}
            </div>
          </section>
        </div>
        <footer className="shrink-0 border-t border-[#e9e7ef] bg-white px-5 py-3.5 sm:px-6">
          {!preview.changed && <p className="mb-3 mt-0 text-xs text-[#716d7d]">The suggestion matches your selected text.</p>}
          {error && <p role="alert" className="mb-3 mt-0 text-xs text-[#b33c50]">{error}</p>}
          <div className="flex flex-wrap items-center justify-end gap-x-5 gap-y-3">
            <p className="m-0 mr-auto text-xs text-[#8b8594]" role="status">{busy ? "Saving changes…" : "Changes apply only after you accept."}</p>
            <div className="ml-auto flex shrink-0 gap-2">
              <button ref={cancel} type="button" disabled={busy} className="rounded-md border border-[#e0dce8] bg-white px-3.5 py-2 text-[0.8125rem] font-semibold text-[#625b70] transition-colors hover:bg-[#f6f5f9] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#8e7cf4] disabled:opacity-40" onClick={onCancel}>Decline</button>
              <button type="button" disabled={busy || !preview.changed} className="rounded-md border border-[#6350df] bg-[#6350df] px-4 py-2 text-[0.8125rem] font-semibold text-white transition-colors hover:border-[#5542ce] hover:bg-[#5542ce] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#8e7cf4] disabled:opacity-40" onClick={onAccept}>{busy ? "Saving…" : "Accept change"}</button>
            </div>
          </div>
        </footer>
      </div>
    </div>, document.body,
  );
}

export function TranscriptHistory({ entries, error, onRetry }: { entries: EnhancementHistory[]; error: string; onRetry: () => void }) {
  return <section className="mx-auto mt-6 w-full max-w-[760px] rounded-xl border border-[#e0dce9] bg-white px-6 py-5" aria-label="Accepted enhancement history">
    <h3 className="m-0 text-sm font-bold">Change history <span className="ml-2 text-xs font-normal text-[#827b8e]">Accepted enhancements</span></h3>
    {error ? <p role="alert" className="mb-0 text-sm text-[#a14354]">{error} <button type="button" className="underline" onClick={onRetry}>Retry</button></p> : entries.length ? <div className="mt-4 divide-y divide-[#edeaf3]">{entries.map((entry) => <details key={entry.id} className="py-3">
      <summary className="cursor-pointer text-sm font-semibold text-[#53476c]">Revision {entry.result_revision} · <span className="capitalize">{[entry.tone, entry.style, entry.audience_level && `${entry.audience_level} audience`].filter(Boolean).join(" · ") || "Text enhancement"}</span><span className="ml-2 text-xs font-normal text-[#827b8e]">{new Date(entry.created_at).toLocaleString()}</span></summary>
      <div className="mt-4 grid grid-cols-2 gap-4 max-[760px]:grid-cols-1"><div className="rounded-lg bg-[#f6f5f8] p-4"><h4 className="mb-2 mt-0 text-xs text-[#777180]">Before</h4><p className="m-0 whitespace-pre-wrap text-sm leading-6">{entry.before ?? "The original text was not stored for this older change."}</p></div><div className="rounded-lg bg-[#f6f3ff] p-4"><h4 className="mb-2 mt-0 text-xs text-[#6450d3]">After</h4><p className="m-0 whitespace-pre-wrap text-sm leading-6">{entry.after}</p></div></div>
    </details>)}</div> : <p className="mb-0 text-sm text-[#827b8e]">Accepted text enhancements will appear here, with the original and replacement side by side.</p>}
  </section>;
}
