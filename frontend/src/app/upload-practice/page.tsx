"use client";

import { ProcessingSteps } from "@/components/processing-steps";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/auth/auth-provider";
import { Brand } from "@/components/brand";
import { PracticeGestures, type PoseTracking } from "@/components/practice-gestures";
import { PracticePaceChart, type PaceSample, type PaceEvent } from "@/components/practice-pace-chart";
import "./practice.css";
import { PracticeSpeechMoment, type SpeechMoment } from "@/components/practice-speech-moment";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type PoseEvent = {
  evidence_video_url?: string | null;
  type: string;
  label: string;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  confidence: number;
  feedback: string;
  evidence_image_url: string | null;
};

type CoachingFinding = {
  id: string;
  category: string;
  headline: string;
  observation: string;
  impact: string;
  recommendation: string;
  drill: string;
  start_seconds: number;
  end_seconds: number;
  evidence_image_url: string | null;
};

type PracticeReport = {
  speech_coaching_status?: string | null;
  id: string;
  original_filename: string;
  status: "queued" | "processing" | "completed" | "failed";
  progress_percent: number;
  duration_seconds: number | null;
  video_width: number | null;
  video_height: number | null;
  video_codec: string | null;
  transcript: string | null;
  word_count: number | null;
  speech_duration_seconds: number | null;
  words_per_minute: number | null;
  filler_events: Array<{ term: string; timestamp_seconds: number; context?: string }>;
  filler_clusters: Array<{ start_seconds: number; end_seconds: number; count: number; terms: string[]; context: string }>;
  pause_events: Array<{ start_seconds: number; end_seconds: number; duration_seconds: number; severity: "noticeable" | "long"; context: string }>;
  pace_samples: PaceSample[];
  speech_moments: SpeechMoment[];
  pace_events: PaceEvent[];
  repetition_events: Array<{ timestamp_seconds: number; phrase: string; context: string }>;
  sensitive_term_flags: Array<{ term: string; timestamp_seconds: number; context: string }>;
  pose_events: PoseEvent[];
  pose_tracking?: PoseTracking | null;
  coaching_findings: CoachingFinding[];
  coaching_strengths: string[];
  practice_plan: string[];
  processing_error_code: string | null;
  processing_error_message: string | null;
  created_at: string;
  completed_at: string | null;
};

function apiError(payload: unknown, fallback: string) {
  return typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string"
    ? payload.detail
    : fallback;
}

function formatTime(seconds: number | null) {
  if (seconds === null || !Number.isFinite(seconds)) return "—";
  const rounded = Math.max(0, Math.round(seconds));
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Recently" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function EvidenceImage({ finding, accessToken }: { finding: CoachingFinding; accessToken: string | null }) {
  const [source, setSource] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setSource(null);
    setFailed(false);
    if (!finding.evidence_image_url || !accessToken) return;
    let active = true;
    let objectUrl: string | null = null;
    void (async () => {
      try {
        const response = await fetch(`${apiBaseUrl}${finding.evidence_image_url}`, { headers: { Authorization: `Bearer ${accessToken}` } });
        if (!response.ok) throw new Error("Image unavailable");
        objectUrl = URL.createObjectURL(await response.blob());
        if (active) setSource(objectUrl);
      } catch {
        if (active) setFailed(true);
      }
    })();
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [accessToken, finding.evidence_image_url]);
  return <div className="aspect-video overflow-hidden rounded-2xl border border-[#e4e2ea] bg-[#efeff3]">{source ? <img alt={`Evidence for ${finding.headline} at ${formatTime(finding.start_seconds)}`} className="h-full w-full object-cover" src={source} /> : <div className="grid h-full place-items-center px-5 text-center text-xs font-semibold leading-5 text-[#8a8795]">{failed ? "Frame could not be loaded." : "Loading frame…"}</div>}</div>;
}

function UploadIcon() {
  return <svg aria-hidden="true" fill="none" height="26" viewBox="0 0 24 24" width="26"><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M4 15.5V18a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" /></svg>;
}

