"use client";
import Link from "next/link";
import "./deck-upload.css";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { useAuth } from "./auth/auth-provider";
import { Brand } from "./brand";

export function DeckUpload({ mode }: { mode: "slide" | "transcript" }) {
  const { getAccessToken } = useAuth();
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function upload(file: File) {
    if (!file.name.toLowerCase().endsWith(".pptx") || file.size > 30 * 1024 * 1024) { setError("Choose a PowerPoint (.pptx) file up to 30 MB."); return; }
    setBusy(true); setError("");
    try {
      const token = await getAccessToken();
      const body = new FormData(); body.append("file", file);
      const response = await fetch((process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000") + "/api/v1/presentations" + (mode === "transcript" ? "/transcript" : ""), { method: "POST", headers: { Authorization: `Bearer ${token}` }, body });
      const data = await response.json();
      if (!response.ok || typeof data.id !== "string") throw new Error(typeof data.detail === "string" ? data.detail : "Upload failed. Please try again.");
      router.push(`/${mode}?presentation=${data.id}`);
    } catch (error) { setError(error instanceof Error ? error.message : "Upload failed."); setBusy(false); }
    finally { if (input.current) input.current.value = ""; }
  }
  return <main className="deck-upload">
    <nav className="deck-upload-nav"><Link href="/home" aria-label="Rehearse AI home"><Brand /></Link><Link href="/home">← Workspace</Link></nav>
    <div className="deck-upload-content">
      <header><p className="deck-upload-kicker">{mode === "slide" ? "Slide Analyzer" : "Transcript Enhancer"}</p><h1>{mode === "slide" ? "A clearer deck starts here." : "Find the words for your slides."}</h1><p>{mode === "slide" ? "Review your content and visual design, with practical feedback for every slide." : "Turn your slides into a spoken script, or bring your own words and refine them."}</p></header>
      <div className="deck-upload-grid">
        <section className="deck-upload-picker" aria-busy={busy}>
          <span className="deck-upload-symbol" aria-hidden="true"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="1.6"><rect x="7" y="7" width="34" height="25" rx="3"/><path d="M24 32v9m-8 0h16M15 16h18M15 22h11"/></svg></span>
          <h2>Choose your presentation</h2><p>Upload a PowerPoint deck to get started.</p>
          <input ref={input} type="file" accept=".pptx" aria-label="Choose a PowerPoint presentation" className="hidden" onChange={e => { const file = e.target.files?.[0]; if (file) void upload(file); }} />
          <button type="button" disabled={busy} onClick={() => input.current?.click()}>{busy ? "Uploading presentation…" : "Choose PowerPoint"}<span aria-hidden="true">↑</span></button>
          <small>PowerPoint (.pptx) · Up to 30 MB</small>
          {error && <p role="alert" className="deck-upload-error">{error}</p>}
        </section>
        <aside className="deck-upload-guide"><h2>What you’ll get</h2>{(mode === "slide" ? [
          ["01", "Feedback for each slide", "Find unclear wording, dense content, and opportunities to sharpen your message."],
          ["02", "A visual design review", "Review readability, contrast, layout, and consistency across your deck."],
          ["03", "A plan for your next edit", "See improvement priorities alongside your slides, plus a summary of the deck."],
        ] : [
          ["01", "A script for your audience", "Generate scripts for one slide or a selected range, with your choice of tone, style, audience, and length."],
          ["02", "Room for your own voice", "Write and edit directly, or select a passage to enhance. Compare the suggestion before accepting it."],
          ["03", "Your work, kept together", "Return to earlier script versions and export your saved presentation script."],
        ]).map(([number, title, description]) => <div key={number}><span>{number}</span><section><h3>{title}</h3><p>{description}</p></section></div>)}</aside>
      </div>
      <footer>Returning to a deck? <Link href="/home">Find it in your workspace →</Link></footer>
    </div>
  </main>;
}
