"use client";

import { ProcessingSteps } from "@/components/processing-steps";
import { PracticeProcessing, type ReviewTrack } from "@/components/practice-processing";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/auth/auth-provider";
import { Brand } from "@/components/brand";
import { PracticeGestures, type PoseTracking } from "@/components/practice-gestures";
import { PracticePaceChart, type PaceSample, type PaceEvent } from "@/components/practice-pace-chart";
import "./practice.css";
import "./practice-polish.css";
import { DeletePracticeReportDialog } from "@/components/delete-practice-report-dialog";
import { PracticeSpeechMoment, type SpeechMoment } from "@/components/practice-speech-moment";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type PoseEvent = {
  detection?: { is_issue?: boolean } | null;
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
  processing_tracks?: Partial<Record<"gestures" | "speech", ReviewTrack>> | null;
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

function GuestRecordingNotice() {
  const { login } = useAuth();
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState("");
  async function signIn() {
    setConnecting(true); setError("");
    try { await login(); }
    catch { setError("Sign-in couldn’t start. Please try again."); setConnecting(false); }
  }
  return <aside className="practice-guest-notice" aria-label="Recording uploads require sign-in">
    <div><h2>Want to upload your own recording?</h2>
      <p>Sign in with Google to upload and analyze your rehearsal. Guests can explore the sample report.</p>
      {error && <p role="alert">{error}</p>}
    </div>
    <button type="button" className="practice-button primary" disabled={connecting} onClick={() => void signIn()}>{connecting ? "Connecting to Google…" : "Sign in to upload"}</button>
  </aside>;
}

export default function UploadPracticePage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { getAccessToken, isGuest } = useAuth();
  const fileInput = useRef<HTMLInputElement>(null);
  const requestedSession = searchParams.get("session");
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [report, setReport] = useState<PracticeReport | null>(null);
  const [loading, setLoading] = useState(Boolean(requestedSession));
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [retryingSpeech, setRetryingSpeech] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

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
    if (isGuest) { setError("Sign in with Google to upload your own recording."); return; }
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
    if (!report || deleting) return;
    setDeleting(true);
    try {
      const token = accessToken ?? await getAccessToken();
      const response = await fetch(`${apiBaseUrl}/api/v1/practice/upload/sessions/${report.id}`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw new Error("The report could not be deleted.");
      router.replace("/upload-practice");
      setReport(null);
      setConfirmDelete(false);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "The report could not be deleted.");
      setConfirmDelete(false);
    } finally { setDeleting(false); }
  };


  const processing = report && ["queued", "processing"].includes(report.status);
  const stage = !report || report.status === "queued" ? "Waiting to start"
    : report.progress_percent < 20 ? "Preparing your recording"
    : report.progress_percent < 95 ? "Reviewing body language and speech" : "Saving your report";
  useEffect(() => {
    if (!isGuest || requestedSession) return;
    let active = true;
    void getAccessToken().then(token => fetch(`${apiBaseUrl}/api/v1/practice/upload/sessions`, { headers: { Authorization: `Bearer ${token}` } }))
      .then(async response => {
        if (!response.ok) throw new Error("The sample report could not be loaded.");
        const reports: PracticeReport[] = await response.json();
        if (active && reports.length) router.replace(`/upload-practice?session=${reports[0].id}`);
      }).catch(error => { if (active) setError(error.message); });
    return () => { active = false; };
  }, [isGuest, requestedSession, getAccessToken, router]);

  return <main className={`practice-page${!requestedSession ? " practice-upload-page" : ""}`}>
    <nav className="practice-nav" aria-label="Workspace navigation">
      <div className="practice-nav-brand"><Link href="/home"><Brand /></Link><span>Upload Practice</span></div>
      <Link className="practice-button" href="/home">Back to workspace</Link>
    </nav>
    <div className="practice-scroll"><div className="practice-content">
      {isGuest && <GuestRecordingNotice />}
      {error && <div className="practice-error" role="alert">{error}</div>}
      {!requestedSession && isGuest ? <section className="practice-panel practice-loading"><p className="practice-eyebrow">Sample recording</p><h2>Explore Upload Practice</h2><p className="practice-muted">No sample report is available yet. You can still try Live Practice or upload slides as a guest.</p><Link className="practice-button" href="/home">Back to workspace</Link></section> : !requestedSession ? <>
        <header className="practice-heading"><div><h1>Learn from your last rehearsal.</h1><p className="practice-muted">Review your delivery and choose what to practise next.</p></div></header>
        <section className="practice-upload-layout">
          <div className="practice-upload" aria-busy={uploading}><span className="practice-upload-icon"><UploadIcon /></span><h3>Start with a rehearsal video</h3><p>For body-language feedback, keep your face, arms, and torso visible.<br />Use clear audio for speech analysis.</p>
            <input accept="video/mp4,.mp4" aria-label="Choose an MP4 rehearsal recording" className="hidden" ref={fileInput} type="file" onChange={event => { const file = event.target.files?.[0]; if (file) void upload(file); }} />
            <button className="practice-button primary" type="button" disabled={uploading} onClick={() => fileInput.current?.click()}>{uploading ? "Uploading recording…" : "Choose recording"}</button>
            <p style={{ marginBottom: 0 }}>MP4 / H.264 · up to 10 minutes · 1080p · 500 MB</p>
          </div>
          <aside className="practice-upload-guide"><h2>What you’ll get</h2>{[
            ["01", "Body language in context", "Review captured moments with frames, replay clips when available, and specific adjustments to try."],
            ["02", "Feedback you can hear", "Listen to speech excerpts and work on clarity, pauses, fillers, and repeated wording."],
            ["03", "A view of your speaking pace", "Explore changes across your recording and select a passage to practise."],
          ].map(([number, title, description]) => <div key={number}><span>{number}</span><section><h3>{title}</h3><p>{description}</p></section></div>)}</aside>
        </section>
        <p className="practice-note">The full video and extracted audio are removed after analysis. Your private report keeps speech excerpts with audio and captured gesture moments with replay clips when available. Deleting the report removes its saved evidence too.</p>
      </> : loading || !report ? <section className="practice-panel practice-loading"><h2>Loading your report…</h2><p className="practice-muted">Retrieving your rehearsal feedback.</p></section>
        : processing ? <section className="practice-panel practice-loading" aria-live="polite"><p className="practice-eyebrow">Analyzing recording</p><h2>{stage}</h2><ProcessingSteps steps={["Waiting to start", "Prepare recording", "Review body language and speech together", "Save report"]} current={report.status === "queued" ? 0 : report.progress_percent < 20 ? 1 : report.progress_percent < 95 ? 2 : 3} />{report.status === "processing" && report.progress_percent >= 20 && <PracticeProcessing tracks={report.processing_tracks} />}<p className="practice-muted">You can return to your workspace while this finishes.</p><div className="practice-progress" role="progressbar" aria-valuenow={report.progress_percent} aria-valuemin={0} aria-valuemax={100}><div style={{ width: report.progress_percent + "%" }} /></div><p className="practice-muted">{report.progress_percent}% complete</p></section>
        : report.status === "failed" ? <section className="practice-panel practice-loading"><p className="practice-eyebrow">Needs attention</p><h2>Analysis could not finish</h2><p className="practice-muted">{report.processing_error_message ?? "Please upload the recording again."}</p><div className="practice-actions" style={{ marginTop: 20 }}><Link className="practice-button" href="/upload-practice">Upload another</Link><button type="button" className="practice-button danger" onClick={() => setConfirmDelete(true)}>Delete report</button></div></section>
        : <ReportView readOnly={isGuest} key={report.id} accessToken={accessToken} deleteReport={async () => setConfirmDelete(true)} report={report} retrySpeech={retrySpeech} retryingSpeech={retryingSpeech} />}
    </div></div>
    {confirmDelete && <DeletePracticeReportDialog busy={deleting} onCancel={() => setConfirmDelete(false)} onConfirm={() => void deleteReport()} />}
  </main>;
}

