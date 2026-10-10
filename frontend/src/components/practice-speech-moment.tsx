"use client";

import { useEffect, useState } from "react";

export type SpeechMoment = {
  id: number; kind: string;
  event_start_seconds: number; event_end_seconds: number;
  start_seconds: number; end_seconds: number;
  transcript_excerpt: string; timing_source: string;
  coaching_status: string; observation: string | null;
  recommendation: string | null; suggested_delivery: string | null;
  audio_url: string | null;
};

function time(seconds: number) {
  const s = Math.round(seconds);
  return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
}

export function PracticeSpeechMoment({ moment, accessToken }: {
  moment: SpeechMoment; accessToken: string | null;
}) {
  const [source, setSource] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    setSource(null);
    setError(false);
    if (!accessToken || !moment.audio_url) return;
    const controller = new AbortController();
    let url: string | null = null;
    void (async () => {
      try {
        const response = await fetch(
          (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000") + moment.audio_url,
          { headers: { Authorization: "Bearer " + accessToken }, signal: controller.signal },
        );
        if (!response.ok) throw new Error("Audio unavailable");
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        url = URL.createObjectURL(blob);
        setSource(url);
      } catch {
        if (!controller.signal.aborted) setError(true);
      }
    })();
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [accessToken, moment.audio_url]);

  return <div className="practice-speech-excerpt">
    <p className="practice-eyebrow">What you said · {time(moment.start_seconds)}–{time(moment.end_seconds)}</p>
    <blockquote className={expanded ? "" : "practice-excerpt-collapsed"}>{moment.transcript_excerpt}</blockquote>
    {moment.transcript_excerpt.length > 180 && <button type="button" className="practice-text-toggle" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? "Show less" : "Read full excerpt"}</button>}
    <small>Automatic transcription · wording and timing may contain recognition errors.</small>
    {source ? <audio key={source} controls preload="metadata" src={source} aria-label={"Listen to speech at " + time(moment.start_seconds)} />
      : <p className="practice-note">{error ? "Audio could not be loaded. Refresh to retry." : moment.audio_url ? "Loading audio excerpt…" : "Audio is unavailable for this excerpt."}</p>}
    {moment.coaching_status === "ready" ? <>
      <p className="practice-eyebrow">Delivery feedback</p>
      <p>{moment.observation}</p>
      <p className="practice-recommendation">{moment.recommendation}</p>
      <details className="practice-delivery-example"><summary>Try saying it this way</summary>
        <blockquote className="practice-rehearsal">{moment.suggested_delivery}</blockquote>
      </details>
    </> : <p className="practice-note">The excerpt is available, but specific coaching could not be generated for this moment.</p>}
  </div>;
}
