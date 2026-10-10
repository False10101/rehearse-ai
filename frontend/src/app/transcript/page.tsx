"use client";

import { DeckUpload } from "@/components/deck-upload";
import { ProcessingSteps } from "@/components/processing-steps";
import Link from "next/link";
import { ExportDownload } from "@/components/export-download";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent } from "react";
import { useAuth } from "@/components/auth/auth-provider";
import { Brand } from "@/components/brand";
import { processingMessage } from "@/lib/processing-message";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
type Tone = "auto" | "persuasive" | "informative" | "conversational";
type Style = "natural" | "formal";
type AudienceLevel = "beginner" | "general" | "specialist";
type Mode = "ai-gen" | "human-enhance";
type Paragraph = { id: string; position: number; original: string | null; current: string };
type TranscriptSlide = {
  slide_number: number; title: string | null; image_url: string | null; transcript_id: string | null;
  revision: number | null; mode: string | null; paragraphs: Paragraph[];
  requested_tone: Tone | null; requested_style: Style | null; requested_audience_level?: AudienceLevel | null; requested_duration_seconds: 45 | 75 | 105 | null;
  tone_matches_request: boolean | null;
  coaching_analysis_available: boolean;
  complex_terms: Array<{ term: string; definition: string; pronunciation: string | null }>;
  tone_check: { classification: string | null; confidence: number | null; rationale: string | null } | null;
  vocabulary_upgrades: Array<{ original: string; suggested: string; reason: string }>;
};
type TranscriptResponse = { preparation_progress: number | null; preparation_status: string | null; presentation_id: string; filename: string; status: string; processing_error_code: string | null; bulk_generation_status: string | null; bulk_generation_progress: number | null; slide_count: number | null; slides: TranscriptSlide[] };
type TextSelection = { text: string; start: { paragraph_id: string; offset: number }; end: { paragraph_id: string; offset: number } };
type PendingAction = { type: "slide"; index: number } | { type: "route"; href: string } | { type: "generate-all" } | { type: "generate-slide" };
type SlideRange = { start: number; end: number };

function wordCount(paragraphs: Paragraph[]) { return paragraphs.flatMap((paragraph) => paragraph.current.trim().split(/\s+/)).filter(Boolean).length; }
function apiError(payload: unknown, fallback: string) { return typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string" ? payload.detail : fallback; }

function useProtectedSlideImage(imageUrl: string | null, accessToken: string | null) {
  const [source, setSource] = useState<string | null>(null);
  useEffect(() => {
    if (!imageUrl || !accessToken) { setSource(null); return; }
    let active = true; let objectUrl: string | null = null;
    async function loadImage() {
      try {
        const response = await fetch(`${apiBaseUrl}${imageUrl}`, { headers: { Authorization: `Bearer ${accessToken}` } });
        if (!response.ok) throw new Error("Slide preview unavailable.");
        objectUrl = URL.createObjectURL(await response.blob());
        if (active) setSource(objectUrl);
      } catch { if (active) setSource(null); }
    }
    void loadImage();
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [accessToken, imageUrl]);
  return source;
}

function TranscriptThumbnail({ slide, accessToken }: { slide: TranscriptSlide; accessToken: string | null }) {
  const source = useProtectedSlideImage(slide.image_url, accessToken);
  return <div className="grid aspect-video w-full place-items-center overflow-hidden rounded border border-[#e5e4eb] bg-white shadow-[0_1px_2px_rgba(27,27,47,0.03)]">{source ? <img alt={`${slide.title ?? "Untitled"} thumbnail`} className="h-full w-full object-cover" src={source} /> : <span className="px-2 text-center text-[0.42rem] font-bold text-[#858394]">{slide.title ?? "Untitled slide"}</span>}</div>;
}

function OptionGrid<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: readonly T[]; onChange: (value: T) => void }) {
  return <div><span className="mb-[0.36rem] block text-[0.66rem] font-extrabold uppercase tracking-[0.055em] text-[#777583]">{label}</span><div className="grid grid-cols-2 gap-1.5">{options.map((option) => <button className={`rounded-[6px] border px-[0.38rem] py-[0.43rem] text-[0.62rem] font-bold capitalize ${value === option ? "border-[#a99dff] bg-[#f6f4ff] text-[#5e4ce0]" : "border-[#e5e4ea] bg-white text-[#777583]"}`} key={option} type="button" onClick={() => onChange(option)}>{option}</button>)}</div></div>;
}

