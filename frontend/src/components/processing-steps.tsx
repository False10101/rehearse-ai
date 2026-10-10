export function ProcessingSteps({ steps, current }: { steps: string[]; current: number }) {
  return <ol className="my-6 space-y-4 text-left">{steps.map((step, i) => <li key={step} aria-current={i === current ? "step" : undefined} className={`flex items-center gap-3 text-sm ${i > current ? "text-[#a7a2b1]" : "text-[#4c425f]"}`}>
    <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs ${i === current ? "bg-[#7861ff] text-white" : "bg-[#eeebff] text-[#725be6]"}`}>{i < current ? "✓" : i + 1}</span>
    {step}{i === current && <span className="ml-auto text-xs text-[#7660df]">In progress</span>}
  </li>)}</ol>;
}
