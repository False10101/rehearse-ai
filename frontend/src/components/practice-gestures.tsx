"use client";
import { useEffect, useRef, useState } from "react";

type Event = { type: string; label: string; start_seconds: number; duration_seconds: number; feedback: string; evidence_image_url: string | null; evidence_video_url?: string | null };
export type PoseTracking = {
  status: "reliable" | "limited" | "insufficient";
  reliable_body_percent: number;
  reliable_body_seconds: number;
  person_visible_percent: number;
  checks: { type: string; label: string; status: "reliable" | "limited" | "insufficient"; coverage_percent: number }[];
};
const time = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

type GestureAdvice = { title: string; observation: string; impact: string; action: string };
const advice: Record<string, GestureAdvice> = {
  arms_crossed: {
    title: "Release crossed arms between points",
    observation: "An arm reached across your body toward the opposite shoulder, or your forearms appeared folded across your torso.",
    impact: "If this becomes your resting pose, it can limit the gestures you use to explain or emphasize your message. A brief, intentional crossing is not automatically a problem.",
    action: "Replay this moment. If the crossing was unintentional, release your arms at the next transition and use a comfortable resting position before your next gesture.",
  },
  repeated_head_movement: {
    title: "Let your head settle between ideas",
    observation: "Repeated head turns or sideways tilts were estimated around this moment. This does not establish where your eyes were looking or whether you were reading notes.",
    impact: "Repeated back-and-forth movement may compete with what you are saying. Looking toward different listeners and nodding to emphasize a point can still be useful.",
    action: "Try the same passage again, letting your head settle while you finish each idea. Keep audience glances that serve a purpose rather than trying to stay completely still.",
  },
  repeated_swaying: {
    title: "Use a steadier stance for key points",
    observation: "Your upper body appeared to shift from side to side repeatedly.",
    impact: "Repeated swaying can draw attention away from the explanation when the movement is unrelated to the message.",
    action: "Replay the passage, then practise it with your weight comfortably balanced. Move deliberately at a transition, and settle before delivering the next key point.",
  },
  hand_near_face: {
    title: "Bring your hand back after an adjustment",
    observation: "Your hand appeared near your face for a sustained moment or on repeated occasions. The video check does not establish whether you touched your face.",
    impact: "Repeated incidental adjustments can compete with your message. A quick adjustment or a gesture that illustrates your point may be entirely appropriate.",
    action: "Watch what the hand was doing. If it was an incidental adjustment, finish it and return your hand to a relaxed position before continuing your explanation.",
  },
  hands_clasped_low: {
    title: "Give your hands room to support the message",
    observation: "Your hands appeared close together near the lower part of your torso.",
    impact: "Keeping them fixed there can reduce visible emphasis. Resting your hands together briefly is not itself a mistake.",
    action: "If your hands stayed fixed through a key point, try one natural gesture to illustrate it, then return to a comfortable resting position. You do not need to gesture constantly.",
  },
  gesture_box_excursion: {
    title: "Bring wide gestures back after the emphasis",
    observation: "An arm appeared close to a full sideways extension.",
    impact: "A large gesture can be effective emphasis, but holding it or repeating it without a clear purpose may pull attention away from your words.",
    action: "Check whether the reach supported the point. Keep it if it did; otherwise try a smaller reach and bring the arm back when the emphasis is finished.",
  },
};

