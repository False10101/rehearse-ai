"use client";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

export type SaveWarning = {
  confirmation_required: true;
  review_id: string;
  slide_number: number;
  title: string | null;
  warnings: Array<{ passage: string; explanation: string; suggestion: string }>;
};

export function TranscriptSaveWarning({ review, busy, error, onCancel, onConfirm }: {
  review: SaveWarning; busy: boolean; error: string; onCancel: () => void; onConfirm: () => void;
}) {
  const dialog = useRef<HTMLDivElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    cancel.current?.focus();
    return () => { document.body.style.overflow = overflow; previous?.focus({ preventScroll: true }); };
  }, []);
  return createPortal(<div className="fixed inset-0 z-[150] grid place-items-center bg-[#171724]/40 p-6 backdrop-blur-[3px]">
    <div ref={dialog} role="dialog" aria-modal="true" aria-labelledby="save-warning-title" aria-describedby="save-warning-description"
      className="flex max-h-[calc(100dvh-48px)] w-full max-w-[620px] flex-col overflow-hidden rounded-xl border border-[#e6e4ed] bg-white text-[#292533] shadow-[0_24px_80px_-20px_rgba(25,20,50,0.3)]"
      onKeyDown={event => {
        if (event.key === "Escape" && !busy) { event.preventDefault(); onCancel(); }
        if (event.key !== "Tab") return;
        const buttons = Array.from(dialog.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? []);
        if (!buttons.length) { event.preventDefault(); return; }
        const first = buttons[0], last = buttons[buttons.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }}>
      <header className="shrink-0 border-b border-[#ece8e0] px-6 py-5">
        <p className="m-0 text-xs font-medium text-[#8e6728]">Slide {review.slide_number}{review.title ? ` · ${review.title}` : ""}</p>
        <h2 id="save-warning-title" className="mb-0 mt-2 text-xl font-semibold tracking-[-0.025em]">Check this before saving</h2>
        <p id="save-warning-description" className="mb-0 mt-2 text-[13px] leading-5 text-[#746e7d]">Part of your script may not match this slide. Your edits are still here and haven’t been saved yet.</p>
      </header>
      <div className="min-h-0 overflow-y-auto px-6 py-5">
        <div className="grid gap-5">{review.warnings.map((warning, index) => <section key={index}>
          <h3 className="m-0 text-xs font-semibold text-[#746e7d]">Passage to review</h3>
          <blockquote className="mx-0 mb-3 mt-2 border-l-[3px] border-[#d8b577] bg-[#fcf8f0] px-4 py-3 text-[13px] leading-6 text-[#514534]">“{warning.passage}”</blockquote>
          <h3 className="mb-1 mt-0 text-xs font-semibold">Why it may not fit</h3>
          <p className="m-0 text-[13px] leading-6 text-[#696271]">{warning.explanation}</p>
          <h3 className="mb-1 mt-3 text-xs font-semibold">What to reconsider</h3>
          <p className="m-0 text-[13px] leading-6 text-[#696271]">{warning.suggestion}</p>
        </section>)}</div>
        {error && <p role="alert" className="mb-0 mt-4 text-[13px] leading-5 text-[#b43d50]">{error}</p>}
      </div>
      <footer className="flex shrink-0 items-center justify-between gap-4 border-t border-[#ece9f1] bg-[#fcfbfd] px-6 py-4">
        <span className="text-xs text-[#8a8294]">You decide what to keep.</span>
        <div className="flex gap-2">
          <button ref={cancel} type="button" disabled={busy} onClick={onCancel} className="rounded-lg border border-[#ded9e7] bg-white px-4 py-2 text-xs font-medium text-[#62576f] disabled:opacity-50">Keep editing</button>
          <button type="button" disabled={busy} onClick={onConfirm} className="rounded-lg bg-[#6751de] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy ? "Saving…" : "Save anyway"}</button>
        </div>
      </footer>
    </div>
  </div>, document.body);
}
