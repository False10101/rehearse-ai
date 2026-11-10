"use client";

import "./transcript-dialogs.css";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

export function TranscriptBulkDrawer({ slides, range, replaceExisting, settings, dirty, busy, error, onRange, onReplaceExisting, onGenerate, onClose }: {
  slides: Array<{ slide_number: number; paragraphs: Array<{ current: string }> }>;
  range: { start: number; end: number }; replaceExisting: boolean; settings: string[]; dirty: boolean; busy: boolean; error: string;
  onRange: (range: { start: number; end: number }) => void; onReplaceExisting: (value: boolean) => void;
  onGenerate: () => void; onClose: () => void;
}) {
  const dialog = useRef<HTMLElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const selected = slides.filter((slide) => slide.slide_number >= range.start && slide.slide_number <= range.end);
  const existing = selected.filter((slide) => slide.paragraphs.some((part) => part.current.trim())).length;
  const empty = selected.length - existing;
  const count = replaceExisting ? selected.length : empty;
  const focus = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#8e7cf4]";
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    close.current?.focus();
    return () => { document.body.style.overflow = overflow; previous?.focus({ preventScroll: true }); };
  }, []);
  if (typeof document === "undefined") return null;
  return createPortal(<div className="transcript-dialog-overlay transcript-bulk-overlay fixed inset-0 z-[90] flex justify-end bg-[#191724]/45 font-sans text-[#302b3b] backdrop-blur-[4px]">
    <section ref={dialog} role="dialog" aria-modal="true" aria-labelledby="bulk-setup-title" className="transcript-dialog transcript-bulk-dialog flex h-dvh w-full max-w-[460px] flex-col border-l border-white/70 bg-white shadow-[-16px_0_70px_-20px_rgba(25,20,50,0.3)]" onKeyDown={(event) => {
      if (event.key === "Escape" && !busy) { event.preventDefault(); onClose(); }
      if (event.key !== "Tab") return;
      const controls = Array.from(dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled), select:not(:disabled), input:not(:disabled)") ?? []);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }}>
      <header className="flex shrink-0 items-start justify-between gap-4 border-b border-[#eeecf2] px-7 py-6">
        <div><h2 id="bulk-setup-title" className="m-0 text-xl font-semibold tracking-tight">Generate slide scripts</h2><p className="mb-0 mt-2 text-sm leading-6 text-[#8a8394]">Choose your slides and what to keep.</p></div>
        <button ref={close} type="button" disabled={busy} onClick={onClose} aria-label="Close generation settings" className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg text-[#8b8595] hover:bg-[#f3f1f8] disabled:opacity-40 ${focus}`}><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg></button>
      </header>
      <div className="transcript-bulk-content min-h-0 flex-1 overflow-y-auto px-7 py-6">
        <div className="mb-3 flex items-center justify-between"><h3 className="m-0 text-sm font-semibold">Slide range</h3><button type="button" disabled={busy} onClick={() => onRange({ start: slides[0].slide_number, end: slides[slides.length - 1].slide_number })} className={`rounded text-xs font-medium text-[#7359d6] hover:text-[#5038b5] ${focus}`}>Select all slides</button></div>
        <div className="grid grid-cols-2 gap-3">
          <label className="grid gap-2 text-xs text-[#8a8394]">From<select disabled={busy} value={range.start} onChange={(event) => { const start = Number(event.target.value); onRange({ start, end: Math.max(start, range.end) }); }} className={`transcript-select h-11 rounded-lg border border-[#e4dfea] bg-white px-3 text-sm font-medium text-[#62596e] ${focus}`}>{slides.map((slide) => <option key={slide.slide_number} value={slide.slide_number}>Slide {slide.slide_number}</option>)}</select></label>
          <label className="grid gap-2 text-xs text-[#8a8394]">To<select disabled={busy} value={range.end} onChange={(event) => onRange({ ...range, end: Number(event.target.value) })} className={`transcript-select h-11 rounded-lg border border-[#e4dfea] bg-white px-3 text-sm font-medium text-[#62596e] ${focus}`}>{slides.filter((slide) => slide.slide_number >= range.start).map((slide) => <option key={slide.slide_number} value={slide.slide_number}>Slide {slide.slide_number}</option>)}</select></label>
        </div>
        <section className="mt-7 border-t border-[#eeecf2] pt-6">
          <h3 className="mb-3 mt-0 text-sm font-semibold">Existing scripts</h3>
          <label className={`transcript-replace-option flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition-colors ${replaceExisting ? "border-[#dcd3f7] bg-[#faf8ff]" : "border-[#e8e3ee] bg-[#faf9fc]"}`}>
            <input type="checkbox" disabled={busy} checked={replaceExisting} onChange={(event) => onReplaceExisting(event.target.checked)} className={`mt-0.5 h-4 w-4 shrink-0 accent-[#6850db] ${focus}`} />
            <span><span className="block text-[0.8125rem] font-semibold leading-5">Include slides that already have a script</span><span className="mt-1.5 block text-xs leading-5 text-[#8a8394]">Replace AI-generated and manually written scripts in this range. Their saved versions stay in Version history.</span></span>
          </label>
          <p className="mb-0 mt-3 text-xs leading-5 text-[#8a8394]">{replaceExisting ? "All selected slides will receive a new script." : "Only empty slides will be generated. Existing scripts stay unchanged."}</p>
        </section>
        <section className="mt-7 border-t border-[#eeecf2] pt-6">
          <h3 className="mb-3 mt-0 text-sm font-semibold">Generation settings</h3>
          <div className="flex flex-wrap gap-2">{settings.map((setting) => <span key={setting} className="rounded-md bg-[#f5f2fa] px-2.5 py-1.5 text-xs text-[#796c8b]">{setting}</span>)}</div>
          <p className="mb-0 mt-3 text-xs leading-5 text-[#a198ad]">Uses the settings selected in Script controls.</p>
        </section>
        <div className="mt-7 rounded-xl border border-[#e7e0f7] bg-[#faf8ff] px-4 py-4" aria-live="polite">
          <p className="m-0 text-sm font-semibold text-[#6546ce]">{count ? `${count} ${count === 1 ? "slide" : "slides"} to generate` : "No empty slides in this range"}</p>
          <p className="mb-0 mt-1.5 text-xs leading-5 text-[#8a7d9f]">{replaceExisting ? `${empty} empty · ${existing} existing ${existing === 1 ? "script" : "scripts"} replaced` : `${empty} empty · ${existing} existing ${existing === 1 ? "script" : "scripts"} kept`}</p>
        </div>
      </div>
      <footer className="shrink-0 border-t border-[#eeecf2] px-7 py-5">
        {error && <p role="alert" className="mb-3 mt-0 text-xs leading-5 text-[#b33c50]">{error}</p>}
        {dirty && <p className="mb-3 mt-0 text-xs leading-5 text-[#8a8394]">Your current edits will be saved before generation starts.</p>}
        <div className="flex justify-end gap-2"><button type="button" disabled={busy} onClick={onClose} className={`rounded-lg border border-[#e4dfea] px-4 py-2.5 text-sm font-medium text-[#796d89] disabled:opacity-40 ${focus}`}>Cancel</button><button type="button" disabled={busy || count === 0} onClick={onGenerate} className={`rounded-lg bg-[#6850db] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#5941ca] disabled:bg-[#eae6f4] disabled:text-[#aaa0be] ${focus}`}>{busy ? "Saving edits…" : replaceExisting && existing ? `Regenerate ${count} ${count === 1 ? "slide" : "slides"}` : `Generate ${count} ${count === 1 ? "slide" : "slides"}`}</button></div>
      </footer>
    </section>
  </div>, document.body);
}
