"use client";

import { useEffect, useRef, useState } from "react";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
type NodeBase = { x: number; y: number; color: string };
type SceneNode = NodeBase & (
  | { kind: "rect"; w: number; h: number; radius: number; stroke: string | null; rotation: number }
  | { kind: "circle"; w: number; h: number }
  | { kind: "line"; x2: number; y2: number; weight: number }
  | { kind: "text"; w: number; h: number; size: number; bold: boolean; align: string; serif: boolean; lines: string[] }
);
type Template = { id: string; name: string; nodes: SceneNode[] };
type Catalog = { width: number; height: number; themes: Record<string, Record<string, string>>; templates: Template[] };
const focus = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 focus-visible:ring-offset-2";

function AgendaPreview({ template, palette, label }: { template: Template; palette: Record<string, string>; label: string }) {
  const color = (token: string) => `#${palette[token] ?? "253047"}`;
  return (
    <svg className="block aspect-video h-auto w-full bg-white" viewBox="0 0 1280 720" role="img" aria-label={label}>
      {template.nodes.map((node, index) => {
        if (node.kind === "line") return <line key={index} x1={node.x} y1={node.y} x2={node.x2} y2={node.y2} stroke={color(node.color)} strokeWidth={node.weight} />;
        if (node.kind === "circle") return <ellipse key={index} cx={node.x + node.w / 2} cy={node.y + node.h / 2} rx={node.w / 2} ry={node.h / 2} fill="none" stroke={color(node.color)} strokeWidth={2.5} />;
        if (node.kind === "rect") return <rect key={index} x={node.x} y={node.y} width={node.w} height={node.h} rx={node.radius} fill={color(node.color)} stroke={node.stroke ? color(node.stroke) : undefined} strokeWidth={1.5} transform={node.rotation ? `rotate(${node.rotation} ${node.x + node.w / 2} ${node.y + node.h / 2})` : undefined} />;
        return <text key={index} fill={color(node.color)} fontFamily={node.serif ? "Georgia, 'Liberation Serif', serif" : "Arial, 'Liberation Sans', sans-serif"} fontSize={node.size} fontWeight={node.bold ? 700 : 400} textAnchor={node.align === "center" ? "middle" : "start"}>
          {node.lines.map((line, lineIndex) => <tspan key={lineIndex} x={node.x + (node.align === "center" ? node.w / 2 : 0)} y={node.y + node.size * .94 + lineIndex * node.size * 1.2}>{line}</tspan>)}
        </text>;
      })}
    </svg>
  );
}

