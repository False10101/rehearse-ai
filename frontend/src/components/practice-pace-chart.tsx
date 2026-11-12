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
  const w = 1100, h = 250, left = 52, right = 26, top = 22, bottom = 42;
  const end = Math.max(duration, ...samples.map(s => s.end_seconds), 1);
  const maximum = Math.max(240, Math.ceil(Math.max(...samples.map(s => s.words_per_minute), 0) / 60) * 60);
  const x = (t: number) => left + t / end * (w - left - right);
  const y = (v: number) => top + (1 - v / maximum) * (h - top - bottom);
  const color = (type: string) => type === "fast" ? "#bd432b" : type === "slow" ? "#2866a4" : "#67528e";
  const moment = selected && moments.find(m => m.kind === selected.type
    && Math.abs(m.event_start_seconds - selected.start_seconds) < 0.1);

  return <section className="practice-panel practice-pace-panel" aria-labelledby="pace-heading">
    <div className="practice-panel-heading">
      <div><p className="practice-eyebrow">Speaking pace</p><h2 id="pace-heading">Find a pace your audience can follow</h2>
        <p className="practice-muted">See where you spoke quickly or slowly. Select a highlighted section to listen and read the advice.</p></div>
      <span className="practice-count">{events.length} {events.length === 1 ? "passage" : "passages"} to review</span>
    </div>
    {samples.length ? <>
      <div className="practice-pace-overview">
      <div className="practice-pace-chart-heading"><h3>Pace across your recording</h3><div className="practice-chart-key">
        <span><i style={{ background: "#51416f" }} />Measured pace</span>
        <span><i style={{ background: "#bd432b" }} />Faster passage</span>
        <span><i style={{ background: "#2866a4" }} />Slower passage</span>
      </div></div>
      <div className="practice-chart-scroll">
        <svg className="practice-chart" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Speaking pace estimates. The dark line shows measured words per minute. Orange and blue points and shading mark faster and slower passages to review."
          onMouseLeave={() => setHoverIndex(null)}>

          {events.map((event, index) => <g key={`${event.type}-${event.start_seconds}`}>
            <rect x={x(event.start_seconds)} y={top} width={Math.max(1, x(event.end_seconds)-x(event.start_seconds))} height={h-top-bottom}
              fill={event.type === "fast" ? "#e37866" : "#6e9fd1"} fillOpacity={index === selectedIndex ? .28 : .18}
              onClick={() => setSelectedIndex(index)} style={{ cursor: "pointer" }} />

          </g>)}
          {Array.from({ length: 5 }, (_, i) => maximum * i / 4).map(value => <g key={value}>
            <line x1={left} x2={w-right} y1={y(value)} y2={y(value)} stroke="#c8c4d0" strokeWidth="1" pointerEvents="none" />
            <text x={left-10} y={y(value)+4} textAnchor="end" fill="#777180" fontSize="12">{value}</text>
          </g>)}
          <text x={left} y="13" fill="#777180" fontSize="11">WORDS / MIN</text>
          {samples.slice(1).map((sample, i) => {
            const previous = samples[i];
            if (sample.timestamp_seconds - previous.timestamp_seconds > 5.1) return null;
            return <line key={sample.timestamp_seconds} x1={x(previous.timestamp_seconds)} x2={x(sample.timestamp_seconds)} y1={y(previous.words_per_minute)} y2={y(sample.words_per_minute)} stroke="#51416f" strokeWidth="2.5" strokeLinecap="round" />;
          })}
          {samples.map((sample, i) => <g key={sample.timestamp_seconds}>
            <circle cx={x(sample.timestamp_seconds)} cy={y(sample.words_per_minute)} r={hoverIndex === i ? 4 : 2.8} fill={color(sample.type)} stroke="white" strokeWidth="1.2" />
            <rect x={x(sample.timestamp_seconds)-Math.max(4,(w-left-right)*2.5/end)} y={top} width={Math.max(8,(w-left-right)*5/end)} height={h-top-bottom}
              fill="transparent" style={{ cursor: events.some(event => sample.timestamp_seconds >= event.start_seconds && sample.timestamp_seconds <= event.end_seconds) ? "pointer" : "crosshair" }} onMouseEnter={() => setHoverIndex(i)} onClick={() => {
                setHoverIndex(i);
                const index = events.findIndex(event => sample.timestamp_seconds >= event.start_seconds && sample.timestamp_seconds <= event.end_seconds);
                if (index >= 0) setSelectedIndex(index);
              }}>
              <title>{`${time(sample.start_seconds)}–${time(sample.end_seconds)}: ${sample.words_per_minute} WPM`}</title>
            </rect>
          </g>)}
          {inspected && <line x1={x(inspected.timestamp_seconds)} x2={x(inspected.timestamp_seconds)} y1={top} y2={h-bottom} stroke="#777180" strokeDasharray="3 4" pointerEvents="none" />}
          {[0,.2,.4,.6,.8,1].map(fraction => <text key={fraction} x={x(end*fraction)} y={h-14} textAnchor={fraction === 0 ? "start" : fraction === 1 ? "end" : "middle"} fill="#777180" fontSize="12">{time(end*fraction)}</text>)}
        </svg>
      </div>
      <div className="practice-chart-caption" aria-live="polite">
        {inspected ? <strong>{time(inspected.start_seconds)}–{time(inspected.end_seconds)} · {Math.round(inspected.words_per_minute)} WPM over 15 seconds</strong>
          : <span>Hover over the line to inspect a passage. Click an orange or blue point to review that passage below.</span>}
        <span>Measured {time(samples[0].start_seconds)}–{time(samples[samples.length - 1].end_seconds)}. Each point sits at the middle of its 15-second passage.</span>
      </div>
      </div>
    </> : <p className="practice-empty">The speaking-speed chart is unavailable. Analyze the recording again to create it. Saved sections are shown below.</p>}
    {events.length ? <div className="practice-pace-details">
      <div className="practice-pace-picker"><p className="practice-eyebrow">Choose a passage to practise</p>
        <div className="practice-intervals">{events.map((event, i) =>
          <button type="button" className={i === selectedIndex ? "is-selected" : ""} aria-pressed={i === selectedIndex} key={`${event.start_seconds}-${i}`} onClick={() => setSelectedIndex(i)}>
            <i style={{ background: color(event.type) }} /><span>{time(event.start_seconds)}–{time(event.end_seconds)}</span>
            <small>{event.type === "fast" ? "Faster" : "Slower"}</small>
          </button>)}</div>
      </div>
      {selected && <div className="practice-selected practice-pace-review" aria-live="polite">
        <div className="practice-selected-title"><div><p className={`practice-pace-review-label ${selected.type}`}>{selected.type === "fast" ? "Faster passage" : "Slower passage"} · {time(selected.start_seconds)}–{time(selected.end_seconds)}</p><h3>Listen and practise</h3></div><span className="practice-pace-estimate"><span>Estimated pace</span>{Math.round(selected.words_per_minute)} words/min</span></div>
        {moment ? <PracticeSpeechMoment key={moment.id} moment={moment} accessToken={accessToken} presentation="review" />
          : <p>The audio and transcript for this section are unavailable. Analyze the recording again to create them.</p>}
        <p className="practice-pace-review-note">Speed is estimated for each 15-second section. Listen to the recording to decide where to slow down or speak more quickly.</p>
      </div>}
    </div> : samples.length ? <p className="practice-empty">No unusually fast or slow sections were detected.</p> : null}
  </section>;
}
