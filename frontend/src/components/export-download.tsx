"use client";
import { useState } from "react";
import { useAuth } from "./auth/auth-provider";

export function ExportDownload({ path, filename, disabled = false, title }: { path: string; filename: string; disabled?: boolean; title?: string }) {
  const { getAccessToken } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function download() {
    setBusy(true); setError("");
    try {
      const token = await getAccessToken();
      const response = await fetch((process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000") + path, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) { const data = await response.json().catch(() => null); throw new Error(typeof data?.detail === "string" ? data.detail : "Export failed. Please retry."); }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a"); link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { setError(error instanceof Error ? error.message : "Export failed."); }
    finally { setBusy(false); }
  }
  return <div className="relative"><button type="button" onClick={() => void download()} disabled={busy || disabled} title={title} className="inline-flex min-h-[37px] items-center rounded-[10px] border border-[#18181e] bg-[#18181e] px-3 text-xs font-bold text-white disabled:opacity-50">{busy ? "Exporting…" : "⇩ Export"}</button>{error && <p role="alert" className="absolute right-0 top-full z-50 mt-2 w-64 rounded-lg border border-red-200 bg-white p-3 text-xs text-red-700 shadow-lg">{error}</p>}</div>;
}