export function AgendaLaunch({ presentationId, accessToken }: { presentationId: string; accessToken: string | null }) {
  const [open, setOpen] = useState(false);
  const [layout, setLayout] = useState("paired-sections");
  const [theme, setTheme] = useState("violet");
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const launchRef = useRef<HTMLButtonElement>(null);
  const requestInFlight = useRef(false);

  useEffect(() => {
    if (!open || !accessToken || catalog) return;
    const controller = new AbortController();
    setLoading(true);
    setLoadError(null);
    async function load() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/presentations/agenda/templates`, {
          headers: { Authorization: `Bearer ${accessToken}` }, signal: controller.signal,
        });
        if (!response.ok) throw new Error("The agenda styles couldn’t be loaded.");
        const value: Catalog = await response.json();
        if (value.templates?.length !== 5 || !value.themes?.violet) throw new Error("The agenda styles couldn’t be loaded.");
        if (!controller.signal.aborted) setCatalog(value);
      } catch {
        if (!controller.signal.aborted) setLoadError("The agenda styles couldn’t be loaded. Please try again.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [open, accessToken, catalog, retry]);

  useEffect(() => {
    if (!open) return;
    const trigger = launchRef.current;
    dialogRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
      trigger?.focus();
    };
  }, [open]);

  async function create() {
    if (!accessToken || !catalog || requestInFlight.current) return;
    requestInFlight.current = true;
    setCreating(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/presentations/${presentationId}/agenda`, {
        method: "POST", headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({ layout, theme }),
      });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok || typeof payload !== "object" || payload === null || !("inserted_slide_number" in payload) || typeof payload.inserted_slide_number !== "number") {
        throw new Error(typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string" ? payload.detail : "The agenda could not be created. Please try again.");
      }
      setOpen(false);
      window.dispatchEvent(new CustomEvent<number>("rehearse:agenda-created", { detail: payload.inserted_slide_number }));
    } catch (creationError) {
      setError(creationError instanceof Error ? creationError.message : "The agenda could not be created.");
    } finally {
      requestInFlight.current = false;
      setCreating(false);
    }
  }

  const selected = catalog?.templates.find((item) => item.id === layout);
  const palette = catalog?.themes[theme];
  return <>
    <button ref={launchRef} className={`w-full rounded-lg border border-[#f2d2ad] bg-[#fffaf2] px-3 py-2 text-[0.72rem] font-extrabold text-[#a86410] ${focus}`} onClick={() => { setError(null); setOpen(true); }} type="button">✦ Create agenda</button>
    {open ? <div className="fixed inset-0 z-50 grid place-items-center bg-[#171724]/45 p-3 backdrop-blur-sm sm:p-6">
      <div ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="agenda-title" aria-describedby="agenda-description" className="flex max-h-[92dvh] w-full max-w-[72rem] flex-col overflow-hidden rounded-2xl bg-white text-[#282336] shadow-2xl outline-none" onKeyDown={(event) => {
        if (event.key === "Escape" && !creating) { event.stopPropagation(); setOpen(false); }
        if (event.key !== "Tab") return;
        const elements = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), [tabindex="0"]') ?? []);
        const first = elements[0], last = elements.at(-1);
        if (!first) { event.preventDefault(); return; }
        if (event.shiftKey && (document.activeElement === first || document.activeElement === dialogRef.current)) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialogRef.current)) { event.preventDefault(); first.focus(); }
      }}>
        <header className="flex flex-none items-start justify-between gap-5 border-b border-[#ebe7f0] px-6 py-5">
          <div><h2 className="m-0 text-xl font-semibold tracking-tight" id="agenda-title">An agenda that fits your presentation</h2><p className="mb-0 mt-2 text-sm text-[#83788e]" id="agenda-description">Choose a layout and palette. We’ll write the sections from your deck and add the slide in the right place.</p></div>
          <button className={`rounded-lg px-2 text-2xl text-[#887c96] disabled:opacity-30 ${focus}`} aria-label="Close agenda builder" disabled={creating} onClick={() => setOpen(false)} type="button">×</button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {!catalog ? <div className="grid min-h-80 place-items-center px-6 text-center" role="status"><div><p className="text-sm text-[#82748e]">{loadError ?? (loading ? "Loading agenda styles…" : "Preparing agenda styles…")}</p>{loadError ? <button className={`rounded-lg border px-4 py-2 text-sm ${focus}`} onClick={() => setRetry((value) => value + 1)} type="button">Try again</button> : null}</div></div> : <div className="grid md:grid-cols-[15rem_minmax(0,1fr)]">
            <aside className="border-b border-[#ebe7f0] bg-[#faf9fc] p-5 md:border-b-0 md:border-r" aria-label="Agenda layouts">
              <p className="mb-4 mt-0 text-xs font-semibold uppercase tracking-wider text-[#8e809c]">Choose a layout</p>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-1">
                {catalog.templates.map((item, index) => <button className={`overflow-hidden rounded-xl border bg-white p-1.5 text-left transition disabled:opacity-60 ${layout === item.id ? "border-[#9b7be3] ring-1 ring-[#9b7be3]" : "border-[#e3ddea] hover:border-[#b8a2d8]"} ${focus}`} key={item.id} aria-pressed={layout === item.id} disabled={creating} onClick={() => setLayout(item.id)} type="button">
                  <div className="overflow-hidden rounded-md border border-[#f0edf4]"><AgendaPreview template={item} palette={palette ?? catalog.themes.violet} label={item.name} /></div>
                  <span className="flex items-center gap-2 px-1 pb-1 pt-2 text-xs font-medium text-[#70607f]"><span className="text-[10px] text-[#a596b1]">0{index + 1}</span>{item.name}{layout === item.id ? <span className="ml-auto text-[#8761cd]" aria-hidden="true">✓</span> : null}</span>
                </button>)}
              </div>
            </aside>
            <div className="flex min-w-0 flex-col justify-center p-5 sm:p-7">
              <div className="mb-4 flex items-center justify-between"><h3 className="m-0 text-sm font-semibold">{selected?.name}</h3><span className="text-xs text-[#93849f]">Example content · up to 6 sections</span></div>
              <div className="overflow-hidden rounded-xl border border-[#e5dfea] shadow-[0_12px_35px_rgba(48,32,70,0.06)]">{selected && palette ? <AgendaPreview template={selected} palette={palette} label={`${selected.name} in ${theme}`} /> : null}</div>
              <fieldset className="m-0 mt-7 min-w-0 border-0 p-0" disabled={creating}>
                <legend className="mb-3 text-xs font-semibold text-[#81718f]">Color palette</legend>
                <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
                  {Object.entries(catalog.themes).map(([name, colors]) => <button className={`rounded-lg border p-2 transition ${theme === name ? "border-[#a083d2] bg-[#f7f3fc]" : "border-[#e8e1ee] bg-white hover:border-[#c1afda]"} ${focus}`} key={name} onClick={() => setTheme(name)} type="button" aria-pressed={theme === name}>
                    <span className="flex overflow-hidden rounded-sm" aria-hidden="true">{[0, 1, 2, 3, 4, 5].map((i) => <span className="h-3 flex-1" key={i} style={{ backgroundColor: `#${colors[`accent${i}`]}` }} />)}</span>
                    <span className="mt-2 block text-[11px] capitalize text-[#80708d]">{name}</span>
                  </button>)}
                </div>
              </fieldset>
              <p className="mb-0 mt-5 text-xs leading-5 text-[#95859f]">The preview shows the layout and colors. Your agenda will use titles and short descriptions from your own presentation.</p>
            </div>
          </div>}
        </div>
        <footer className="flex flex-none flex-wrap items-center justify-between gap-3 border-t border-[#ebe7f0] bg-white px-6 py-4">
          <div className="min-w-0 flex-1 text-xs leading-5" aria-live="polite">{error ? <p className="m-0 text-[#b7445d]" role="alert">{error}</p> : <p className="m-0 text-[#93829f]">{creating ? "Writing your agenda and updating slide previews. This may take a moment." : "Added directly to your deck. All slide content stays editable in PowerPoint."}</p>}</div>
          <button className={`inline-flex items-center gap-2 rounded-xl bg-[#7960d7] px-5 py-3 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-60 ${focus}`} disabled={creating || !accessToken || !catalog} onClick={() => void create()} type="button">{creating ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" aria-hidden="true" /> : null}{creating ? "Creating agenda…" : error ? "Try again" : "Add agenda to deck"}</button>
        </footer>
      </div>
    </div> : null}
  </>;
}
