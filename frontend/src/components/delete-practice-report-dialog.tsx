"use client";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

export function DeletePracticeReportDialog({ busy, onCancel, onConfirm }: {
  busy: boolean; onCancel: () => void; onConfirm: () => void;
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
  if (typeof document === "undefined") return null;
  return createPortal(<div className="practice-delete-overlay">
    <div ref={dialog} role="alertdialog" aria-modal="true" aria-labelledby="delete-practice-title" aria-describedby="delete-practice-description" tabIndex={-1} onKeyDown={event => {
      if (event.key === "Escape" && !busy) { event.preventDefault(); onCancel(); }
      if (event.key !== "Tab") return;
      const controls = Array.from(dialog.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? []);
      if (!controls.length) { event.preventDefault(); return; }
      if (event.shiftKey && document.activeElement === controls[0]) { event.preventDefault(); controls.at(-1)?.focus(); }
      else if (!event.shiftKey && document.activeElement === controls.at(-1)) { event.preventDefault(); controls[0]?.focus(); }
    }}>
      <span className="practice-delete-icon" aria-hidden="true"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7" /></svg></span>
      <h2 id="delete-practice-title">Delete this report?</h2>
      <p id="delete-practice-description">This permanently removes the report and its saved frames, replay clips, and audio excerpts. This cannot be undone.</p>
      <div><button ref={cancel} type="button" disabled={busy} onClick={onCancel}>Keep report</button><button type="button" disabled={busy} onClick={onConfirm}>{busy ? "Deleting…" : "Delete report"}</button></div>
    </div>
  </div>, document.body);
}