function GestureGroup({ events, token }: { events: Event[]; token: string | null }) {
  const [selected, setSelected] = useState(0);
  type Replay = { url: string; video: boolean; timestamp: number; label: string };
  const [replay, setReplay] = useState<Replay | null>(null);
  const [incoming, setIncoming] = useState<Replay | null>(null);
  const [loading, setLoading] = useState(false);
  const urls = useRef(new Map<string, string>());
  const player = useRef<HTMLVideoElement | null>(null);
  const [failed, setFailed] = useState(false);
  const event = events[Math.min(selected, events.length - 1)];
  const coaching = advice[event.type] ?? {
    title: event.label,
    observation: event.feedback,
    impact: "A movement is worth changing only if it distracts from or makes your message harder to follow.",
    action: "Replay the moment and compare it with your intended emphasis. Try the passage again with a more deliberate movement if needed.",
  };
  const path = event.evidence_video_url || event.evidence_image_url;
  useEffect(() => {
    const cache = urls.current;
    return () => { for (const url of cache.values()) URL.revokeObjectURL(url); cache.clear(); };
  }, [token]);
  useEffect(() => {
    setIncoming(null); setFailed(false);
    player.current?.pause();
    if (!path || !token) { setReplay(null); setLoading(false); return; }
    setLoading(true);
    const controller = new AbortController();
    const next = (url: string) => setIncoming({ url, video: Boolean(event.evidence_video_url), timestamp: event.start_seconds, label: event.label });
    const cached = urls.current.get(path);
    if (cached) { next(cached); return; }
    void fetch((process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000") + path, { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error(); return response.blob(); })
      .then(blob => { if (!controller.signal.aborted) { const url = URL.createObjectURL(blob); urls.current.set(path, url); next(url); } })
      .catch(() => { if (!controller.signal.aborted) { setFailed(true); setLoading(false); } });
    return () => controller.abort();
  }, [path, token, event.evidence_video_url, event.start_seconds, event.label]);
  const ready = () => { if (incoming) { setReplay(incoming); setIncoming(null); setLoading(false); } };
  const mediaFailed = () => { setIncoming(null); setLoading(false); setFailed(true); };
  return <article className="practice-gesture-card">
    <div className="practice-gesture-evidence"><p className="practice-eyebrow">Replay the moment · {time(event.start_seconds)}</p>
    <div className="practice-gesture-media" aria-busy={loading}>{[replay, incoming].filter((item): item is Replay => item !== null).map((item, index) => {
      const pending = index === (replay ? 1 : 0) && incoming !== null;
      return <div key={`${item.url}-${pending && replay?.url === item.url ? "reload" : "media"}`} className={`practice-gesture-layer${pending ? " practice-gesture-preload" : ""}`} aria-hidden={pending}>{item.video
        ? <video ref={pending ? undefined : player} src={item.url} controls={!pending && !loading && !failed} playsInline preload="auto" onLoadedData={pending ? ready : undefined} onError={pending ? mediaFailed : undefined} tabIndex={pending ? -1 : 0} aria-label={`Review gesture at ${time(item.timestamp)}`} />
        : <img src={item.url} alt={pending ? "" : `Detected ${item.label.toLowerCase()} at ${time(item.timestamp)}`} onLoad={pending ? ready : undefined} onError={pending ? mediaFailed : undefined} />}</div>;
    })}
      {(loading || failed || !path) && <p className="practice-gesture-load-status" role="status">{failed ? "The selected replay could not be loaded. Refresh to try again." : path ? "Loading selected replay…" : "This older report has no saved replay for this moment."}</p>}
    </div>
      <p className="practice-gesture-caption">{event.evidence_video_url ? "Silent replay with the surrounding context." : "A captured moment from your recording."}</p>
      {events.length > 1 && <div className="practice-gesture-moments"><p className="practice-eyebrow">Other moments to review</p>
        <div className="practice-intervals" aria-label={`Choose a ${event.label.toLowerCase()} moment`}>{events.map((item, i) => <button key={`${item.start_seconds}-${i}`} type="button" aria-label={`Review at ${time(item.start_seconds)}`} aria-pressed={i === selected} className={i === selected ? "is-selected" : ""} onClick={() => setSelected(i)}>{time(item.start_seconds)}</button>)}</div>
      </div>}
    </div>
    <div className="practice-gesture-coaching" aria-live="polite"><p className="practice-eyebrow">{event.label}</p><h3>{coaching.title}</h3>
      <div className="practice-gesture-explanation"><h4>What happened</h4><p>{coaching.observation}</p></div>
      <div className="practice-gesture-explanation"><h4>Why it matters</h4><p>{coaching.impact}</p></div>
      <div className="practice-gesture-action"><h4>Try this next</h4><p>{coaching.action}</p></div>
    </div>
  </article>;
}

export function PracticeGestures({ events, token, tracking }: { events: Event[]; token: string | null; tracking?: PoseTracking | null }) {
  const groups = new Map<string, Event[]>();
  for (const event of events) groups.set(event.type, [...(groups.get(event.type) ?? []), event]);
  return <section className="practice-panel"><div className="practice-panel-heading"><div><p className="practice-eyebrow">On camera</p><h2>Gestures & body language</h2><p className="practice-muted">See what happened, why it may matter, and one adjustment to try. Keep deliberate movements that support your message.</p></div></div>
    {tracking?.status !== "reliable" && <div className="practice-gesture-warning" role="status">
      <strong>{!tracking ? "This older report has a limited visibility check" : tracking.status === "insufficient" ? "Your movements weren’t clear enough to review fully" : "Some movements couldn’t be reviewed clearly"}</strong>
      <p>{!tracking ? "You can review the saved moments below. Upload again for a more complete review." : tracking.person_visible_percent === 0 ? "Keep the speaker visible in the recording, with the face, arms and torso in frame." : "Keep your face, arms and torso in frame with clear lighting. No flagged moments does not mean the unclear parts were problem-free."}</p>
    </div>}
    {groups.size ? Array.from(groups, ([key, items]) => <GestureGroup key={key} events={items} token={token} />) : <p className="practice-empty">{tracking?.status === "reliable" ? "No gesture moments were flagged for review. Keep using natural movements that support your message." : "No gesture moments were saved for review. Improve the visibility of the speaker and try another recording."}</p>}
  </section>;
}