export default function TranscriptEnhancerPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { getAccessToken, isAuthenticated, isLoading: authLoading } = useAuth();
  const presentationId = searchParams.get("presentation");
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [data, setData] = useState<TranscriptResponse | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [mode, setMode] = useState<Mode>("ai-gen");
  const [duration, setDuration] = useState<45 | 75 | 105>(75);
  const [tone, setTone] = useState<Tone>("auto");
  const [style, setStyle] = useState<Style>("natural");
  const [audienceLevel, setAudienceLevel] = useState<AudienceLevel>("general");
  const [selection, setSelection] = useState<TextSelection | null>(null);
  const [actionNote, setActionNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [bulkGenerationState, setBulkGenerationState] = useState<"starting" | "tracking" | null>(null);
  const [rangeDrawerOpen, setRangeDrawerOpen] = useState(false);
  const [bulkRange, setBulkRange] = useState<SlideRange>({ start: 1, end: 1 });
  const [dirty, setDirty] = useState(false);
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const documentRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<HTMLDivElement>(null);

  const loadTranscript = useCallback(async (silent = false) => {
    if (!presentationId || !isAuthenticated) { setLoading(false); return; }
    if (!silent) setLoading(true);
    try {
      const token = await getAccessToken(); setAccessToken(token);
      const response = await fetch(`${apiBaseUrl}/api/v1/presentations/${presentationId}/transcript`, { headers: { Authorization: `Bearer ${token}` } });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new Error(apiError(payload, "Transcript could not be loaded."));
      setData(payload as TranscriptResponse); if (!silent) setActionNote("");
    } catch (error) { setActionNote(error instanceof Error ? error.message : "Transcript could not be loaded."); }
    finally { if (!silent) setLoading(false); }
  }, [getAccessToken, isAuthenticated, presentationId]);
  useEffect(() => { void loadTranscript(); }, [loadTranscript]);
  useEffect(() => {
    if (!data?.slides.length) return;
    setBulkRange({ start: data.slides[0].slide_number, end: data.slides.at(-1)!.slide_number });
  }, [presentationId, data?.slides.length]);
  useEffect(() => {
    const bulkRunning = data?.bulk_generation_status === "queued" || data?.bulk_generation_status === "running";
    if (!bulkRunning && data?.status !== "queued" && data?.status !== "processing") return;
    const timer = window.setInterval(() => { void loadTranscript(true); }, 2500);
    return () => window.clearInterval(timer);
  }, [data?.bulk_generation_status, data?.status, loadTranscript]);
  useEffect(() => {
    if (bulkGenerationState === "tracking" && data?.bulk_generation_status === "completed") {
      setBulkGenerationState(null);
      setActionNote("All slide scripts are ready.");
    }
  }, [bulkGenerationState, data?.bulk_generation_status]);

  const bulkRunning = data?.bulk_generation_status === "queued" || data?.bulk_generation_status === "running";
  const bulkFailed = bulkGenerationState === "tracking" && data?.bulk_generation_status === "failed";
  const bulkModalVisible = bulkGenerationState === "starting" || bulkRunning || bulkFailed;
  const bulkProgress = data?.bulk_generation_progress ?? 0;
  const bulkRangeCount = bulkRange.end - bulkRange.start + 1;
  const completedSlideCount = Math.min(bulkRangeCount, Math.round((bulkProgress / 100) * bulkRangeCount));

  const transcript = data?.slides[selectedIndex] ?? null;
  const paragraphs = transcript?.paragraphs ?? [];
  const words = useMemo(() => wordCount(paragraphs), [paragraphs]);
  const selectedGeneratedTone = transcript?.mode === "ai-gen" && transcript.requested_tone && transcript.requested_tone !== "auto" ? transcript.requested_tone : null;
  const visibleTone = selectedGeneratedTone ? `${selectedGeneratedTone[0].toUpperCase()}${selectedGeneratedTone.slice(1)}` : transcript?.tone_check?.classification;
  useEffect(() => {
    if (!transcript) return;
    if (transcript.requested_tone) setTone(transcript.requested_tone);
    if (transcript.requested_style) setStyle(transcript.requested_style);
    if (transcript.requested_audience_level) setAudienceLevel(transcript.requested_audience_level);
    if (transcript.requested_duration_seconds) setDuration(transcript.requested_duration_seconds);
  }, [transcript?.transcript_id]);
  const replaceSlide = useCallback((updated: TranscriptSlide) => setData((current) => current ? { ...current, slides: current.slides.map((slide) => slide.slide_number === updated.slide_number ? updated : slide) } : current), []);
  const clearSelection = useCallback(() => { window.getSelection()?.removeAllRanges(); setSelection(null); }, []);
  const activateSlide = (index: number) => { setSelectedIndex(index); setActionNote(""); setDirty(false); clearSelection(); };
  const selectSlide = (index: number) => {
    if (index === selectedIndex) return;
    if (dirty) { setPendingAction({ type: "slide", index }); return; }
    activateSlide(index);
  };
  const guardRoute = (event: MouseEvent<HTMLAnchorElement>, href: string) => {
    if (!dirty) return;
    event.preventDefault(); setPendingAction({ type: "route", href });
  };

  const captureSelection = () => {
    const current = window.getSelection(); const root = documentRef.current;
    if (!current || !root || current.isCollapsed || !root.contains(current.anchorNode) || !root.contains(current.focusNode)) { setSelection(null); return; }
    const range = current.getRangeAt(0);
    const elementFor = (node: Node) => (node.nodeType === Node.ELEMENT_NODE ? node as Element : node.parentElement)?.closest<HTMLElement>("[data-paragraph-id]");
    const startElement = elementFor(range.startContainer); const endElement = elementFor(range.endContainer);
    if (!startElement?.dataset.paragraphId || !endElement?.dataset.paragraphId) { setSelection(null); return; }
    const offsetIn = (container: HTMLElement, node: Node, offset: number) => { const before = document.createRange(); before.selectNodeContents(container); before.setEnd(node, offset); return before.toString().length; };
    const text = range.toString().replace(/\s+/g, " ").trim();
    if (!text) { setSelection(null); return; }
    setSelection({ text, start: { paragraph_id: startElement.dataset.paragraphId, offset: offsetIn(startElement, range.startContainer, range.startOffset) }, end: { paragraph_id: endElement.dataset.paragraphId, offset: offsetIn(endElement, range.endContainer, range.endOffset) } });
  };

  const saveScriptEdits = useCallback(async (): Promise<TranscriptSlide | null> => {
    if (!dirty || !transcript?.transcript_id || !transcript.revision || !presentationId || !accessToken) return transcript;
    const seenIds = new Set<string>();
    const edits = Array.from(editorRef.current?.childNodes ?? []).map((node) => {
      const element = node.nodeType === Node.ELEMENT_NODE ? node as HTMLElement : null;
      const paragraphId = element?.dataset.paragraphId;
      const id = paragraphId && !seenIds.has(paragraphId) ? paragraphId : null;
      if (paragraphId) seenIds.add(paragraphId);
      return { id, text: node.textContent?.trim() ?? "" };
    }).filter((paragraph) => Boolean(paragraph.text));
    if (!edits.length) edits.push({ id: transcript.paragraphs[0]?.id ?? null, text: "" });
    setWorking(true);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/presentations/${presentationId}/transcript/slides/${transcript.slide_number}`, { method: "PATCH", headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" }, body: JSON.stringify({ slide_transcript_id: transcript.transcript_id, base_revision: transcript.revision, paragraphs: edits }) });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new Error(apiError(payload, "Script could not be saved."));
      const updated = payload as TranscriptSlide; replaceSlide(updated); setDirty(false);
      setActionNote(updated.coaching_analysis_available ? "Script saved and coaching feedback refreshed." : "Script saved. Coaching feedback could not refresh; save again later to retry it.");
      return updated;
    } catch (error) { setActionNote(error instanceof Error ? error.message : "Script could not be saved."); return null; }
    finally { setWorking(false); }
  }, [accessToken, dirty, presentationId, replaceSlide, transcript]);

  const requestRegeneration = async () => {
    if (!presentationId || !accessToken || !transcript) return;
    if (mode === "human-enhance" && (!selection || !transcript.transcript_id || !transcript.revision)) { setActionNote(transcript.transcript_id ? "Select text in the document before enhancing it." : "Generate this slide first, then select text to enhance."); return; }
    setWorking(true); setActionNote("");
    try {
      if (mode === "ai-gen") {
        const response = await fetch(`${apiBaseUrl}/api/v1/presentations/${presentationId}/transcript/generate`, { method: "POST", headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" }, body: JSON.stringify({ slide_number: transcript.slide_number, duration_seconds: duration, tone, style, audience_level: audienceLevel }) });
        const payload: unknown = await response.json().catch(() => null);
        if (!response.ok) throw new Error(apiError(payload, "Script generation could not finish."));
        const updated = payload as TranscriptSlide;
        if (updated.slide_number !== transcript.slide_number) throw new Error("The server returned a script for the wrong slide. Nothing was replaced.");
        replaceSlide(updated); setActionNote(`Script for slide ${updated.slide_number} generated and saved.`);
      } else {
        if (dirty) {
          const saved = await saveScriptEdits();
          if (saved) {
            clearSelection();
            setActionNote("Edits saved. Reselect the passage you want to enhance.");
          }
          return;
        }
        const saved = await saveScriptEdits();
        if (!saved || !selection) return;
        const response = await fetch(`${apiBaseUrl}/api/v1/presentations/${presentationId}/transcript/enhance`, { method: "POST", headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" }, body: JSON.stringify({ slide_transcript_id: saved.transcript_id, base_revision: saved.revision, start: selection.start, end: selection.end, tone, style, audience_level: audienceLevel }) });
        const payload: unknown = await response.json().catch(() => null);
        if (!response.ok) throw new Error(apiError(payload, "Text enhancement could not finish."));
        const updated = payload as TranscriptSlide;
        if (updated.slide_number !== transcript.slide_number) throw new Error("The server returned enhanced text for the wrong slide. Nothing was replaced.");
        replaceSlide(updated); clearSelection(); setActionNote("Selected text enhanced and saved.");
      }
    } catch (error) { setActionNote(error instanceof Error ? error.message : "The request could not finish."); }
    finally { setWorking(false); }
  };

  const startHumanWriting = async () => {
    if (!presentationId || !accessToken || !transcript) return;
    setWorking(true); setActionNote("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/presentations/${presentationId}/transcript/human`, { method: "POST", headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" }, body: JSON.stringify({ slide_number: transcript.slide_number }) });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new Error(apiError(payload, "A blank script could not be created."));
      replaceSlide(payload as TranscriptSlide); setActionNote("Blank script created. Start writing in the document.");
    } catch (error) { setActionNote(error instanceof Error ? error.message : "A blank script could not be created."); }
    finally { setWorking(false); }
  };

  const generateAllSlides = async () => {
    if (!presentationId || !accessToken) return;
    setWorking(true); setBulkGenerationState("starting"); setActionNote("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/presentations/${presentationId}/transcript/generate-all`, { method: "POST", headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" }, body: JSON.stringify({ duration_seconds: duration, tone, style, audience_level: audienceLevel, start_slide: bulkRange.start, end_slide: bulkRange.end }) });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new Error(apiError(payload, "All-slide generation could not be started."));
      await loadTranscript(true); setBulkGenerationState("tracking");
    } catch (error) { setBulkGenerationState(null); setActionNote(error instanceof Error ? error.message : "All-slide generation could not be started."); }
    finally { setWorking(false); }
  };

  const requestAllGeneration = () => setRangeDrawerOpen(true);
  const requestSlideGeneration = () => {
    if (mode === "ai-gen" && dirty) { setPendingAction({ type: "generate-slide" }); return; }
    void requestRegeneration();
  };
  const confirmPendingAction = () => {
    const action = pendingAction;
    if (!action) return;
    setPendingAction(null);
    if (action.type === "slide") { activateSlide(action.index); return; }
    if (action.type === "route") { setDirty(false); router.push(action.href); return; }
    setDirty(false);
    if (action.type === "generate-all") { void generateAllSlides(); return; }
    void requestRegeneration();
  };
  useEffect(() => {
    if (!dirty) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [dirty]);

  const pendingActionTitle = pendingAction?.type === "generate-all" ? "Generate selected slide scripts?" : pendingAction?.type === "generate-slide" ? "Regenerate this slide?" : "Discard unsaved edits?";
  const pendingActionMessage = pendingAction?.type === "generate-all" ? (dirty ? `Slides ${bulkRange.start}–${bulkRange.end} will be checked. Save this slide first if you want its current edits preserved.` : `Only empty transcripts from slide ${bulkRange.start} through ${bulkRange.end} will be generated. Existing scripts will not be replaced.`) : pendingAction?.type === "generate-slide" ? "This replaces the current slide script and discards your unsaved edits." : pendingAction?.type === "slide" ? "Switching slides will discard the edits you have not saved." : "Leaving this page will discard the edits you have not saved.";
  const pendingActionConfirm = pendingAction?.type === "generate-all" ? "Generate range" : pendingAction?.type === "generate-slide" ? "Regenerate slide" : pendingAction?.type === "slide" ? "Discard & switch" : "Discard & leave";

  if (authLoading || loading) return <main className="grid h-dvh place-items-center bg-[#f7f7f9] text-sm font-semibold text-[#6e6c7b]">Loading transcript…</main>;
  if (!presentationId) return <DeckUpload mode="transcript" />;
  if (data && data.status !== "completed") return <main className="grid h-dvh place-items-center bg-[#f7f7f9] p-6 text-center text-[#6e6c7b]"><div><p className="text-[0.75rem] font-bold uppercase tracking-[0.1em] text-[#6753ea]">Transcript Enhancer</p><h1 className="mt-3 text-3xl tracking-[-0.06em]">{data?.status === "failed" ? "Deck preparation could not finish" : "Preparing your deck"}</h1><p className="mt-3 max-w-md text-sm leading-6">{data?.status === "failed" ? processingMessage(data.processing_error_code, "We couldn’t prepare this deck. Please try uploading it again.") : "Getting your slides ready so you can write or generate a presenter script."}</p>{data?.status !== "failed" && <ProcessingSteps steps={["Waiting to start", "Read slide content", "Render slide previews", "Review visual context", "Save prepared slides"]} current={data.preparation_status === "queued" ? 0 : (data.preparation_progress ?? 0) < 10 ? 1 : (data.preparation_progress ?? 0) < 25 ? 2 : (data.preparation_progress ?? 0) < 95 ? 3 : 4} />}{data?.status === "failed" ? <Link className="mt-5 inline-flex rounded-lg bg-[#18181e] px-4 py-2 text-sm font-bold text-white no-underline" href="/transcript">Try another deck</Link> : null}</div></main>;
  if (!data || !transcript) return <main className="grid h-dvh place-items-center bg-[#f7f7f9] p-6 text-center text-sm text-[#6e6c7b]"><div><p>{actionNote || "Transcript could not be loaded."}</p><button className="mt-3 rounded-lg bg-[#19191f] px-3 py-2 text-xs font-bold text-white" onClick={() => void loadTranscript()} type="button">Retry</button></div></main>;

  return <main className="h-dvh min-w-[860px] overflow-hidden bg-[#f7f7f9] font-sans text-[#171724]">
    <header className="relative grid min-h-[74px] grid-cols-[238px_minmax(0,1fr)_auto] items-center border-b border-[#e7e7ec] bg-white/95 max-[1220px]:grid-cols-[205px_minmax(0,1fr)_auto] max-[920px]:grid-cols-[170px_minmax(0,1fr)_auto]">
      <Link className="inline-flex h-full items-center justify-center no-underline hover:bg-[#faf9ff]" href="/home" onClick={(event) => guardRoute(event, "/home")} aria-label="Rehearse AI home"><Brand /></Link>
      <span aria-hidden className="absolute bottom-[22px] left-[238px] top-[22px] w-px rounded-full bg-gradient-to-b from-transparent via-[#8777ff] to-transparent shadow-[0_0_9px_rgba(124,105,255,0.17)] max-[1220px]:left-[205px] max-[920px]:left-[170px]" />
      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center px-5 max-[920px]:px-[0.9rem]"><h1 className="m-0 whitespace-nowrap text-[1.32rem] font-extrabold tracking-[-0.055em] text-[#20202c] max-[920px]:text-[1.16rem]">Transcript Enhancer</h1><div className="flex min-w-0 items-center justify-self-center gap-[0.9rem] text-[0.8rem] text-[#737382]"><strong className="max-w-[16rem] truncate">{data.filename}</strong><span className="before:mr-[0.9rem] before:text-[#bbbcc5] before:content-['•']">{data.slides.length} slides</span><span className="before:mr-[0.9rem] before:text-[#bbbcc5] before:content-['•'] max-[920px]:hidden">Saved</span></div></div>
      <div className="flex justify-self-end gap-2 pr-[1.1rem] max-[920px]:pr-3"><Link className="inline-flex min-h-[37px] items-center rounded-[10px] border border-[#e0e0e6] bg-white px-[0.8rem] text-[0.78rem] font-bold text-[#292936] no-underline" href={`/slide?presentation=${data.presentation_id}`} onClick={(event) => guardRoute(event, `/slide?presentation=${data.presentation_id}`)}><span className="mr-[0.38rem] grid h-[17px] w-[17px] place-items-center rounded bg-[#f0edff] text-[0.68rem] font-extrabold text-[#6350e8]" aria-hidden="true">▤</span>Slide analyzer</Link><ExportDownload path={`/api/v1/presentations/${data.presentation_id}/transcript/export`} filename="presentation-script.txt" disabled={dirty || working} title={dirty ? "Save your edits before exporting" : "Download saved script"} /></div>
    </header>
    <section className="grid h-[calc(100dvh-74px)] min-h-0 grid-cols-[238px_minmax(540px,1fr)_412px] overflow-hidden max-[1220px]:grid-cols-[205px_minmax(440px,1fr)_350px] max-[920px]:grid-cols-[170px_minmax(390px,1fr)_310px] max-[620px]:grid-cols-[150px_minmax(390px,1fr)_300px]" aria-label="Transcript enhancer workspace">
      <aside className="flex min-h-0 min-w-0 flex-col overflow-hidden border-r border-[#e7e7ec] bg-white"><div className="flex items-center border-b border-[#eeeef2] px-[1.15rem] py-[0.95rem]"><h2 className="m-0 text-[0.8rem] font-bold uppercase text-[#565563]">Slides <span className="text-[0.72rem] font-semibold normal-case text-[#9897a3]">· {data.slides.length} total</span></h2></div><div className="min-h-0 flex-1 overflow-y-auto px-[0.6rem] py-[0.65rem]">{data.slides.map((slide, index) => <button className={`grid w-full grid-cols-[23px_1fr] items-center gap-[0.45rem] rounded-[10px] border px-[0.4rem] py-[0.48rem] text-left hover:bg-[#f8f7ff] ${selectedIndex === index ? "border-[#a699ff] bg-[#f7f5ff] shadow-[0_0_0_1px_rgba(121,99,255,0.08)]" : "border-transparent bg-transparent"}`} key={slide.slide_number} onClick={() => selectSlide(index)} type="button" aria-current={selectedIndex === index ? "true" : undefined}><span className={`text-[0.7rem] font-bold tabular-nums ${selectedIndex === index ? "text-[#6757ed]" : "text-[#878793]"}`}>{String(slide.slide_number).padStart(2, "0")}</span><TranscriptThumbnail slide={slide} accessToken={accessToken} /></button>)}</div><div className="flex items-center gap-[0.4rem] border-t border-[#eeeef2] px-[1.15rem] py-[0.9rem] text-[0.71rem] text-[#777786]"><span className="h-[6px] w-[6px] rounded-full bg-[#29b770] shadow-[0_0_0_3px_#e8f9ef]" /> Transcript is saved</div></aside>
      <section className="grid min-h-0 min-w-0 grid-rows-[auto_minmax(0,1fr)_auto] bg-[#eff0f3] px-[clamp(1.5rem,3vw,2.75rem)] pb-[1.1rem] pt-6 max-[620px]:p-4" aria-label={`Transcript for slide ${transcript.slide_number}`}><div className="mb-[1.1rem] flex items-end justify-between"><div><p className="mb-[0.28rem] text-[0.73rem] font-bold uppercase tracking-[0.06em] text-[#81818f]">Slide {String(transcript.slide_number).padStart(2, "0")} of {data.slides.length}</p><h2 className="m-0 text-[1.42rem] leading-[1.1] tracking-[-0.055em]">{transcript.title ?? "Untitled slide"}</h2></div><span className="rounded-full border border-[#dcd7ff] bg-[#f6f4ff] px-[0.62rem] py-[0.32rem] text-[0.67rem] font-bold text-[#6550e5]">{mode === "ai-gen" ? "AI-generated" : "Human-enhanced"}</span></div>
        <div className="min-h-0 overflow-y-auto pb-4"><div ref={documentRef} className="mx-auto min-h-[min(860px,calc(100dvh-215px))] w-full max-w-[760px] select-text bg-white px-[clamp(2rem,6vw,5.25rem)] py-[clamp(2.25rem,5vw,4rem)] shadow-[0_12px_32px_rgba(34,32,51,0.13)]" onMouseUp={captureSelection}><div className="flex items-center justify-between border-b border-[#ecebf1] pb-[1.1rem]"><div><p className="m-0 text-[0.67rem] font-bold uppercase tracking-[0.08em] text-[#8a8896]">Presenter script</p><p className="mb-0 mt-[0.25rem] text-[0.78rem] text-[#767482]">{data.filename} · Slide {String(transcript.slide_number).padStart(2, "0")}</p></div><span className="text-[0.7rem] font-bold text-[#8b8995]">{words} words</span></div><div ref={editorRef} key={`${transcript.transcript_id ?? "empty"}-${transcript.revision ?? 0}-${mode}`} className={`mt-[2.1rem] grid min-h-[12rem] cursor-text content-start gap-[1.45rem] text-[0.94rem] leading-[1.82] text-[#2f2e3c] ${transcript.transcript_id ? "rounded-[5px] outline-none" : ""}`} contentEditable={Boolean(transcript.transcript_id)} suppressContentEditableWarning={Boolean(transcript.transcript_id)} role={transcript.transcript_id ? "textbox" : undefined} aria-multiline={transcript.transcript_id ? true : undefined} aria-label="Editable presenter script" onInput={() => setDirty(true)} onMouseUp={captureSelection}>{paragraphs.length ? paragraphs.map((paragraph) => <p className="m-0 whitespace-pre-wrap" data-paragraph-id={paragraph.id} data-transcript-paragraph key={paragraph.id}>{paragraph.current}</p>) : <p className="m-0 text-[#858390]">Generate a script or start writing to create one for this slide.</p>}</div><p className="mt-[2.4rem] border-t border-[#f0eff3] pt-[1rem] text-[0.69rem] leading-[1.45] text-[#92909c]">{transcript.transcript_id ? "Edit directly in the document, or select any portion to refine only that passage with AI." : "Generate a script from the slide, or start a blank script and write it yourself."}</p></div></div>
        <nav className="flex items-center justify-between pt-4 text-[0.76rem] tabular-nums text-[#81818d]" aria-label="Slide navigation"><button className="min-w-[95px] rounded-lg bg-white px-[0.65rem] py-[0.55rem] text-[0.77rem] font-bold text-[#4b4a5b] hover:bg-[#f0eeff] hover:text-[#5e4de3] disabled:cursor-not-allowed disabled:opacity-35" type="button" onClick={() => selectSlide(Math.max(0, selectedIndex - 1))} disabled={selectedIndex === 0}>← Previous</button><span><strong className="text-[#363642]">{String(transcript.slide_number).padStart(2, "0")}</strong> / {data.slides.length}</span><button className="min-w-[95px] rounded-lg bg-white px-[0.65rem] py-[0.55rem] text-[0.77rem] font-bold text-[#4b4a5b] hover:bg-[#f0eeff] hover:text-[#5e4de3] disabled:cursor-not-allowed disabled:opacity-35" type="button" onClick={() => selectSlide(Math.min(data.slides.length - 1, selectedIndex + 1))} disabled={selectedIndex === data.slides.length - 1}>Next →</button></nav>
      </section>
      <aside className="flex min-h-0 min-w-0 flex-col overflow-hidden border-l border-[#e7e7ec] bg-[#f7f7f9]"><div className="flex items-start justify-between bg-white px-[1.7rem] pb-5 pt-6"><div><p className="mb-[0.28rem] text-[0.73rem] font-bold uppercase tracking-[0.06em] text-[#81818f]">Transcript settings</p><h2 className="m-0 text-[1.08rem] tracking-[-0.045em]">Script coach</h2></div><span className="grid h-[30px] w-[30px] place-items-center rounded-[9px] bg-[#efedff] text-[0.9rem] font-extrabold text-[#6753e9]">✦</span></div><div className="grid min-h-0 flex-1 content-start gap-[0.9rem] overflow-y-auto bg-[#f7f7f9] px-[1.35rem] py-[1.2rem]">
        <section className="rounded-[10px] border border-[#e6e5eb] bg-white px-[0.9rem] py-[0.85rem]"><div className="flex items-center justify-between"><h3 className="m-0 text-[0.84rem] tracking-[-0.025em]">Script controls</h3><span className="text-[0.65rem] font-bold text-[#6550e5]">Editor</span></div><div className="mt-[0.72rem] grid grid-cols-2 gap-2 rounded-[8px] bg-[#f5f4f8] p-[0.18rem]"><button className={`rounded-[6px] px-[0.45rem] py-[0.48rem] text-[0.67rem] font-bold ${mode === "ai-gen" ? "bg-white text-[#5d49dd] shadow-[0_1px_3px_rgba(34,31,56,0.1)]" : "text-[#777583]"}`} type="button" onClick={() => setMode("ai-gen")}>AI generate</button><button className={`rounded-[6px] px-[0.45rem] py-[0.48rem] text-[0.67rem] font-bold ${mode === "human-enhance" ? "bg-white text-[#5d49dd] shadow-[0_1px_3px_rgba(34,31,56,0.1)]" : "text-[#777583]"}`} type="button" onClick={() => { setMode("human-enhance"); if (!transcript.transcript_id) void startHumanWriting(); }}>Write & enhance</button></div>
          {mode === "ai-gen" ? <div className="mt-[0.72rem] grid gap-[0.68rem]"><div><div className="mb-[0.36rem] flex items-center justify-between"><span className="text-[0.66rem] font-extrabold uppercase tracking-[0.055em] text-[#777583]">Duration</span><span className="text-[0.65rem] font-bold text-[#6550e5]">{duration} sec</span></div><div className="grid grid-cols-3 gap-1.5">{([{ value: 45, label: "Short" }, { value: 75, label: "Standard" }, { value: 105, label: "Detailed" }] as const).map((option) => <button className={`rounded-[6px] border px-[0.25rem] py-[0.43rem] text-[0.62rem] font-bold ${duration === option.value ? "border-[#a99dff] bg-[#f6f4ff] text-[#5e4ce0]" : "border-[#e5e4ea] bg-white text-[#777583]"}`} key={option.value} type="button" onClick={() => setDuration(option.value)}>{option.label}</button>)}</div></div><OptionGrid label="Tone" value={tone} options={["auto", "persuasive", "informative", "conversational"]} onChange={setTone} /><OptionGrid label="Style" value={style} options={["natural", "formal"]} onChange={setStyle} /></div> : <><div className={`mt-[0.72rem] rounded-[8px] border px-[0.7rem] py-[0.65rem] ${selection ? "border-[#d9d3ff] bg-[#faf9ff]" : "border-[#e7e6ec] bg-[#fbfbfc]"}`}><div className="flex items-center justify-between gap-2"><span className="text-[0.66rem] font-extrabold uppercase tracking-[0.055em] text-[#777583]">Selection</span>{selection && <button className="p-0 text-[0.66rem] font-bold text-[#6651e8]" type="button" onClick={clearSelection}>Clear</button>}</div>{selection ? <p className="mb-0 mt-[0.35rem] line-clamp-3 text-[0.72rem] leading-[1.45] text-[#4d4a62]">“{selection.text}”</p> : <p className="mb-0 mt-[0.35rem] text-[0.72rem] leading-[1.45] text-[#858390]">Select words in the document to enhance only that portion.</p>}</div><div className="mt-[0.68rem] grid gap-[0.68rem]"><OptionGrid label="Tone" value={tone} options={["auto", "persuasive", "informative", "conversational"]} onChange={setTone} /><OptionGrid label="Style" value={style} options={["natural", "formal"]} onChange={setStyle} /></div></>}
          <div className="mt-3"><label className="grid gap-1.5 text-[0.66rem] font-extrabold uppercase tracking-[0.055em] text-[#777583]">Audience level<select value={audienceLevel} onChange={(event) => setAudienceLevel(event.target.value as AudienceLevel)} className="w-full rounded-md border border-[#e5e4ea] bg-white px-2 py-2 text-[0.72rem] font-semibold normal-case tracking-normal text-[#4d4a62]"><option value="beginner">Beginner</option><option value="general">General audience</option><option value="specialist">Specialist</option></select></label><p className="mb-0 mt-1.5 text-[0.68rem] leading-[1.4] text-[#777583]">{audienceLevel === "beginner" ? "Explain terms and build ideas step by step." : audienceLevel === "specialist" ? "Assume subject knowledge and retain technical detail." : "Give context for listeners without specialist knowledge."}</p></div>
          {mode === "ai-gen" ? <button className="mt-[0.72rem] w-full rounded-[8px] border border-[#d9d3ff] bg-[#faf9ff] px-[0.7rem] py-[0.62rem] text-[0.7rem] font-bold text-[#5e4ce0] disabled:cursor-not-allowed disabled:opacity-45" type="button" onClick={requestAllGeneration} disabled={working || data.bulk_generation_status === "queued" || data.bulk_generation_status === "running"}>{data.bulk_generation_status === "queued" || data.bulk_generation_status === "running" ? `Generating all slides${data.bulk_generation_progress !== null ? ` · ${data.bulk_generation_progress}%` : ""}` : "Generate all slides"}</button> : null}{mode === "human-enhance" && !transcript.transcript_id ? <button className="mt-[0.72rem] w-full rounded-[8px] border border-[#d9d3ff] bg-[#faf9ff] px-[0.7rem] py-[0.62rem] text-[0.7rem] font-bold text-[#5e4ce0] disabled:cursor-not-allowed disabled:opacity-45" type="button" onClick={() => void startHumanWriting()} disabled={working}>Start writing on this slide</button> : null}{dirty ? <button className="mt-[0.72rem] w-full rounded-[8px] border border-[#d9d3ff] bg-[#faf9ff] px-[0.7rem] py-[0.62rem] text-[0.7rem] font-bold text-[#5e4ce0] disabled:cursor-not-allowed disabled:opacity-45" type="button" onClick={() => void saveScriptEdits()} disabled={working}>Save edits</button> : null}<button className="mt-[0.72rem] w-full rounded-[8px] bg-[#19191f] px-[0.7rem] py-[0.7rem] text-[0.73rem] font-bold text-white disabled:cursor-not-allowed disabled:opacity-45" type="button" onClick={requestSlideGeneration} disabled={working || (mode === "human-enhance" && (!selection || !transcript.transcript_id))}>{working ? "Working…" : mode === "human-enhance" ? "Enhance selected text" : "Generate this slide"}</button>{actionNote && <p className="mb-0 mt-[0.48rem] text-[0.68rem] leading-[1.4] text-[#6e6c7b]">{actionNote}</p>}</section>
        <section className="rounded-[10px] border border-[#e6e5eb] bg-white px-[0.9rem] py-[0.85rem]"><div className="flex items-center justify-between gap-3"><h3 className="m-0 text-[0.84rem] tracking-[-0.025em]">{selectedGeneratedTone ? "Selected tone" : "Tone check"}</h3>{visibleTone && <span className="rounded-full border border-[#bfe7ce] bg-[#f3fff7] px-[0.55rem] py-[0.27rem] text-[0.66rem] font-bold text-[#218e56]">✦ {visibleTone}</span>}</div>{selectedGeneratedTone ? <p className="mb-0 mt-[0.5rem] text-[0.72rem] leading-[1.48] text-[#62606d]">Used as the target delivery tone for this generated script.</p> : <>{transcript.tone_check?.classification ? <p className="mb-0 mt-[0.5rem] text-[0.66rem] font-bold text-[#777583]">Automatically detected from the current script</p> : null}<p className="mb-0 mt-[0.45rem] text-[0.72rem] leading-[1.48] text-[#62606d]">{transcript.transcript_id && !transcript.coaching_analysis_available ? "Coaching feedback is temporarily unavailable. Your script is still saved." : transcript.tone_check?.rationale ?? "Generate or write a script to receive a tone assessment."}</p></>}</section>
        <section className="rounded-[10px] border border-[#e6e5eb] bg-white px-[0.9rem] py-[0.85rem]"><div className="flex items-center justify-between"><h3 className="m-0 text-[0.84rem] tracking-[-0.025em]">Complex terms</h3><span className="grid h-[19px] w-[19px] place-items-center rounded-full bg-[#f0edff] text-[0.62rem] font-extrabold text-[#6a55ea]">{transcript.complex_terms.length}</span></div>{transcript.complex_terms.length ? <div className="mt-[0.65rem] grid gap-[0.48rem]">{transcript.complex_terms.map((term) => <div className="rounded-[7px] border border-[#e9e7f2] bg-[#fbfaff] px-[0.65rem] py-[0.55rem]" key={term.term}><strong className="text-[0.68rem] text-[#5c49d5]">{term.term}</strong><p className="mb-0 mt-[0.22rem] text-[0.69rem] leading-[1.42] text-[#6b6977]">{term.definition}</p></div>)}</div> : <p className="mb-0 mt-[0.55rem] text-[0.7rem] leading-[1.4] text-[#858390]">No complex terms were detected on this slide.</p>}</section>
        <section className="rounded-[10px] border border-[#e6e5eb] bg-white px-[0.9rem] py-[0.85rem]"><div className="flex items-center justify-between"><h3 className="m-0 text-[0.84rem] tracking-[-0.025em]">Vocabulary upgrades</h3><span className="grid h-[19px] w-[19px] place-items-center rounded-full bg-[#f0edff] text-[0.62rem] font-extrabold text-[#6a55ea]">{transcript.vocabulary_upgrades.length}</span></div>{transcript.vocabulary_upgrades.length ? <div className="mt-[0.65rem] grid gap-[0.5rem]">{transcript.vocabulary_upgrades.map((upgrade) => <div className="border-l-2 border-[#c9c0ff] pl-[0.58rem]" key={`${upgrade.original}-${upgrade.suggested}`}><p className="m-0 text-[0.69rem] leading-[1.4] text-[#5e5b6b]"><span className="text-[#888591]">“{upgrade.original}”</span> → <strong className="text-[#5142bb]">{upgrade.suggested}</strong></p></div>)}</div> : <p className="mb-0 mt-[0.55rem] text-[0.7rem] leading-[1.4] text-[#858390]">No vocabulary upgrades were suggested.</p>}</section>
      </div></aside>
    </section>
    {rangeDrawerOpen ? <div className="fixed inset-0 z-[70] flex justify-end bg-[#171724]/45 backdrop-blur-[2px]" role="dialog" aria-modal="true" aria-labelledby="slide-range-title"><section className="flex h-full w-full max-w-[25rem] flex-col border-l border-[#e3e1ea] bg-white px-7 py-8 shadow-[-18px_0_60px_rgba(26,22,51,0.22)]"><div className="flex items-start justify-between gap-4"><div><p className="m-0 text-[0.68rem] font-bold uppercase tracking-[0.1em] text-[#6753e9]">Bulk generation</p><h2 className="mb-0 mt-2 text-[1.55rem] tracking-[-0.055em]" id="slide-range-title">Choose a slide range</h2></div><button className="grid h-9 w-9 place-items-center rounded-lg border border-[#e1dfe7] text-lg text-[#686675]" onClick={() => setRangeDrawerOpen(false)} type="button" aria-label="Close slide range drawer">×</button></div><p className="mb-0 mt-4 text-[0.82rem] leading-6 text-[#656270]">Generate scripts only for empty slides within this range. Existing generated or written scripts stay untouched.</p><div className="mt-8 grid grid-cols-2 gap-3"><label className="grid gap-2 text-[0.7rem] font-bold uppercase tracking-[0.055em] text-[#777583]">From slide<select className="h-11 rounded-lg border border-[#dddbe5] bg-white px-3 text-[0.82rem] font-semibold normal-case tracking-normal text-[#302e3d] outline-none focus:border-[#8e7cf4]" value={bulkRange.start} onChange={(event) => { const start = Number(event.target.value); setBulkRange((current) => ({ start, end: Math.max(start, current.end) })); }}>{data.slides.map((slide) => <option key={slide.slide_number} value={slide.slide_number}>Slide {slide.slide_number}</option>)}</select></label><label className="grid gap-2 text-[0.7rem] font-bold uppercase tracking-[0.055em] text-[#777583]">To slide<select className="h-11 rounded-lg border border-[#dddbe5] bg-white px-3 text-[0.82rem] font-semibold normal-case tracking-normal text-[#302e3d] outline-none focus:border-[#8e7cf4]" value={bulkRange.end} onChange={(event) => setBulkRange((current) => ({ ...current, end: Number(event.target.value) }))}>{data.slides.filter((slide) => slide.slide_number >= bulkRange.start).map((slide) => <option key={slide.slide_number} value={slide.slide_number}>Slide {slide.slide_number}</option>)}</select></label></div><div className="mt-5 rounded-xl border border-[#e5e1ff] bg-[#f8f6ff] px-4 py-3"><strong className="text-[0.8rem] text-[#4f3fd0]">{bulkRangeCount} {bulkRangeCount === 1 ? "slide" : "slides"} selected</strong><p className="mb-0 mt-1 text-[0.72rem] leading-5 text-[#6d687e]">Slides {bulkRange.start}–{bulkRange.end} will be checked for empty transcripts.</p></div><div className="mt-auto grid grid-cols-2 gap-2 pt-8"><button className="rounded-lg border border-[#dddbe4] px-3 py-2.5 text-[0.76rem] font-bold text-[#5b5968]" onClick={() => setRangeDrawerOpen(false)} type="button">Cancel</button><button className="rounded-lg bg-[#1b1a22] px-3 py-2.5 text-[0.76rem] font-bold text-white" onClick={() => { setRangeDrawerOpen(false); setPendingAction({ type: "generate-all" }); }} type="button">Continue</button></div></section></div> : null}
    {pendingAction ? <div className="fixed inset-0 z-[60] grid place-items-center bg-[#171724]/45 p-6 backdrop-blur-[2px]" role="dialog" aria-modal="true" aria-labelledby="pending-action-title"><section className="w-full max-w-[27rem] rounded-2xl border border-[#e3e1ea] bg-white p-7 shadow-[0_24px_70px_rgba(26,22,51,0.3)]"><div className="grid h-11 w-11 place-items-center rounded-xl bg-[#fff3df] text-[1.1rem] font-extrabold text-[#b66b12]" aria-hidden="true">!</div><p className="mb-0 mt-5 text-[0.68rem] font-bold uppercase tracking-[0.1em] text-[#9c651e]">Confirmation needed</p><h2 className="mb-0 mt-2 text-[1.42rem] tracking-[-0.05em]" id="pending-action-title">{pendingActionTitle}</h2><p className="mb-0 mt-3 text-[0.84rem] leading-6 text-[#656270]">{pendingActionMessage}</p><div className="mt-6 flex justify-end gap-2"><button className="rounded-lg border border-[#dddbe4] px-3 py-2 text-[0.75rem] font-bold text-[#5b5968]" onClick={() => setPendingAction(null)} type="button">Keep editing</button><button className="rounded-lg bg-[#1b1a22] px-3 py-2 text-[0.75rem] font-bold text-white" onClick={confirmPendingAction} type="button">{pendingActionConfirm}</button></div></section></div> : null}
    {bulkModalVisible ? <div className="fixed inset-0 z-50 grid place-items-center bg-[#171724]/45 p-6 backdrop-blur-[2px]" role="dialog" aria-modal="true" aria-labelledby="bulk-generation-title"><section className="w-full max-w-[28rem] rounded-2xl border border-[#e3dfff] bg-white p-7 shadow-[0_24px_70px_rgba(26,22,51,0.3)]">{bulkFailed ? <><div className="grid h-11 w-11 place-items-center rounded-xl bg-[#fff1f3] text-xl font-extrabold text-[#c43d55]" aria-hidden="true">!</div><p className="mb-0 mt-5 text-[0.68rem] font-bold uppercase tracking-[0.1em] text-[#b33c50]">Generation stopped</p><h2 className="mb-0 mt-2 text-[1.45rem] tracking-[-0.05em]" id="bulk-generation-title">Scripts could not be completed</h2><p className="mb-0 mt-3 text-[0.84rem] leading-6 text-[#656270]">Completed scripts are preserved. Retry will continue with only the slides that are still empty.</p><div className="mt-6 flex justify-end gap-2"><button className="rounded-lg border border-[#dddbe4] px-3 py-2 text-[0.75rem] font-bold text-[#5b5968]" onClick={() => setBulkGenerationState(null)} type="button">Dismiss</button><button className="rounded-lg bg-[#1b1a22] px-3 py-2 text-[0.75rem] font-bold text-white" onClick={() => void generateAllSlides()} type="button">Retry generation</button></div></> : <><div className="grid h-11 w-11 place-items-center rounded-xl bg-[#f0edff] text-[1.15rem] text-[#6550e5]" aria-hidden="true"><span className="animate-pulse">✦</span></div><p className="mb-0 mt-5 text-[0.68rem] font-bold uppercase tracking-[0.1em] text-[#6753e9]">Transcript generation</p><h2 className="mb-0 mt-2 text-[1.45rem] tracking-[-0.05em]" id="bulk-generation-title">{bulkGenerationState === "starting" ? "Starting generation…" : "Writing your presenter scripts"}</h2><p className="mb-0 mt-3 text-[0.84rem] leading-6 text-[#656270]">{bulkGenerationState === "starting" ? `Setting up generation for slides ${bulkRange.start}–${bulkRange.end}. Keep this window open while it starts.` : `Filling empty transcripts from slide ${bulkRange.start} through ${bulkRange.end}. Existing scripts are being left unchanged.`}</p><div className="mt-6"><div className="flex items-center justify-between text-[0.72rem] font-bold text-[#555261]"><span>{bulkGenerationState === "starting" ? "Queueing job" : `${completedSlideCount} of ${bulkRangeCount} slides checked`}</span><span className="tabular-nums text-[#6550e5]">{bulkGenerationState === "starting" ? "…" : `${bulkProgress}%`}</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-[#ebe9f2]"><div className="h-full rounded-full bg-gradient-to-r from-[#705cf0] to-[#a28cff] transition-[width] duration-500 ease-out" style={{ width: bulkGenerationState === "starting" ? "8%" : `${bulkProgress}%` }} /></div></div><p className="mb-0 mt-5 text-center text-[0.69rem] text-[#918e9e]">Each empty slide is retried up to three times before the job stops.</p></>}</section></div> : null}
  </main>;
}
