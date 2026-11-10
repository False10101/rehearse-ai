"use client";

import "./transcript-dialogs.css";

import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { phraseMatches } from "@/lib/transcript-highlights";

type Term = { term: string; definition: string; pronunciation: string | null };
type Upgrade = { original: string; suggested: string; reason: string };
type Annotation = {
  range: Range; paragraphId: string; start: number; end: number;
  term?: Term; upgrade?: Upgrade; key: string;
};

function textRange(element: HTMLElement, start: number, end: number): Range | null {
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  let offset = 0, node: Node | null;
  const range = document.createRange();
  let found = false;
  while ((node = walker.nextNode())) {
    const length = node.textContent?.length ?? 0;
    if (!found && start < offset + length) { range.setStart(node, start - offset); found = true; }
    if (found && end <= offset + length) { range.setEnd(node, end - offset); return range; }
    offset += length;
  }
  return null;
}

export function ScriptHighlights({ editor, terms, upgrades, dirty, busy, enabled, onToggle, onApply }: {
  editor: RefObject<HTMLDivElement | null>; terms: Term[]; upgrades: Upgrade[]; dirty: boolean; busy: boolean;
  enabled: boolean; onToggle: (value: boolean) => void;
  onApply: (paragraphId: string, start: number, end: number, replacement: string) => Promise<boolean>;
}) {
  const [dismissed, setDismissed] = useState<string[]>([]);
  const [active, setActive] = useState<Annotation | null>(null);
  const [anchor, setAnchor] = useState({ left: 0, top: 0 });
  const [available, setAvailable] = useState(0);
  const [error, setError] = useState("");
  const annotations = useRef<Annotation[]>([]);
  const popover = useRef<HTMLDivElement>(null);
  const reviewButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const root = editor.current;
    if (!root) return;
    const registry = typeof CSS !== "undefined" && "highlights" in CSS ? CSS.highlights : null;
    setActive(null); setError("");
    annotations.current = [];
    registry?.delete("script-terms"); registry?.delete("script-vocabulary");
    if (!enabled || dirty) { setAvailable(0); return; }
    const explainedTerms = new Set<string>();
    for (const element of root.querySelectorAll<HTMLElement>("[data-paragraph-id]")) {
      const text = element.textContent ?? "";
      const occupied: Array<{ start: number; end: number }> = [];
      // Actionable suggestions take precedence when two annotations overlap.
      const candidates = [
        ...upgrades.map((upgrade) => ({ phrase: upgrade.original, upgrade, term: undefined as Term | undefined })),
        ...terms.map((term) => ({ phrase: term.term, term, upgrade: undefined as Upgrade | undefined })),
      ].sort((a, b) => Number(Boolean(b.upgrade)) - Number(Boolean(a.upgrade)) || b.phrase.length - a.phrase.length);
      for (const candidate of candidates) {
        const key = candidate.upgrade ? `upgrade:${candidate.phrase}:${candidate.upgrade.suggested}` : `term:${candidate.phrase}`;
        if (dismissed.includes(key) || (candidate.term && explainedTerms.has(key))) continue;
        for (const match of phraseMatches(text, candidate.phrase)) {
          if (occupied.some((part) => match.start < part.end && match.end > part.start)) continue;
          const range = textRange(element, match.start, match.end);
          if (!range) continue;
          occupied.push(match);
          annotations.current.push({ ...match, range, paragraphId: element.dataset.paragraphId!, key, term: candidate.term, upgrade: candidate.upgrade });
          if (candidate.term) { explainedTerms.add(key); break; }
        }
      }
    }
    annotations.current.sort((a, b) => a.range.compareBoundaryPoints(Range.START_TO_START, b.range));
    setAvailable(annotations.current.length);
    if (registry && typeof Highlight !== "undefined") {
      registry.set("script-terms", new Highlight(...annotations.current.filter((item) => item.term).map((item) => item.range)));
      registry.set("script-vocabulary", new Highlight(...annotations.current.filter((item) => item.upgrade).map((item) => item.range)));
    }
    const click = (event: MouseEvent) => {
      if (!window.getSelection()?.isCollapsed) return;
      const item = annotations.current.find((item) => Array.from(item.range.getClientRects()).some((rect) => event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom));
      setActive(item ?? null); setError("");
    };
    root.addEventListener("click", click);
    return () => {
      root.removeEventListener("click", click);
      registry?.delete("script-terms"); registry?.delete("script-vocabulary");
    };
  }, [editor, terms, upgrades, dirty, enabled, dismissed]);

  useLayoutEffect(() => {
    if (!active) return;
    const rect = active.range.getBoundingClientRect();
    const height = popover.current?.offsetHeight ?? 240;
    setAnchor({
      left: Math.max(12, Math.min(rect.left, window.innerWidth - 332)),
      top: Math.max(12, rect.bottom + height + 12 <= window.innerHeight ? rect.bottom + 8 : rect.top - height - 8),
    });
    const dismiss = (event: PointerEvent) => {
      if (!popover.current?.contains(event.target as Node) && !reviewButton.current?.contains(event.target as Node) && !editor.current?.contains(event.target as Node)) setActive(null);
    };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { setActive(null); reviewButton.current?.focus(); } };
    const scroll = (event: Event) => { if (!popover.current?.contains(event.target as Node)) setActive(null); };
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("keydown", escape);
    document.addEventListener("scroll", scroll, true);
    window.addEventListener("resize", scroll);
    return () => {
      document.removeEventListener("pointerdown", dismiss);
      document.removeEventListener("keydown", escape);
      document.removeEventListener("scroll", scroll, true);
      window.removeEventListener("resize", scroll);
    };
  }, [active, editor]);

  const move = (direction: number) => {
    const list = annotations.current;
    if (!list.length) return;
    const index = active ? list.indexOf(active) : -1;
    const item = list[(index + direction + list.length) % list.length];
    setActive(null); setError("");
    item.range.startContainer.parentElement?.scrollIntoView({ block: "nearest" });
    requestAnimationFrame(() => setActive(item));
  };
  const focus = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#8e7cf4]";
  return <>
    <div className="flex items-center gap-3 text-[0.6875rem] text-[#8a8394]">
      <label className="inline-flex cursor-pointer items-center gap-1.5"><input type="checkbox" checked={enabled} onChange={(event) => onToggle(event.target.checked)} className={`h-3.5 w-3.5 accent-[#7963c7] ${focus}`} />Highlights</label>
      {enabled && available > 0 && !dirty && <button ref={reviewButton} type="button" onClick={() => { move(1); requestAnimationFrame(() => requestAnimationFrame(() => popover.current?.querySelector<HTMLButtonElement>("button")?.focus())); }} className={`rounded text-[#7963a7] hover:text-[#574276] ${focus}`}>Review</button>}
      {enabled && dirty && <span>Save to refresh</span>}
    </div>
    {active && !dirty && enabled && createPortal(<div ref={popover} role="dialog" aria-label={active.upgrade ? "Wording suggestion" : "Term explanation"} className="transcript-highlight-popover fixed z-[80] w-[320px] max-w-[calc(100vw-24px)] rounded-xl border border-[#e6e1ec] bg-white p-4 font-sans text-[#51485d] shadow-[0_8px_28px_rgba(38,24,60,0.14)]" style={anchor}>
      <div className="mb-2 flex items-center justify-between gap-3"><span className="text-[0.6875rem] text-[#9b92a5]">{active.upgrade ? "Wording suggestion" : "Term explanation"}</span><button type="button" aria-label="Close highlight details" onClick={() => { setActive(null); reviewButton.current?.focus(); }} className={`rounded px-1 text-[#9b92a5] ${focus}`}>×</button></div>
      <p className="m-0 break-words text-sm font-semibold">{active.upgrade?.original ?? active.term?.term}</p>
      {active.term && <><p className="mb-0 mt-2 text-xs leading-5 text-[#756a82]">{active.term.definition}</p>{active.term.pronunciation && <p className="mb-0 mt-2 text-xs text-[#9b92a5]">Say it: {active.term.pronunciation}</p>}</>}
      {active.upgrade && <><p className="mb-0 mt-2 break-words text-sm text-[#736038]">→ {active.upgrade.suggested}</p><p className="mb-0 mt-2 text-xs leading-5 text-[#8a7d92]">{active.upgrade.reason}</p>{error && <p role="alert" className="mb-0 mt-2 text-xs text-[#b33c50]">{error}</p>}<div className="mt-3 flex gap-2"><button type="button" disabled={busy} onClick={async () => {
        const applied = await onApply(active.paragraphId, active.start, active.end, active.upgrade!.suggested);
        if (applied) setActive(null); else setError("Couldn’t apply this suggestion. Your script is unchanged; please retry or reload.");
      }} className={`rounded-md bg-[#6850db] px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40 ${focus}`}>{busy ? "Saving…" : "Apply"}</button><button type="button" disabled={busy} onClick={() => { setDismissed((items) => [...items, active.key]); setActive(null); }} className={`rounded-md border border-[#e6e1ec] px-3 py-1.5 text-xs text-[#8a7d92] ${focus}`}>Dismiss</button></div></>}
      <div className="mt-3 flex items-center justify-between border-t border-[#f0edf4] pt-2 text-[0.6875rem] text-[#a198ad]"><span>{annotations.current.indexOf(active) + 1} of {available}</span><div className="flex gap-3"><button type="button" aria-label="Previous highlight" onClick={() => move(-1)} className={`rounded px-1 ${focus}`}>←</button><button type="button" aria-label="Next highlight" onClick={() => move(1)} className={`rounded px-1 ${focus}`}>→</button></div></div>
    </div>, document.body)}
  </>;
}
