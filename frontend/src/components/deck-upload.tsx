"use client";
import Link from "next/link";
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
  return <main className="min-h-dvh bg-[#f8f8fb] text-[#242132]">
    <nav className="flex items-center justify-between border-b border-[#e8e6ee] bg-white px-8 py-5"><Brand /><Link href="/home" className="text-sm text-[#797383]">← Workspace</Link></nav>
    <section className="mx-auto max-w-2xl px-6 py-16"><p className="text-xs font-semibold uppercase tracking-widest text-[#7660df]">{mode === "slide" ? "Slide Analyzer" : "Transcript Enhancer"}</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">{mode === "slide" ? "Give your slides a second look." : "Find the words for your slides."}</h1>
      <p className="mt-4 text-sm leading-6 text-[#797383]">{mode === "slide" ? "Upload your deck for slide feedback, visual review, and a presentation summary." : "Upload your deck to write or generate an editable presenter script. Slide analysis is not required."}</p>
      <div className="mt-8 rounded-2xl border border-dashed border-[#cdc5df] bg-white p-10 text-center"><h2 className="font-semibold">Choose your presentation</h2><p className="mt-2 text-xs text-[#797383]">PowerPoint · .pptx · up to 30 MB</p>
        <input ref={input} type="file" accept=".pptx" className="hidden" onChange={e => { const file = e.target.files?.[0]; if (file) void upload(file); }} />
        <button type="button" disabled={busy} onClick={() => input.current?.click()} className="mt-6 rounded-xl bg-[#242132] px-6 py-3 text-sm font-semibold text-white disabled:opacity-60">{busy ? "Uploading presentation…" : "Choose PowerPoint"}</button>
        {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}
      </div><p className="mt-5 text-xs text-[#797383]">Existing decks are available in your workspace’s Recent work.</p>
    </section></main>;
}
