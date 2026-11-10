"use client";

import "./live-overlays.css";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

export function EndLiveSessionDialog({ onCancel, onConfirm }: { onCancel: () => void; onConfirm: () => void }) {
  const dialog = useRef<HTMLDivElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    cancel.current?.focus();
    return () => { document.body.style.overflow = overflow; previous?.focus({ preventScroll: true }); };
  }, []);
  if (typeof document === "undefined") return null;
  return createPortal(<div className="live-end-overlay fixed inset-0 z-[130] grid place-items-center bg-[#191724]/45 p-5 backdrop-blur-[4px]">
    <div ref={dialog} role="alertdialog" aria-modal="true" aria-labelledby="end-live-title" aria-describedby="end-live-description" className="w-full max-w-[400px] rounded-2xl border border-white/70 bg-white p-6 font-sans shadow-[0_24px_70px_-20px_rgba(25,20,50,0.35)]" onKeyDown={(event) => {
      if (event.key === "Escape") { event.preventDefault(); onCancel(); }
      if (event.key !== "Tab") return;
      const controls = Array.from(dialog.current?.querySelectorAll<HTMLButtonElement>("button") ?? []);
      if (event.shiftKey && document.activeElement === controls[0]) { event.preventDefault(); controls.at(-1)?.focus(); }
      else if (!event.shiftKey && document.activeElement === controls.at(-1)) { event.preventDefault(); controls[0]?.focus(); }
    }}>
      <span aria-hidden="true" className="mb-4 grid h-10 w-10 place-items-center rounded-xl bg-[#fff0f3] text-[#b6556c]"><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2" /></svg></span>
      <h2 id="end-live-title" className="m-0 text-lg font-semibold tracking-tight text-[#382d45]">End this practice session?</h2>
      <p id="end-live-description" className="mb-0 mt-2 text-sm leading-6 text-[#8a7d95]">Tracking is paused while you decide. Ending will turn off your camera and clear this session’s coaching moments.</p>
      <div className="mt-6 flex justify-end gap-2">
        <button ref={cancel} type="button" onClick={onCancel} className="rounded-lg border border-[#e3ddea] bg-white px-3.5 py-2.5 text-xs font-semibold text-[#72647e] hover:bg-[#faf8fc] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#8e7cf4]">Keep practising</button>
        <button type="button" onClick={onConfirm} className="rounded-lg bg-[#b6556c] px-3.5 py-2.5 text-xs font-semibold text-white hover:bg-[#a1485d] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#c97084]">End session</button>
      </div>
    </div>
  </div>, document.body);
}