export default function UploadPracticePage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { getAccessToken } = useAuth();
  const fileInput = useRef<HTMLInputElement>(null);
  const requestedSession = searchParams.get("session");
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [report, setReport] = useState<PracticeReport | null>(null);
  const [loading, setLoading] = useState(Boolean(requestedSession));
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [retryingSpeech, setRetryingSpeech] = useState(false);

  const loadReport = useCallback(async (silent = false) => {
    if (!requestedSession) return;
    if (!silent) setLoading(true);
    try {
      const token = accessToken ?? await getAccessToken();
      setAccessToken(token);
      const response = await fetch(`${apiBaseUrl}/api/v1/practice/upload/sessions/${requestedSession}`, { headers: { Authorization: `Bearer ${token}` } });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new Error(apiError(payload, "The practice report could not be loaded."));
      setReport(payload as PracticeReport);
      setError("");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "The practice report could not be loaded.");
    } finally {
      if (!silent) setLoading(false);
    }
  }, [accessToken, getAccessToken, requestedSession]);

  useEffect(() => { if (requestedSession) void loadReport(); }, [loadReport, requestedSession]);
  useEffect(() => {
    if (!report || (!["queued", "processing"].includes(report.status) && !["queued", "running"].includes(report.speech_coaching_status ?? ""))) return;
    const timer = window.setInterval(() => void loadReport(true), 2000);
    return () => window.clearInterval(timer);
  }, [loadReport, report]);

  const retrySpeech = async () => {
    if (!report) return;
    setRetryingSpeech(true);
    setError("");
    try {
      const token = accessToken ?? await getAccessToken();
      const response = await fetch(`${apiBaseUrl}/api/v1/practice/upload/sessions/${report.id}/speech/retry`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new Error(apiError(payload, "Speech feedback could not be retried."));
      await loadReport(true);
    } catch (retryError) {
      setError(retryError instanceof Error ? retryError.message : "Speech feedback could not be retried.");
    } finally { setRetryingSpeech(false); }
  };

  const upload = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".mp4")) { setError("Choose an MP4 rehearsal video."); return; }
    if (file.size > 500 * 1024 * 1024) { setError("The rehearsal video must be 500 MB or smaller."); return; }
    setUploading(true);
    setError("");
    try {
      const token = accessToken ?? await getAccessToken();
      setAccessToken(token);
      const body = new FormData();
      body.append("file", file);
      const response = await fetch(`${apiBaseUrl}/api/v1/practice/upload/sessions`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok || typeof payload !== "object" || payload === null || !("id" in payload) || typeof payload.id !== "string") throw new Error(apiError(payload, "The rehearsal video could not be uploaded."));
      router.replace(`/upload-practice?session=${payload.id}`);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "The rehearsal video could not be uploaded.");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const deleteReport = async () => {
    if (!report || !window.confirm("Delete this report and its retained evidence frames?")) return;
    try {
      const token = accessToken ?? await getAccessToken();
      const response = await fetch(`${apiBaseUrl}/api/v1/practice/upload/sessions/${report.id}`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw new Error("The report could not be deleted.");
      router.replace("/upload-practice");
      setReport(null);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "The report could not be deleted.");
    }
  };


  const processing = report && ["queued", "processing"].includes(report.status);
  const stage = !report || report.status === "queued" ? "Waiting to start"
    : report.progress_percent < 20 ? "Preparing your recording"
    : report.progress_percent < 80 ? "Reviewing body language" : report.progress_percent < 90 ? "Reviewing speech delivery" : "Building your feedback";
  return <main className="practice-page">
    <nav className="practice-nav" aria-label="Workspace navigation">
      <div className="practice-nav-brand"><Link href="/home"><Brand /></Link><span>Upload Practice</span></div>
      <Link className="practice-button" href="/home">Back to workspace</Link>
    </nav>
    <div className="practice-scroll"><div className="practice-content">
      {error && <div className="practice-error" role="alert">{error}</div>}
      {!requestedSession ? <>
        <header className="practice-heading"><div><h1>Learn from your last rehearsal.</h1><p className="practice-muted">Review your delivery and choose what to practise next.</p></div></header>
        <section className="practice-panel">
          <div className="practice-panel-heading"><div><p className="practice-eyebrow">Recorded practice</p><h2>Upload a presentation recording</h2><p className="practice-muted">Get speech feedback with timestamps and body-language feedback with captured frames.</p></div></div>
          <div className="practice-upload"><UploadIcon /><h3>Start with a rehearsal video</h3><p>For body-language feedback, keep your face, arms, and torso visible.<br />Use clear audio for speech analysis.</p>
            <input accept="video/mp4,.mp4" className="hidden" ref={fileInput} type="file" onChange={event => { const file = event.target.files?.[0]; if (file) void upload(file); }} />
            <button className="practice-button primary" type="button" disabled={uploading} onClick={() => fileInput.current?.click()}>{uploading ? "Uploading recording…" : "Choose recording"}</button>
            <p style={{ marginBottom: 0 }}>MP4 / H.264 · up to 10 minutes · 1080p · 500 MB</p>
          </div>
        </section>
        <p className="practice-note">The full video and extracted audio are removed after analysis. Your private report keeps the transcript, up to 12 short audio excerpts, and a frame for every detected gesture with a silent replay clip when available. Longer gestures can have longer clips so the movement is not cut off. Deleting the report removes its saved evidence too.</p>
      </> : loading || !report ? <section className="practice-panel practice-loading"><h2>Loading your report…</h2><p className="practice-muted">Retrieving your rehearsal feedback.</p></section>
        : processing ? <section className="practice-panel practice-loading" aria-live="polite"><p className="practice-eyebrow">Analyzing recording</p><h2>{stage}</h2><ProcessingSteps steps={["Waiting to start", "Prepare recording", "Review gestures & retain clips", "Review speech", "Build feedback & save report"]} current={report.status === "queued" ? 0 : report.progress_percent < 20 ? 1 : report.progress_percent < 80 ? 2 : report.progress_percent < 90 ? 3 : 4} /><p className="practice-muted">You can return to your workspace while this finishes.</p><div className="practice-progress" role="progressbar" aria-valuenow={report.progress_percent} aria-valuemin={0} aria-valuemax={100}><div style={{ width: report.progress_percent + "%" }} /></div><p className="practice-muted">{report.progress_percent}% complete</p></section>
        : report.status === "failed" ? <section className="practice-panel practice-loading"><p className="practice-eyebrow">Needs attention</p><h2>Analysis could not finish</h2><p className="practice-muted">{report.processing_error_message ?? "Please upload the recording again."}</p><div className="practice-actions" style={{ marginTop: 20 }}><Link className="practice-button" href="/upload-practice">Upload another</Link><button type="button" className="practice-button danger" onClick={() => void deleteReport()}>Delete report</button></div></section>
        : <ReportView key={report.id} accessToken={accessToken} deleteReport={deleteReport} report={report} retrySpeech={retrySpeech} retryingSpeech={retryingSpeech} />}
    </div></div>
  </main>;
}

