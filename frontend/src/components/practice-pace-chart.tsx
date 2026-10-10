"use client";

import { useState } from "react";
import { PracticeSpeechMoment, type SpeechMoment } from "./practice-speech-moment";

export type PaceSample = {
  start_seconds: number; end_seconds: number; timestamp_seconds: number;
  words_per_minute: number; word_count: number;
  type: "slow" | "steady" | "fast"; context: string;
};
export type PaceEvent = {
  type: "slow" | "fast"; start_seconds: number; end_seconds: number;
  words_per_minute: number; context: string;
};

function time(seconds: number) {
  const total = Math.max(0, Math.round(seconds));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function PracticePaceChart({ samples, events, duration, moments, accessToken }: {
  samples: PaceSample[]; events: PaceEvent[]; duration: number;
  moments: SpeechMoment[]; accessToken: string | null;
}) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const selected = events[selectedIndex] ?? events[0];
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const inspected = hoverIndex === null ? null : samples[hoverIndex];
  const w = 1100, h = 290, left = 52, right = 26, top = 25, bottom = 42;
  const end = Math.max(duration, ...samples.map(s => s.end_seconds), 1);
  const maximum = Math.max(240, Math.ceil(Math.max(...samples.map(s => s.words_per_minute), 0) / 60) * 60);
  const x = (t: number) => left + t / end * (w - left - right);
  const y = (v: number) => top + (1 - v / maximum) * (h - top - bottom);
  const color = (type: string) => type === "fast" ? "#db6b47" : type === "slow" ? "#4d83ba" : "#8170cc";
  const moment = selected && moments.find(m => m.kind === selected.type
    && Math.abs(m.event_start_seconds - selected.start_seconds) < 0.1);

  return <section className="practice-panel" aria-labelledby="pace-heading">
    <div className="practice-panel-heading">
      <div><p className="practice-eyebrow">Speech delivery</p><h2 id="pace-heading">Where your pace changes</h2>
        <p className="practice-muted">Select a highlighted interval to see what to practise. Hover or tap the chart to inspect a measurement.</p></div>
      <span className="practice-count">{events.length} intervals to review</span>
    </div>
    {samples.length ? <>
      <div className="practice-chart-key">
        <span><i style={{ background: "#db6b47" }} />Faster passage · above reference or your usual pace</span>
        <span><i style={{ background: "#4d83ba" }} />Slower passage · may be intentional</span>
        <span><i style={{ background: "#8170cc" }} />No pronounced pace change</span>
      </div>
      <div className="practice-chart-scroll">
        <svg className="practice-chart" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Speaking pace estimates. Orange and blue mark faster and slower passages to review, not confirmed delivery mistakes."
          onMouseLeave={() => setHoverIndex(null)}>
          <rect x={left} y={y(180)} width={w-left-right} height={y(100)-y(180)} fill="#f4f2fb" />
          {selected && <rect x={x(selected.start_seconds)} y={top} width={Math.max(3, x(selected.end_seconds)-x(selected.start_seconds))} height={h-top-bottom} fill={color(selected.type)} opacity=".12" />}
          {[0, 100, 180, maximum].map(value => <g key={value}>
            <line x1={left} x2={w-right} y1={y(value)} y2={y(value)} stroke="#dedce7" strokeDasharray={value === 100 || value === 180 ? "5 5" : undefined} />
            <text x={left-10} y={y(value)+4} textAnchor="end" fill="#777180" fontSize="12">{value}</text>
          </g>)}
          <text x={left} y="13" fill="#777180" fontSize="11">WORDS / MIN</text>
          {samples.slice(1).map((sample, i) => {
            const previous = samples[i];
            if (sample.timestamp_seconds - previous.timestamp_seconds > 5.1) return null;
            return <line key={sample.timestamp_seconds} x1={x(previous.timestamp_seconds)} x2={x(sample.timestamp_seconds)} y1={y(previous.words_per_minute)} y2={y(sample.words_per_minute)} stroke={color(sample.type)} strokeWidth="3" strokeLinecap="round" />;
          })}
          {samples.map((sample, i) => <g key={sample.timestamp_seconds}>
            <circle cx={x(sample.timestamp_seconds)} cy={y(sample.words_per_minute)} r={hoverIndex === i ? 5 : 2.5} fill={color(sample.type)} />
            <rect x={x(sample.timestamp_seconds)-Math.max(4,(w-left-right)*2.5/end)} y={top} width={Math.max(8,(w-left-right)*5/end)} height={h-top-bottom}
              fill="transparent" onMouseEnter={() => setHoverIndex(i)} onClick={() => setHoverIndex(i)}>
              <title>{time(sample.start_seconds)}–{time(sample.end_seconds)}: {sample.words_per_minute} WPM</title>
            </rect>
          </g>)}
          {inspected && <line x1={x(inspected.timestamp_seconds)} x2={x(inspected.timestamp_seconds)} y1={top} y2={h-bottom} stroke="#777180" strokeDasharray="3 4" pointerEvents="none" />}
          {[0,.2,.4,.6,.8,1].map(fraction => <text key={fraction} x={x(end*fraction)} y={h-14} textAnchor={fraction === 0 ? "start" : fraction === 1 ? "end" : "middle"} fill="#777180" fontSize="12">{time(end*fraction)}</text>)}
        </svg>
      </div>
      <div className="practice-chart-caption" aria-live="polite">
        {inspected ? <strong>{time(inspected.start_seconds)}–{time(inspected.end_seconds)} · {Math.round(inspected.words_per_minute)} WPM over 15 seconds</strong>
          : <span>15-second averages, sampled every 5 seconds. No estimate is made from the final partial window.</span>}
        <span>Timing is estimated from speech transcription.</span>
      </div>
    </> : <p className="practice-empty">This recording has no complete pace timeline. A new analysis is needed to draw the chart; any saved intervals remain below.</p>}
    {events.length ? <div className="practice-pace-details">
      <div><p className="practice-eyebrow">Choose a moment</p>
        <div className="practice-intervals">{events.map((event, i) =>
          <button type="button" className={i === selectedIndex ? "is-selected" : ""} aria-pressed={i === selectedIndex} key={`${event.start_seconds}-${i}`} onClick={() => setSelectedIndex(i)}>
            <i style={{ background: color(event.type) }} /><span>{time(event.start_seconds)}–{time(event.end_seconds)}</span>
            <small>{event.type === "fast" ? "Fast" : "Slow"}</small>
          </button>)}</div>
      </div>
      {selected && <div className="practice-selected" aria-live="polite">
        <div className="practice-selected-title"><h3>{selected.type === "fast" ? "Review this faster passage" : "Review this slower passage or pause"}</h3><span>{Math.round(selected.words_per_minute)} WPM*</span></div>
        {moment ? <PracticeSpeechMoment key={moment.id} moment={moment} accessToken={accessToken} />
          : <p>No coaching excerpt was retained for this interval. Each new report keeps up to 12 selected speech moments.</p>}
        <small>*Average of overlapping pace measurements in the selected interval. A slow interval alone does not prove a mistake.</small>
      </div>}
    </div> : samples.length ? <p className="practice-empty">No measured interval crossed the fast or slow review thresholds.</p> : null}
  </section>;
}
