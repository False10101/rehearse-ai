"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export function LiveRecalibrationHelp() {
  const id = useId();
  const button = useRef<HTMLButtonElement>(null);
  const tooltip = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ left: 0, top: 0 });

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const anchor = button.current?.getBoundingClientRect();
      if (!anchor) return;
      const width = tooltip.current?.offsetWidth ?? 272;
      const height = tooltip.current?.offsetHeight ?? 100;
      setPosition({
        left: Math.max(12, Math.min(anchor.left + anchor.width / 2 - width / 2, window.innerWidth - width - 12)),
        top: anchor.top >= height + 20 ? anchor.top - height - 10 : anchor.bottom + 10,
      });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!button.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  return <>
    <button
      ref={button}
      type="button"
      aria-label="About recalibration"
      aria-describedby={open ? id : undefined}
      className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-[#81788f] hover:bg-[#f2effa] hover:text-[#6550cf] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#8e7cf4]"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => { if (document.activeElement !== button.current) setOpen(false); }}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onClick={() => setOpen(true)}
    ><span aria-hidden="true" className="grid h-[18px] w-[18px] place-items-center rounded-full border border-current text-[0.6875rem] font-semibold">?</span></button>
    {open && createPortal(<div ref={tooltip} id={id} role="tooltip" style={position} className="pointer-events-none fixed z-[120] w-[272px] max-w-[calc(100vw-24px)] rounded-xl border border-[#e6e1ef] bg-white px-4 py-3 font-sans shadow-[0_6px_24px_rgba(31,22,51,0.16)]">
      <p className="m-0 text-xs font-semibold text-[#514561]">When to recalibrate</p>
      <p className="mb-0 mt-1.5 text-xs leading-5 text-[#83768f]">Moved your camera or chair? Look at the camera and recalibrate to reset your normal starting position. Your session history stays.</p>
    </div>, document.body)}
  </>;
}
