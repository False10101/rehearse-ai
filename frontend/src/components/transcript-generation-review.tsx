"use client";

import "./transcript-dialogs.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { compareWords } from "@/lib/transcript-highlights";

export type GenerationDraft = {
  id: string; slide_number: number; title: string | null; before: string[]; after: string[];
  tone: string; style: string; audience_level: string; duration_seconds: number; stale: boolean;
};

export function TranscriptGenerationReview({ drafts, initialDraftId, busy, error, onDecision, onClose }: {
  drafts: GenerationDraft[]; initialDraftId?: string; busy: boolean; error: string;
  onDecision: (draft: GenerationDraft, decision: "accept" | "decline") => void;
  onClose: () => void;
}) {
  const [selectedId, setSelectedId] = useState(initialDraftId ?? drafts[0]?.id);
  const [showChanges, setShowChanges] = useState(false);
  const showSlideList = useRef(drafts.length > 1).current;
  const current = drafts.find(d => d.id === selectedId) ?? drafts[0];
  const dialog = useRef<HTMLElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const comparison = useMemo(() => compareWords(current?.before.join("\n\n") ?? "", current?.after.join("\n\n") ?? ""), [current]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    close.current?.focus();
    return () => { document.body.style.overflow = overflow; previous?.focus({ preventScroll: true }); };
  }, []);
  if (!current || typeof document === "undefined") return null;
  const settings = [current.duration_seconds === 45 ? "Short" : current.duration_seconds === 105 ? "Detailed" : "Standard", `${current.tone} tone`, `${current.style} style`, `${current.audience_level} audience`];
  return createPortal(<div className="transcript-dialog-overlay generation-review-overlay">
    <section className="transcript-dialog generation-review-dialog" ref={dialog} role="dialog" aria-modal="true" aria-labelledby="generation-review-title" onKeyDown={event => {
      if (event.key === "Escape" && !busy) { event.preventDefault(); onClose(); }
      if (event.key !== "Tab") return;
      const controls = Array.from(dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled), [tabindex='0']") ?? []);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }}>
      <header className="generation-review-header">
        <div><h2 id="generation-review-title">Review generated scripts</h2><p>Accept or decline each replacement. Your saved scripts stay unchanged until accepted.</p></div>
        <button ref={close} type="button" aria-label="Close generation review" disabled={busy} onClick={onClose}>✕</button>
      </header>
      <div className={`generation-review-body ${!showSlideList ? "generation-review-single" : ""}`}>
        {showSlideList && <nav aria-label="Generated scripts to review" className="generation-review-list"><p>{drafts.length} awaiting review</p>{drafts.map(d => <button key={d.id} type="button" disabled={busy} aria-pressed={current.id === d.id} onClick={() => { setSelectedId(d.id); }}><span>Slide {d.slide_number}</span><strong>{d.title ?? "Untitled slide"}</strong>{d.stale && <small>Script has changed</small>}</button>)}</nav>}
        <div className="generation-review-detail">
          <div className="generation-review-settings"><strong>Slide {current.slide_number} · {current.title ?? "Untitled slide"}</strong><div>{settings.map(s => <span key={s}>{s}</span>)}</div><label><input type="checkbox" checked={showChanges} onChange={e => setShowChanges(e.target.checked)} /> Highlight changes</label></div>
          <div className="generation-review-panes">
            {(["before", "after"] as const).map(side => <section key={side}><h3>{side === "before" ? "Current script" : "Generated replacement"}</h3><div role="region" aria-label={side === "before" ? "Current script" : "Generated replacement"} tabIndex={0}><p>{showChanges ? comparison[side].map((span, i) => span.changed ? <mark className={side} key={i}>{span.text}</mark> : <span key={i}>{span.text}</span>) : current[side].join("\n\n")}</p></div></section>)}
          </div>
        </div>
      </div>
      <footer className="generation-review-footer">
        {current.stale && <p role="alert">The saved script has changed. Decline this draft and generate a new one.</p>}
        {error && <p role="alert">{error}</p>}
        <div><p>{busy ? "Saving your decision…" : `${drafts.length} ${drafts.length === 1 ? "script" : "scripts"} awaiting review · Closing keeps drafts for later.`}</p><button type="button" disabled={busy} onClick={() => onDecision(current, "decline")}>Decline slide {current.slide_number}</button><button type="button" disabled={busy || current.stale} onClick={() => onDecision(current, "accept")}>Accept slide {current.slide_number}</button></div>
      </footer>
    </section>
  </div>, document.body);
}
