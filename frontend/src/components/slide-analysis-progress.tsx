import Link from "next/link";
import type { ReactNode } from "react";
import { Brand } from "@/components/brand";
import { processingMessage } from "@/lib/processing-message";

const stages = [
  { title: "Read your slides", detail: "Preparing slide content and previews.", start: 0 },
  { title: "Review the visuals", detail: "Checking the visual content across your deck.", start: 25 },
  { title: "Build your feedback", detail: "Assessing clarity, structure, and opportunities to improve.", start: 65 },
  { title: "Save your results", detail: "Putting your slide feedback and deck summary together.", start: 95 },
];

export function SlideAnalysisProgress({ progress, filename, failed, error }: {
  progress: number; filename?: string; failed: boolean; error?: string | null;
}) {
  const current = stages.reduce((active, stage, index) => progress >= stage.start ? index : active, 0);
  return (
    <main className="flex h-dvh items-center justify-center overflow-hidden bg-[#f7f7fb] p-6 text-[#242331]">
      <section className="w-full max-w-xl rounded-3xl border border-[#e7e4ef] bg-white p-7 shadow-[0_24px_80px_-40px_#51477540] sm:p-10" aria-busy={!failed}>
        <div className="mb-8 flex items-center gap-3">
          <Brand />
          {!failed && <span className="ml-auto flex items-center gap-2 text-xs font-medium text-[#777186]"><span className="h-1.5 w-1.5 rounded-full bg-[#7861ff] motion-safe:animate-pulse"/>In progress</span>}
        </div>
        <div role="status" aria-live="polite" aria-atomic="true">
          <h1 className="text-2xl font-semibold tracking-[-0.04em] sm:text-3xl">{failed ? "Analysis couldn’t finish" : stages[current].title}</h1>
          <p className="mt-3 text-sm leading-6 text-[#777186]">{failed ? processingMessage(error, "We couldn’t finish reviewing this deck. Please try again from your workspace.") : stages[current].detail}</p>
        </div>
        {filename && <p className="mt-5 truncate rounded-lg bg-[#f8f7fb] px-3 py-2 text-xs font-medium text-[#686174]" title={filename}>{filename}</p>}
        {!failed ? <>
          <ol className="mt-8 space-y-5">
            {stages.map((stage, index) => <li key={stage.title} className={`flex items-center gap-3 text-sm ${index > current ? "text-[#a7a2b1]" : "text-[#4c425f]"}`}>
              <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs ${index < current ? "bg-[#eeebff] text-[#725be6]" : index === current ? "bg-[#7861ff] text-white shadow-[0_0_0_4px_#f1eeff]" : "border border-[#e9e6ef]"}`}>
                {index < current ? "✓" : index === current ? <span className="h-3 w-3 rounded-full border-2 border-white/40 border-t-white motion-safe:animate-spin"/> : index + 1}
              </span>
              <span className={index === current ? "font-semibold" : ""}>{stage.title}</span>
              {index === current && <span className="ml-auto text-[11px] text-[#8b7bac]">Working</span>}
            </li>)}
          </ol>
          <p className="mt-8 border-t border-[#efedf4] pt-5 text-xs leading-5 text-[#96909f]">Your results will open automatically. Larger decks can take a few minutes.</p>
        </> : <Link href="/home" className="mt-6 inline-flex rounded-xl bg-[#242331] px-4 py-3 text-sm font-semibold text-white">Back to home</Link>}
      </section>
    </main>
  );
}

export function SlideAnalysisState({ title, description, filename, action }: {
  title: string;
  description: string;
  filename?: string;
  action: ReactNode;
}) {
  return (
    <main className="flex h-dvh items-center justify-center overflow-hidden bg-[#f7f7fb] p-6 text-[#242331]">
      <section className="w-full max-w-xl rounded-3xl border border-[#e7e4ef] bg-white p-7 shadow-[0_24px_80px_-40px_#51477540] sm:p-10">
        <div className="mb-8"><Brand /></div>
        <p className="text-xs font-bold uppercase tracking-[0.12em] text-[#7861f4]">Slide Analyzer</p>
        <h1 className="mt-3 text-2xl font-semibold tracking-[-0.04em] sm:text-3xl">{title}</h1>
        <p className="mt-3 max-w-md text-sm leading-6 text-[#777186]">{description}</p>
        {filename && <p className="mt-5 truncate rounded-lg bg-[#f8f7fb] px-3 py-2 text-xs font-medium text-[#686174]" title={filename}>{filename}</p>}
        <div className="mt-7 flex items-center gap-3">{action}</div>
      </section>
    </main>
  );
}