function FillerBreakdown({ events }: { events: PracticeReport["filler_events"] }) {
  const groups = new Map<string, number[]>();
  for (const event of events) {
    const term = event.term.trim().toLowerCase();
    if (!term || !Number.isFinite(event.timestamp_seconds)) continue;
    const times = groups.get(term) ?? [];
    times.push(event.timestamp_seconds);
    groups.set(term, times);
  }
  if (!groups.size) return null;
  return <section className="practice-filler-breakdown" aria-label="Detected fillers">
    <h3>Detected fillers</h3>
    <table><thead><tr><th scope="col">Word or phrase</th><th scope="col">Count</th><th scope="col">When it occurred</th></tr></thead>
      <tbody>{Array.from(groups, ([term, times]) => <tr key={term}>
        <th scope="row">“{term}”</th><td>{times.length}</td>
        <td>{times.sort((a, b) => a - b).map(formatTime).join(", ")}</td>
      </tr>)}</tbody>
    </table>
  </section>;
}

function FindingCard({ finding, accessToken, moment }: { finding: CoachingFinding; accessToken: string | null; moment?: SpeechMoment }) {
  return <article className="practice-clarity-finding">
    <header><h3>{finding.headline}</h3><time>{formatTime(finding.start_seconds)}–{formatTime(finding.end_seconds)}</time></header>
    {moment ? <PracticeSpeechMoment moment={moment} accessToken={accessToken} presentation="review" />
      : <div className="practice-clarity-columns">
          <div><h4>What happened</h4><p>{finding.observation}</p></div>
          <div><h4>Try this next</h4><p>{finding.recommendation}</p>{finding.drill && <><h4>Practise it</h4><p>{finding.drill}</p></>}</div>
        </div>}
  </article>;
}

