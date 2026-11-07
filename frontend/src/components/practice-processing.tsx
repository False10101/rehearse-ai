export type ReviewTrack = {
  status: "queued" | "running" | "completed" | "skipped";
  label: string;
  progress_percent: number;
};

export function PracticeProcessing({ tracks }: {
  tracks?: Partial<Record<"gestures" | "speech", ReviewTrack>> | null;
}) {
  return <div className="my-6 grid gap-3 text-left sm:grid-cols-2">
    {([['gestures', 'Body language'], ['speech', 'Speech delivery']] as const).map(([key, title]) => {
      const track = tracks?.[key];
      const done = track?.status === "completed" || track?.status === "skipped";
      const percent = track?.progress_percent ?? 0;
      return <section key={key} className="rounded-xl border border-[#e6e0f2] bg-[#faf8ff] p-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="m-0 text-sm font-bold text-[#393046]">{title}</h3>
          <span className="text-xs font-medium text-[#75618f]">{done ? "Complete" : track?.status === "running" ? "In progress" : "Preparing"}</span>
        </div>
        <p className="mb-3 mt-2 text-xs leading-relaxed text-[#746a80]">{track?.label ?? "Preparing review"}</p>
        <div className="h-1.5 overflow-hidden rounded-full bg-[#e9e2f4]" role="progressbar" aria-label={title} aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full rounded-full bg-[#8061df] transition-[width] duration-300" style={{ width: `${percent}%` }} />
        </div>
      </section>;
    })}
  </div>;
}