function FindingCard({ finding, accessToken, moment }: { finding: CoachingFinding; accessToken: string | null; moment?: SpeechMoment }) {
  const body = finding.category === "Body language";
  return <article className="practice-finding">
    <header><h3>{finding.headline}</h3><span>{formatTime(finding.start_seconds)}–{formatTime(finding.end_seconds)}</span></header>
    <p>{finding.observation}</p>
    {moment ? <PracticeSpeechMoment moment={moment} accessToken={accessToken} />
      : <p className="practice-recommendation">{finding.recommendation}</p>}
    {body && finding.evidence_image_url && <details><summary>View body-language frame</summary><div style={{ marginTop: 12 }}><EvidenceImage accessToken={accessToken} finding={finding} /></div></details>}
    <details><summary>Practice this moment</summary><p>{finding.drill}</p></details>
  </article>;
}

function ReportView({ report, accessToken, deleteReport, retrySpeech, retryingSpeech }: { report: PracticeReport; accessToken: string | null; deleteReport: () => Promise<void>; retrySpeech: () => Promise<void>; retryingSpeech: boolean }) {
  const speechFindings = report.coaching_findings.filter(f => f.id !== "pace-control" && f.category !== "Body language");
  const speechBusy = retryingSpeech || ["queued", "running"].includes(report.speech_coaching_status ?? "");
  const missingSpeech = (report.speech_moments ?? []).filter(m => m.coaching_status !== "ready").length;
  return <>
    <header className="practice-heading"><div><p className="practice-eyebrow">Rehearsal report</p><h1>{report.original_filename}</h1><p className="practice-muted">{formatTime(report.duration_seconds)} recording · {formatDate(report.completed_at ?? report.created_at)}</p></div>
      <div className="practice-actions"><Link className="practice-button" href="/upload-practice">New recording</Link><button className="practice-button danger" onClick={() => void deleteReport()} type="button">Delete</button></div>
    </header>
    <PracticeGestures events={report.pose_events} token={accessToken} tracking={report.pose_tracking} />
    {missingSpeech > 0 && <div className="practice-panel" role="status" style={{ padding: "16px 20px", display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", justifyContent: "space-between" }}><p className="practice-muted" style={{ margin: 0 }}>{speechBusy ? "Generating the missing speech feedback. Your existing results are kept." : `Feedback is missing for ${missingSpeech} speech moment${missingSpeech === 1 ? "" : "s"}. Retry using your saved excerpts—no new upload needed.`}</p><button className="practice-button" type="button" disabled={speechBusy} onClick={() => void retrySpeech()}>{speechBusy ? "Generating feedback…" : "Retry speech feedback"}</button></div>}
    <div className="practice-report-sections">
      <section className="practice-panel"><div className="practice-panel-heading"><div><p className="practice-eyebrow">Clarity & fluency</p><h2>Speech moments to practise</h2></div></div>
        {speechFindings.length ? <div className="practice-speech-grid">{speechFindings.map(f => <details className="practice-speech-row" key={f.id}>
          <summary><span>{f.headline}</span><time>{formatTime(f.start_seconds)}–{formatTime(f.end_seconds)}</time></summary>
          <FindingCard finding={f} accessToken={accessToken} moment={(report.speech_moments ?? []).find(m => m.kind === f.id)} />
        </details>)}</div> : <p className="practice-empty">No additional speech coaching was returned.</p>}
      </section>
    </div>
    <PracticePaceChart samples={report.pace_samples ?? []} events={report.pace_events ?? []} duration={report.duration_seconds ?? 0} moments={report.speech_moments ?? []} accessToken={accessToken} />
  </>;
}
