"use client";
import Link from "next/link";
import { ExportDownload } from "@/components/export-download";
import { DeckUpload } from "@/components/deck-upload";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/auth/auth-provider";
import { AgendaLaunch } from "@/components/agenda-builder";
import { SlideAnalysisProgress, SlideAnalysisState } from "@/components/slide-analysis-progress";
import { Brand } from "@/components/brand";
import { processingMessage } from "@/lib/processing-message";
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
type Slide = {
    number: number;
    title: string;
    label: string;
    imageUrl: string | null;
    generatedByAgenda?: boolean;
};
type SlideAnalysis = {
    num: number;
    slide_score: number;
    overload: boolean;
    overload_reason: string | null;
    visual_hierarchy_issues: string | null;
    improvement_suggestions: string[];
    table_tips: string[];
    refs_found: string[];
};
type SlideAnalyzerResponse = {
    overall_score: number;
    score_rationale: string;
    deck_top_priorities: string[];
    examiner_red_flags: string[];
    agenda_status: "found" | "missing";
    cohesion_feedback: string;
    per_slide: SlideAnalysis[];
    complex_terms: Array<{
        term: string;
        definition: string;
    }>;
};
type PresentationResponse = {
    id: string;
    original_filename: string;
    status: "queued" | "processing" | "completed" | "failed";
    slide_count: number | null;
    processing_error_code: string | null;
    job_status: string | null;
    job_progress_percent: number | null;
    analysis: SlideAnalyzerResponse | null;
    slides: Array<{
        number: number;
        title: string | null;
        layout_name: string | null;
        image_url: string | null;
        generated_by_agenda?: boolean;
    }>;
};
type InspectorTab = "Feedback" | "Table tips" | "References";
function scoreAccent(score: number): "green" | "orange" | "red" {
    if (score < 6.5)
        return "red";
    if (score < 7)
        return "orange";
    return "green";
}
function parseSuggestion(suggestion: string) {
    const match = suggestion.match(/^\[(HIGH|MEDIUM|LOW)\]\s*(.*)$/);
    return { priority: match?.[1] ?? "LOW", text: match?.[2] ?? suggestion };
}
function MiniSlide({ slide, accessToken }: {
    slide: Slide;
    accessToken: string | null;
}) {
    const source = useProtectedSlideImage(slide.imageUrl, accessToken);
    return (<div className="grid aspect-video w-full place-items-center overflow-hidden rounded border border-[#e5e4eb] bg-white shadow-[0_1px_2px_rgba(27,27,47,0.03)]">
      {source ? <img alt={`${slide.title} thumbnail`} className="h-full w-full object-cover" src={source}/> : <span className="px-2 text-center text-[0.42rem] font-bold text-[#858394]">{slide.label}</span>}
    </div>);
}
function useProtectedSlideImage(imageUrl: string | null, accessToken: string | null) {
    const [source, setSource] = useState<string | null>(null);
    useEffect(() => {
        if (!imageUrl || !accessToken) {
            setSource(null);
            return;
        }
        let active = true;
        let objectUrl: string | null = null;
        async function loadImage() {
            try {
                const response = await fetch(`${apiBaseUrl}${imageUrl}`, {
                    headers: { Authorization: `Bearer ${accessToken}` },
                });
                if (!response.ok)
                    throw new Error("The rendered slide could not be loaded.");
                objectUrl = URL.createObjectURL(await response.blob());
                if (active)
                    setSource(objectUrl);
            }
            catch {
                if (active)
                    setSource(null);
            }
        }
        void loadImage();
        return () => {
            active = false;
            if (objectUrl)
                URL.revokeObjectURL(objectUrl);
        };
    }, [accessToken, imageUrl]);
    return source;
}
function RenderedSlidePreview({ imageUrl, accessToken, title }: {
    imageUrl: string | null;
    accessToken: string | null;
    title: string;
}) {
    const source = useProtectedSlideImage(imageUrl, accessToken);
    if (!source)
        return <div className="grid h-full w-full place-items-center text-center text-[0.75rem] font-semibold text-[#878493]">Rendered slide preview unavailable.</div>;
    return <img alt={`${title} slide preview`} className="h-full w-full object-contain" src={source}/>;
}
function ReferenceCoverageWarning({ analysis }: {
    analysis: SlideAnalyzerResponse;
}) {
    const hasReferences = analysis.per_slide.some((slide) => slide.refs_found.length > 0);
    if (hasReferences)
        return null;
    return (<section className="rounded-[10px] border border-[#f2d2ad] bg-[#fffaf2] px-4 py-[0.95rem]" role="alert">
      <div className="text-[0.72rem] font-extrabold text-[#a86410]">No readable references detected</div>
      <p className="mt-[0.52rem] text-[0.77rem] leading-[1.5] text-[#6f604d]">No citations or links could be verified from the extracted slide text.</p>
    </section>);
}