function ReportView({ readOnly, report, accessToken, deleteReport, retrySpeech, retryingSpeech }: { readOnly: boolean; report: PracticeReport; accessToken: string | null; deleteReport: () => Promise<void>; retrySpeech: () => Promise<void>; retryingSpeech: boolean }) {
  const reportElement = useRef<HTMLDivElement>(null);
  const [activeSection, setActiveSection] = useState("recording-gestures");
  const reportTabs = [
    ["recording-gestures", "Body language"],
    ["recording-clarity", "Clarity & fluency"],
    ["recording-pace", "Speaking pace"],
  ];
  const selectSection = (id: string) => {
    reportElement.current?.querySelectorAll<HTMLMediaElement>("video, audio").forEach(media => media.pause());
    setActiveSection(id);
    const shell = reportElement.current;
    const scroller = shell?.closest<HTMLElement>(".practice-scroll");
    const bar = shell?.querySelector<HTMLElement>(".practice-report-index");
    if (scroller && bar && bar.getBoundingClientRect().top <= scroller.getBoundingClientRect().top + 1) {
      const header = shell?.querySelector<HTMLElement>(".practice-report-header");
      if (header) scroller.scrollTop += header.getBoundingClientRect().bottom + parseFloat(getComputedStyle(header).marginBottom) - scroller.getBoundingClientRect().top;
    }
  };
  const speechFindings = report.coaching_findings.filter(f => f.id !== "pace-control" && f.category !== "Body language");
  const clarityMoments = (report.speech_moments ?? []).filter(m => m.kind !== "fast" && m.kind !== "slow");
  const clarityTitles: Record<string, string> = { "verbal-habit": "Fillers in this passage", "long-pause": "Pause between thoughts", "repeated-starts": "Repeated words or phrases", "sensitive-term": "Wording to review" };
  const speechBusy = retryingSpeech || ["queued", "running"].includes(report.speech_coaching_status ?? "");
  const missingSpeech = (report.speech_moments ?? []).filter(m => m.coaching_status !== "ready").length;
  return <div ref={reportElement} className="practice-report-shell">
    <header className="practice-report-header">
      <div className="practice-report-identity">
        <span className="practice-recording-icon" aria-hidden="true"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="4" /><path d="m10 8 6 4-6 4V8Z" /></svg></span>
        <div><p className="practice-eyebrow">Rehearsal report</p><h1>{report.original_filename}</h1></div>
      </div>
      <div className="practice-report-header-bottom">
        <dl className="practice-report-metadata">
          <div><dt>Recording length</dt><dd>{formatTime(report.duration_seconds)}</dd></div>
          <div><dt>Reviewed on</dt><dd>{formatDate(report.completed_at ?? report.created_at)}</dd></div>
        </dl>
        {!readOnly && <div className="practice-actions"><Link className="practice-button" href="/upload-practice"><svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>New recording</Link><button className="practice-button danger" onClick={() => void deleteReport()} type="button"><svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7" /></svg>Delete report</button></div>}
      </div>
    </header>
    <div className="practice-report-layout">
      <div className="practice-report-index" role="tablist" aria-label="Report sections">
        {reportTabs.map(([id, label], index) => <button key={id} id={`${id}-tab`} type="button" role="tab" aria-controls={id} aria-selected={activeSection === id} tabIndex={activeSection === id ? 0 : -1} onClick={() => selectSection(id)} onKeyDown={(event) => {
          let next = index;
          if (event.key === "ArrowRight") next = (index + 1) % reportTabs.length;
          else if (event.key === "ArrowLeft") next = (index + reportTabs.length - 1) % reportTabs.length;
          else if (event.key === "Home") next = 0;
          else if (event.key === "End") next = reportTabs.length - 1;
          else return;
          event.preventDefault();
          selectSection(reportTabs[next][0]);
          document.getElementById(`${reportTabs[next][0]}-tab`)?.focus();
        }}>{label}</button>)}
      </div>
      <div className="practice-report-body">
    <div id="recording-gestures" role="tabpanel" aria-labelledby="recording-gestures-tab" hidden={activeSection !== "recording-gestures"} className="practice-report-section"><PracticeGestures events={report.pose_events} token={accessToken} tracking={report.pose_tracking} duration={report.duration_seconds ?? 0} /></div>
    {!readOnly && activeSection !== "recording-gestures" && missingSpeech > 0 && <div className="practice-panel" role="status" style={{ padding: "16px 20px", display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", justifyContent: "space-between" }}><p className="practice-muted" style={{ margin: 0 }}>{speechBusy ? "Generating the missing speech feedback. Your existing results are kept." : `Feedback is missing for ${missingSpeech} speech moment${missingSpeech === 1 ? "" : "s"}. Retry using your saved excerpts—no new upload needed.`}</p><button className="practice-button" type="button" disabled={speechBusy} onClick={() => void retrySpeech()}>{speechBusy ? "Generating feedback…" : "Retry speech feedback"}</button></div>}
    <div id="recording-clarity" role="tabpanel" aria-labelledby="recording-clarity-tab" hidden={activeSection !== "recording-clarity"} className="practice-report-sections practice-report-section">
      <section className="practice-panel"><div className="practice-panel-heading"><div><p className="practice-eyebrow">Clarity & fluency</p><h2>Speech moments to practise</h2><p className="practice-muted">Review what you said, listen to the moment, and try the suggested delivery.</p></div></div>
        <FillerBreakdown events={report.filler_events ?? []} />
        {clarityMoments.length ? <div className="practice-clarity-findings">{clarityMoments.map(moment =>
          <article key={moment.id} className="practice-clarity-finding">
            <header><h3>{clarityTitles[moment.kind] ?? "Speech passage to review"}</h3><time>{formatTime(moment.event_start_seconds)}–{formatTime(moment.event_end_seconds)}</time></header>
            <PracticeSpeechMoment moment={moment} accessToken={accessToken} presentation="review" />
          </article>
        )}</div> : speechFindings.length ? <div className="practice-clarity-findings">{speechFindings.map(f =>
          <FindingCard key={f.id} finding={f} accessToken={accessToken} />
        )}</div> : <p className="practice-empty">No additional speech coaching was returned.</p>}
      </section>
    </div>
    <div id="recording-pace" role="tabpanel" aria-labelledby="recording-pace-tab" hidden={activeSection !== "recording-pace"} className="practice-report-section"><PracticePaceChart samples={report.pace_samples ?? []} events={report.pace_events ?? []} duration={report.duration_seconds ?? 0} moments={report.speech_moments ?? []} accessToken={accessToken} /></div>
      </div>
    </div>
  </div>;
}