function VisualHierarchyFeedback({ value }: { value: string | null }) {
    const feedback = value ?? "No specific visual-design issue was reported. This does not confirm that every design detail is correct.";
    const match = feedback.match(/^(.*?)(?:\s+Fix:\s*)(.+)$/is);
    const issue = match?.[1] ?? feedback;
    const fix = match?.[2] ?? null;

    return (<>
      <p className="mt-[0.35rem] text-[0.78rem] leading-[1.55] text-[#5d5c6b]">{issue}</p>
      {fix ? <p className="mt-3 text-[0.78rem] leading-[1.55] text-[#5d5c6b]"><span className="font-extrabold text-[#4e4d5d]">Fix: </span>{fix}</p> : null}
    </>);
}


function GeneratedAgendaInspector() {
    return <><div className="bg-white px-[1.7rem] pb-5 pt-6"><p className="mb-[0.28rem] text-[0.73rem] font-bold uppercase tracking-[0.06em] text-[#81818f]">Generated slide</p><h2 className="m-0 text-[1.25rem] tracking-[-0.045em]">Agenda</h2></div><div className="grid min-h-0 flex-1 content-start gap-[1.1rem] overflow-y-auto bg-[#f7f7f9] px-[1.35rem] py-[1.25rem]"><section className="rounded-[10px] border border-[#d9d3ff] bg-[#faf9ff] px-4 py-[0.95rem]"><p className="m-0 text-[0.72rem] font-extrabold text-[#5e4ee5]">Agenda added to this deck</p><p className="mt-[0.52rem] text-[0.77rem] leading-[1.5] text-[#5d5c6b]">This navigation slide was generated from the deck outline and placed into the presentation.</p></section><section className="rounded-[10px] border border-[#e6e5eb] bg-white px-4 py-[0.95rem]"><p className="m-0 text-[0.64rem] font-extrabold uppercase tracking-[0.075em] text-[#83818e]">Analysis</p><p className="mt-[0.52rem] text-[0.77rem] leading-[1.5] text-[#5d5c6b]">Generated agendas are excluded from scoring and slide feedback.</p></section></div></>;
}
export default function SlideAnalyzerPage() {
    const searchParams = useSearchParams();
    const { getAccessToken } = useAuth();
    const [presentation, setPresentation] = useState<PresentationResponse | null>(null);
    const [accessToken, setAccessToken] = useState<string | null>(null);
    const [loadingError, setLoadingError] = useState<string | null>(null);
    const [startingAnalysis, setStartingAnalysis] = useState(false);
    const [selectedIndex, setSelectedIndex] = useState(1);
    const [activeTab, setActiveTab] = useState<InspectorTab>("Feedback");
    const [showDeckSummary, setShowDeckSummary] = useState(false);
    const [zoom, setZoom] = useState(100);
    const requestedPresentationId = searchParams.get("presentation");
    const loadPresentation = useCallback(async () => {
        try {
            const token = await getAccessToken();
            setAccessToken(token);
            const presentationId = requestedPresentationId;
            if (!presentationId) return;
            const response = await fetch(`${apiBaseUrl}/api/v1/presentations/${presentationId}`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            const payload: unknown = await response.json().catch(() => null);
            if (!response.ok || typeof payload !== "object" || payload === null) {
                const detail = typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string"
                    ? payload.detail
                    : "The presentation could not be loaded.";
                throw new Error(detail);
            }
            setPresentation(payload as PresentationResponse);
            setLoadingError(null);
        }
        catch (error) {
            setLoadingError(error instanceof Error ? error.message : "The presentation could not be loaded.");
        }
    }, [getAccessToken, requestedPresentationId]);
    useEffect(() => { void loadPresentation(); }, [loadPresentation]);
    useEffect(() => {
        const handleAgendaCreated = (event: Event) => {
            const detail = event as CustomEvent<number>;
            setSelectedIndex(Math.max(0, detail.detail - 1));
            void loadPresentation();
        };
        window.addEventListener("rehearse:agenda-created", handleAgendaCreated);
        return () => window.removeEventListener("rehearse:agenda-created", handleAgendaCreated);
    }, [loadPresentation]);
    useEffect(() => {
        if (!presentation || presentation.status === "completed" || presentation.status === "failed")
            return;
        const timer = window.setInterval(() => { void loadPresentation(); }, 3000);
        return () => window.clearInterval(timer);
    }, [loadPresentation, presentation]);
    useEffect(() => {
        if (presentation?.slides.length && selectedIndex >= presentation.slides.length) {
            setSelectedIndex(0);
        }
    }, [presentation?.slides.length, selectedIndex]);
    const startAnalysis = async () => {
        if (!presentation)
            return;
        setStartingAnalysis(true);
        try {
            const token = accessToken ?? await getAccessToken();
            const response = await fetch(`${apiBaseUrl}/api/v1/presentations/${presentation.id}/analyze`, {
                method: "POST",
                headers: { Authorization: `Bearer ${token}` },
            });
            const payload: unknown = await response.json().catch(() => null);
            if (!response.ok) {
                const detail = typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string"
                    ? payload.detail
                    : "Slide analysis could not be started.";
                throw new Error(detail);
            }
            await loadPresentation();
        }
        catch (error) {
            setLoadingError(error instanceof Error ? error.message : "Slide analysis could not be started.");
        }
        finally {
            setStartingAnalysis(false);
        }
    };
    const slides = useMemo<Slide[]>(() => presentation?.slides.map((item) => ({
        number: item.number,
        title: item.title || `Slide ${item.number}`,
        label: item.layout_name || `Slide ${item.number}`,
        imageUrl: item.image_url,
        generatedByAgenda: item.generated_by_agenda,
    })) ?? [], [presentation]);
    const analysis = presentation?.analysis ?? null;
    const slide = slides[selectedIndex] ?? slides[0] ?? null;
    const selectedAnalysis = useMemo<SlideAnalysis>(() => {
        const matched = analysis?.per_slide.find((item) => item.num === slide?.number);
        if (matched) return matched;
        // This is a display-only state so the new slide never inherits feedback
        // from the first real slide. Its score is the deck score solely to keep
        // the existing inspector shell stable; the body explicitly states that
        // generated agenda content is not independently evaluated.
        return {
            num: slide?.number ?? 0,
            slide_score: analysis?.overall_score ?? 0,
            overload: false,
            overload_reason: "This agenda was generated from the deck outline and is not independently scored as an original slide.",
            visual_hierarchy_issues: "The agenda is a generated navigation slide. Review its wording and position in the deck before presenting.",
            improvement_suggestions: [],
            table_tips: [],
            refs_found: [],
        };
    }, [analysis, slide]);
    if (!requestedPresentationId) return <DeckUpload mode="slide" />;
    if (loadingError)
        return <SlideAnalysisState title="We couldn’t open this deck" description={loadingError} action={<Link className="inline-flex rounded-xl bg-[#242331] px-4 py-3 text-sm font-semibold text-white no-underline" href="/home">Back to home</Link>}/>;
    if (!presentation || presentation.status !== "completed" || !slide)
        return <SlideAnalysisProgress progress={presentation?.job_progress_percent ?? 0} filename={presentation?.original_filename} failed={presentation?.status === "failed"} error={presentation?.processing_error_code}/>;
    if (!analysis)
        return <SlideAnalysisState title="Your deck is ready" description={processingMessage(presentation.processing_error_code, "Review your slides for clarity, structure, visual hierarchy, and practical improvements.")} filename={presentation.original_filename} action={<><button className="rounded-xl bg-[#242331] px-4 py-3 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-65" disabled={startingAnalysis} onClick={() => void startAnalysis()} type="button">{startingAnalysis ? "Starting analysis…" : "Analyze this deck"}</button><Link className="rounded-xl px-4 py-3 text-sm font-semibold text-[#6a6275] no-underline hover:bg-[#f7f5fa]" href="/home">Back to home</Link></>}/>;
    const moveSlide = (direction: -1 | 1) => setSelectedIndex((current) => Math.min(slides.length - 1, Math.max(0, current + direction)));
    const inspectorScore = showDeckSummary ? analysis.overall_score : selectedAnalysis?.slide_score ?? analysis.overall_score;
    const inspectorScoreColor = scoreAccent(inspectorScore) === "green" ? "#1ba362" : scoreAccent(inspectorScore) === "orange" ? "#d57b15" : "#d64d59";
  return <main className="h-dvh min-w-[860px] overflow-hidden bg-[#f7f7f9] font-sans text-[#171724]">
    <style>{`strong.text-\\[\\#1ba362\\] { color: ${inspectorScoreColor} !important; }`}</style>
    <header className="relative grid min-h-[74px] grid-cols-[238px_minmax(0,1fr)_auto] items-center border-b border-[#e7e7ec] bg-white/95 max-[1220px]:grid-cols-[205px_minmax(0,1fr)_auto] max-[920px]:grid-cols-[170px_minmax(0,1fr)_auto]">
      <Link className="inline-flex h-full items-center justify-center no-underline hover:bg-[#faf9ff]" href="/home" aria-label="Rehearse AI home"><Brand /></Link>
      <span aria-hidden className="absolute bottom-[22px] left-[238px] top-[22px] w-px rounded-full bg-gradient-to-b from-transparent via-[#8777ff] to-transparent shadow-[0_0_9px_rgba(124,105,255,0.17)] max-[1220px]:left-[205px] max-[920px]:left-[170px]"/>
      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)] items-center gap-5 overflow-hidden px-5 max-[920px]:px-[0.9rem]"><h1 className="m-0 whitespace-nowrap text-[1.32rem] font-extrabold tracking-[-0.055em] text-[#20202c] max-[920px]:text-[1.16rem]">Slide Analyzer</h1><div className="flex min-w-0 items-center justify-end gap-[0.7rem] overflow-hidden whitespace-nowrap text-[0.8rem] text-[#737382]"><strong className="min-w-0 truncate" title={presentation.original_filename}>{presentation.original_filename}</strong><span className="shrink-0 before:mr-[0.7rem] before:text-[#bbbcc5] before:content-['•']">{slides.length} slides</span><span className="shrink-0 before:mr-[0.7rem] before:text-[#bbbcc5] before:content-['•'] max-[1220px]:hidden">Analysis saved</span></div></div>
      <div className="flex justify-self-end gap-2 pr-[1.1rem] max-[920px]:pr-3"><button className={`inline-flex min-h-[37px] items-center rounded-[10px] border px-[0.8rem] text-[0.78rem] font-bold ${showDeckSummary ? "border-[#a99dff] bg-[#f6f4ff] text-[#604bde]" : "border-[#e0e0e6] bg-white text-[#292936]"}`} type="button" onClick={() => setShowDeckSummary(true)}>▤&nbsp; Deck summary</button><Link className="inline-flex min-h-[37px] items-center rounded-[10px] border border-[#e0e0e6] bg-white px-[0.8rem] text-[0.78rem] font-bold text-[#292936] no-underline max-[620px]:hidden" href={`/transcript?presentation=${presentation.id}`}>✦&nbsp; Transcript</Link><ExportDownload path={`/api/v1/presentations/${presentation.id}/export`} filename="presentation-export.zip" title="Download current PPTX and Excel feedback" /></div>
    </header>
    <section className="grid h-[calc(100dvh-74px)] min-h-0 grid-cols-[238px_minmax(540px,1fr)_412px] overflow-hidden max-[1220px]:grid-cols-[205px_minmax(440px,1fr)_350px] max-[920px]:grid-cols-[170px_minmax(390px,1fr)_310px] max-[620px]:grid-cols-[150px_minmax(390px,1fr)_300px]">
      <aside className="flex min-h-0 min-w-0 flex-col overflow-hidden border-r border-[#e7e7ec] bg-white"><div className="flex items-center border-b border-[#eeeef2] px-[1.15rem] py-[0.95rem]"><h2 className="m-0 text-[0.8rem] font-bold uppercase text-[#565563]">Slides <span className="text-[0.72rem] font-semibold normal-case text-[#9897a3]">· {slides.length} total</span></h2></div><div className="min-h-0 flex-1 overflow-y-auto px-[0.6rem] py-[0.65rem]">{slides.map((item, index) => { const itemAnalysis = analysis.per_slide.find((entry) => entry.num === item.number); const score = itemAnalysis?.slide_score ?? 0; return <button className={`grid w-full grid-cols-[23px_1fr_30px] items-center gap-[0.45rem] rounded-[10px] border px-[0.4rem] py-[0.48rem] text-left hover:bg-[#f8f7ff] ${selectedIndex === index ? "border-[#a699ff] bg-[#f7f5ff] shadow-[0_0_0_1px_rgba(121,99,255,0.08)]" : "border-transparent bg-transparent"}`} key={`${item.number}-${item.title}`} onClick={() => { setSelectedIndex(index); setShowDeckSummary(false); }} type="button"><span className={`text-[0.7rem] font-bold tabular-nums ${selectedIndex === index ? "text-[#6757ed]" : "text-[#878793]"}`}>{String(item.number).padStart(2, "0")}</span><MiniSlide accessToken={accessToken} slide={item}/><span className={`text-right text-[0.73rem] font-bold tabular-nums ${scoreAccent(score) === "green" ? "text-[#1b9c5b]" : scoreAccent(score) === "orange" ? "text-[#d57b15]" : "text-[#d64d59]"}`}>{itemAnalysis ? score.toFixed(1) : "—"}</span></button>; })}</div><div className="flex items-center gap-[0.4rem] border-t border-[#eeeef2] px-[1.15rem] py-[0.9rem] text-[0.71rem] text-[#777786]"><span className="h-[6px] w-[6px] rounded-full bg-[#29b770] shadow-[0_0_0_3px_#e8f9ef]"/> All slide feedback is saved</div></aside>
      <section className="grid min-h-0 min-w-0 grid-rows-[auto_minmax(0,1fr)_auto] bg-[#fafafb] px-[clamp(1.5rem,3vw,2.75rem)] pb-[1.1rem] pt-6 max-[620px]:p-4">
        <div className="mb-[1.2rem] flex items-center justify-between">
          <div>
            <p className="mb-[0.28rem] text-[0.73rem] font-bold uppercase tracking-[0.06em] text-[#81818f]">Slide {String(slide.number).padStart(2, "0")} of {slides.length}</p>
            <h1 className="m-0 text-[1.55rem] leading-[1.1] tracking-[-0.055em] max-[620px]:text-[1.25rem]">{slide.title}</h1>
          </div>
          <div className="flex items-center overflow-hidden rounded-[9px] border border-[#dedee5] bg-white">
            <button className="h-[34px] w-[34px] text-[1.15rem] text-[#3b3b48] hover:bg-[#f2f0ff]" type="button" onClick={() => setZoom((value) => Math.max(75, value - 25))}>−</button>
            <output className="grid h-[34px] w-[54px] place-items-center border-x border-[#e6e6eb] text-[0.74rem] font-bold">{zoom}%</output>
            <button className="h-[34px] w-[34px] text-[1.15rem] text-[#3b3b48] hover:bg-[#f2f0ff]" type="button" onClick={() => setZoom((value) => Math.min(150, value + 25))}>+</button>
          </div>
        </div>
        <div className="grid min-h-0 place-items-center overflow-hidden rounded-[13px] border border-[#e3e3e8] bg-[#f1f1f4] [background-image:repeating-linear-gradient(0deg,transparent_0_29px,rgba(111,109,150,0.025)_30px)]">
          <div className="relative aspect-video w-[min(90%,720px)] origin-center overflow-hidden rounded bg-white shadow-[0_20px_44px_rgba(29,27,52,0.16)] transition-transform duration-200 max-[1220px]:w-[94%] max-[620px]:w-[96%]" style={{ transform: `scale(${zoom / 100})` }}>
            <RenderedSlidePreview accessToken={accessToken} imageUrl={slide.imageUrl} title={slide.title}/>
          </div>
        </div>
        <nav className="flex items-center justify-between pt-4 text-[0.76rem] tabular-nums text-[#81818d]">
          <button className="min-w-[95px] rounded-lg bg-white px-[0.65rem] py-[0.55rem] text-[0.77rem] font-bold text-[#4b4a5b] disabled:opacity-35" type="button" onClick={() => moveSlide(-1)} disabled={selectedIndex === 0}>← Previous</button>
          <span><strong className="text-[#363642]">{String(slide.number).padStart(2, "0")}</strong> / {slides.length}</span>
          <button className="min-w-[95px] rounded-lg bg-white px-[0.65rem] py-[0.55rem] text-[0.77rem] font-bold text-[#4b4a5b] disabled:opacity-35" type="button" onClick={() => moveSlide(1)} disabled={selectedIndex === slides.length - 1}>Next →</button>
        </nav>
      </section>
      {slide.generatedByAgenda ? <aside className="flex min-h-0 min-w-0 flex-col overflow-hidden border-l border-[#e7e7ec] bg-[#f7f7f9]"><GeneratedAgendaInspector/></aside> : null}
      <div className={slide.generatedByAgenda ? "hidden" : "contents"}>
      <aside className="flex min-h-0 min-w-0 flex-col overflow-hidden border-l border-[#e7e7ec] bg-[#f7f7f9]">{showDeckSummary ? <><div className="flex items-start justify-between bg-white px-[1.4rem] pb-5 pt-6"><div><p className="mb-[0.28rem] text-[0.73rem] font-bold uppercase tracking-[0.06em] text-[#81818f]">Deck analysis</p><h2 className="m-0 text-[1.08rem] tracking-[-0.045em]">Presentation summary</h2></div><div className="grid grid-cols-2 items-baseline gap-x-[0.22rem] text-right"><strong className="text-[1.8rem] tracking-[-0.07em] text-[#1ba362]">{analysis.overall_score.toFixed(1)}</strong><span className="text-[0.8rem] font-bold text-[#777786]">/ 10</span></div></div><div className="grid min-h-0 flex-1 content-start gap-4 overflow-y-auto bg-[#f7f7f9] px-[1.35rem] pb-6 pt-[1.15rem]"><button className="justify-self-start p-0 text-[0.75rem] font-bold text-[#6753ea]" type="button" onClick={() => setShowDeckSummary(false)}>← Return to Slide {String(selectedIndex + 1).padStart(2, "0")}</button><section className="rounded-[10px] border border-[#d9d3ff] bg-[#faf9ff] px-4 py-[0.95rem]"><p className="m-0 text-[0.64rem] font-extrabold uppercase tracking-[0.075em] text-[#83818e]">Score rationale</p><p className="mt-[0.35rem] text-[0.78rem] leading-[1.55] text-[#5d5c6b]">{analysis.score_rationale}</p></section><ReferenceCoverageWarning analysis={analysis}/><section className="py-[0.15rem]"><div className="flex items-center justify-between"><h3 className="m-0 text-[0.88rem] tracking-[-0.025em]">Top priorities</h3><span className="grid h-[21px] w-[21px] place-items-center rounded-full bg-[#f0edff] text-[0.68rem] font-extrabold text-[#715cef]">{analysis.deck_top_priorities.length}</span></div><ol className="mt-[0.7rem] grid list-none gap-[0.7rem] p-0">{analysis.deck_top_priorities.map((item, index) => { const suggestion = parseSuggestion(item); const tag = suggestion.priority === "HIGH" ? "bg-[#ffebee] text-[#bc3b4b]" : suggestion.priority === "MEDIUM" ? "bg-[#fff2dc] text-[#b06a12]" : "bg-[#eaf0ff] text-[#4d66c6]"; return <li className="relative grid grid-cols-[24px_1fr] items-start gap-[0.72rem] py-[0.72rem]" key={item}><span className="relative z-10 grid h-[22px] w-[22px] place-items-center self-start rounded-[7px] border border-[#d9d3ff] bg-[#f7f5ff] text-[0.62rem] font-extrabold tabular-nums text-[#6853e7]">{String(index + 1).padStart(2, "0")}</span>{index < analysis.deck_top_priorities.length - 1 && <span className="absolute left-[11px] top-[34px] h-[calc(100%+0.7rem)] w-px bg-[#ded9ff]"/>}<div className="min-w-0"><span className={`inline-flex h-[22px] items-center rounded px-[0.36rem] py-[0.17rem] text-[0.59rem] font-extrabold tracking-[0.03em] ${tag}`}>{suggestion.priority}</span><p className="mt-[0.38rem] text-[0.78rem] leading-[1.5] text-[#4e4d5d]">{suggestion.text}</p></div></li>; })}</ol>{analysis.deck_top_priorities.length === 0 ? <p className="mt-3 text-[0.77rem] leading-5 text-[#7a7987]">No priority changes were identified from the available slide evidence.</p> : null}</section><section className="flex items-center justify-between gap-[0.8rem] rounded-[10px] border border-[#e6e5eb] bg-white px-4 py-[0.95rem]"><p className="m-0 text-[0.64rem] font-extrabold uppercase tracking-[0.075em] text-[#83818e]">Agenda status</p><strong className={`text-[0.75rem] ${analysis.agenda_status === "found" ? "text-[#168c4f]" : "text-[#a86410]"}`}>● {analysis.agenda_status === "found" ? "Agenda detected" : "No agenda detected"}</strong></section><section className="rounded-[10px] border border-[#e6e5eb] bg-white px-4 py-[0.95rem]"><p className="m-0 text-[0.64rem] font-extrabold uppercase tracking-[0.075em] text-[#83818e]">Cohesion feedback</p><p className="mt-[0.35rem] text-[0.78rem] leading-[1.55] text-[#5d5c6b]">{analysis.cohesion_feedback}</p></section><section className="py-[0.15rem]"><div className="flex items-center justify-between"><h3 className="m-0 text-[0.88rem] tracking-[-0.025em]">Complex terms</h3><span className="grid h-[21px] w-[21px] place-items-center rounded-full bg-[#f0edff] text-[0.68rem] font-extrabold text-[#715cef]">{analysis.complex_terms.length}</span></div><div className="mt-[0.72rem] grid gap-[0.55rem]">{analysis.complex_terms.map((term) => <article className="rounded-lg bg-[#f8f7fb] px-[0.8rem] py-[0.72rem]" key={term.term}><strong className="text-[0.76rem] text-[#373548]">{term.term}</strong><p className="mt-[0.28rem] text-[0.72rem] leading-[1.45] text-[#6d6b7b]">{term.definition}</p></article>)}</div></section></div></> : <><div className="flex items-start justify-between bg-white px-[1.7rem] pb-5 pt-6"><div><p className="mb-[0.28rem] text-[0.73rem] font-bold uppercase tracking-[0.06em] text-[#81818f]">Slide analysis</p><h2 className="m-0 text-[1.08rem] tracking-[-0.045em]">Slide feedback</h2></div><div className="grid grid-cols-2 items-baseline gap-x-[0.22rem] text-right"><strong className="text-[1.8rem] tracking-[-0.07em] text-[#1ba362]">{selectedAnalysis.slide_score.toFixed(1)}</strong><span className="text-[0.8rem] font-bold text-[#777786]">/ 10</span></div></div><div className="grid grid-cols-3 border-b border-[#ececf0] bg-white px-[1.1rem]">{(["Feedback", "Table tips", "References"] as InspectorTab[]).map((tab) => <button key={tab} className={`border-b-2 px-[0.15rem] py-[0.76rem] text-[0.76rem] font-bold ${activeTab === tab ? "border-[#725dff] text-[#624df0]" : "border-transparent text-[#777686]"}`} onClick={() => setActiveTab(tab)} type="button">{tab}</button>)}</div>{activeTab === "Feedback" && <div className="grid min-h-0 flex-1 content-start gap-[1.1rem] overflow-y-auto bg-[#f7f7f9] px-[1.35rem] py-[1.25rem]">{analysis.agenda_status === "missing" ? <AgendaLaunch accessToken={accessToken} presentationId={presentation.id}/> : null}<section className={`rounded-[10px] border px-4 py-[0.95rem] ${selectedAnalysis.overload ? "border-[#f2d2ad] bg-[#fffaf2]" : "border-[#ccebd8] bg-[#f5fff8]"}`}><div className={`flex items-center gap-[0.4rem] text-[0.72rem] font-extrabold ${selectedAnalysis.overload ? "text-[#a86410]" : "text-[#178f51]"}`}>{selectedAnalysis.overload ? "Overload detected" : "No overload detected"}</div><p className="mt-[0.52rem] text-[0.77rem] leading-[1.5] text-[#5d6660]">{selectedAnalysis.overload_reason ?? "The content is divided into clear, manageable sections for the audience."}</p></section><ReferenceCoverageWarning analysis={analysis}/><section className="rounded-[10px] border border-[#e6e5eb] bg-white px-4 py-[0.95rem]"><p className="m-0 text-[0.64rem] font-extrabold uppercase tracking-[0.075em] text-[#83818e]">Visual hierarchy</p><VisualHierarchyFeedback value={selectedAnalysis.visual_hierarchy_issues}/></section><section><h3 className="m-0 text-[0.88rem] tracking-[-0.025em]">Improvement suggestions</h3>{selectedAnalysis.improvement_suggestions.length ? <ol className="mt-[0.7rem] grid list-none gap-[0.7rem] p-0">{selectedAnalysis.improvement_suggestions.map((item, index) => { const suggestion = parseSuggestion(item); const tag = suggestion.priority === "HIGH" ? "bg-[#ffebee] text-[#bc3b4b]" : suggestion.priority === "MEDIUM" ? "bg-[#fff2dc] text-[#b06a12]" : "bg-[#eaf0ff] text-[#4d66c6]"; return <li className="relative grid grid-cols-[24px_1fr] items-start gap-[0.72rem] py-[0.72rem]" key={item}><span className="relative z-10 grid h-[22px] w-[22px] place-items-center self-start rounded-[7px] border border-[#d9d3ff] bg-[#f7f5ff] text-[0.62rem] font-extrabold tabular-nums text-[#6853e7]">{String(index + 1).padStart(2, "0")}</span>{index < selectedAnalysis.improvement_suggestions.length - 1 && <span className="absolute left-[11px] top-[34px] h-[calc(100%+0.7rem)] w-px bg-[#ded9ff]"/>}<div className="min-w-0"><span className={`inline-flex h-[22px] items-center rounded px-[0.36rem] py-[0.17rem] text-[0.59rem] font-extrabold tracking-[0.03em] ${tag}`}>{suggestion.priority}</span><p className="mt-[0.38rem] text-[0.78rem] leading-[1.5] text-[#4e4d5d]">{suggestion.text}</p></div></li>; })}</ol> : <p className="mt-[0.8rem] text-[0.77rem] leading-[1.45] text-[#7a7987]">No further changes are recommended for this slide.</p>}</section></div>}{activeTab === "Table tips" && <section className="grid min-h-0 flex-1 content-start overflow-y-auto bg-[#f7f7f9] px-[1.35rem] py-6"><div className="flex items-center gap-[0.65rem]"><span className="grid h-8 w-8 flex-none place-items-center rounded-[9px] bg-[#efedff] text-[0.95rem] font-extrabold text-[#6c58ec]">▦</span><h3 className="m-0 text-[0.88rem] tracking-[-0.025em] text-[#39364d]">Suggested table structure</h3></div>{selectedAnalysis.table_tips.length ? <div className="mt-5 grid gap-3">{selectedAnalysis.table_tips.map((tip) => <article className="rounded-[11px] border border-[#dfdcf7] border-l-[3px] border-l-[#8b78ff] bg-white px-[1.1rem] py-[1rem] shadow-[0_4px_12px_rgba(55,49,103,0.035)]" key={tip}><p className="m-0 text-[0.78rem] leading-[1.5] tracking-[-0.01em] text-[#3f3c51]">{tip}</p></article>)}</div> : <div className="mt-5 rounded-[10px] border border-dashed border-[#dad9e1] bg-white p-[0.95rem]"><strong className="text-[0.78rem] text-[#4e4d5b]">No table recommended</strong><p className="mt-[0.35rem] text-[0.72rem] leading-[1.45] text-[#82808e]">This content is clearer in its current format.</p></div>}</section>}{activeTab === "References" && <section className="grid min-h-0 flex-1 content-start overflow-y-auto bg-[#f7f7f9] px-[1.35rem] py-6"><div className="flex items-center gap-[0.65rem]"><span className="grid h-8 w-8 flex-none place-items-center rounded-[9px] bg-[#eaf1ff] text-[0.95rem] font-extrabold text-[#4e70c9]">↗</span><h3 className="m-0 text-[0.88rem] tracking-[-0.025em] text-[#39364d]">References found</h3></div>{selectedAnalysis.refs_found.length ? <ol className="mt-5 grid list-none gap-[0.7rem] p-0">{selectedAnalysis.refs_found.map((reference, index) => <li className="relative grid grid-cols-[24px_1fr] items-start gap-[0.72rem] py-[0.72rem]" key={reference}><span className="relative z-10 grid h-[22px] w-[22px] place-items-center self-start rounded-[7px] border border-[#c9d8fb] bg-[#f1f5ff] text-[0.62rem] font-extrabold tabular-nums text-[#5574cd]">{String(index + 1).padStart(2, "0")}</span>{index < selectedAnalysis.refs_found.length - 1 && <span className="absolute left-[11px] top-[34px] h-[calc(100%+0.7rem)] w-px bg-[#c8d7fb]"/>}<div className="min-w-0"><span className="inline-flex h-[22px] items-center rounded bg-[#edf3ff] px-[0.38rem] py-[0.16rem] text-[0.58rem] font-extrabold uppercase tracking-[0.05em] text-[#4c6cc3]">{/^https?:\/\//i.test(reference) ? "URL" : "Citation"}</span><p className="mt-[0.32rem] [overflow-wrap:anywhere] text-[0.78rem] font-medium leading-[1.5] text-[#3f5280]">{reference}</p></div></li>)}</ol> : <div className="mt-5 rounded-[10px] border border-dashed border-[#dad9e1] bg-white p-[0.95rem]"><strong className="text-[0.78rem] text-[#4e4d5b]">No references found on this slide</strong><p className="mt-[0.35rem] text-[0.72rem] leading-[1.45] text-[#82808e]">Only citations and links visible on the slide are listed here.</p></div>}<small className="mt-[1.2rem] block px-[0.2rem] text-[0.69rem] leading-[1.4] text-[#92919f]">Detection only — this result does not validate credibility or accuracy.</small></section>}</>}</aside>
      </div>
    </section>
  </main>;
}
