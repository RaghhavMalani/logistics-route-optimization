/**
 * Map layer control and legend.
 *
 * The weather selector is the important part. Only fields the artefacts
 * actually carry are selectable; a field the feed did not produce (significant
 * wave height, in most runs) is listed as unavailable rather than silently
 * dropped, so the operator can tell "calm" from "not measured".
 */

import { useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";
import type { LayerKey } from "./basemap";
import { WEATHER_FIELDS, type FieldSpec, type WeatherField } from "./layers";

export interface LayerToggle {
  key: LayerKey;
  label: string;
  count?: number | null;
  disabled?: boolean;
  disabledReason?: string;
}

function Check({ on, disabled }: { on: boolean; disabled?: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        "grid h-[13px] w-[13px] shrink-0 place-items-center rounded-[2px] border",
        disabled
          ? "border-[var(--line)] bg-transparent"
          : on
            ? "border-[var(--info)] bg-[var(--info)]"
            : "border-[var(--line-strong)] bg-transparent",
      )}
    >
      {on && !disabled ? (
        <svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="#04121b" strokeWidth="2.2">
          <path d="M2.5 6.2l2.4 2.4L9.5 3.8" />
        </svg>
      ) : null}
    </span>
  );
}

export function MapControlPanel({
  toggles,
  visible,
  onToggle,
  weatherField,
  onWeatherField,
  weatherAvailability,
  footer,
}: {
  toggles: LayerToggle[];
  visible: Partial<Record<LayerKey, boolean>>;
  onToggle: (key: LayerKey) => void;
  weatherField?: WeatherField;
  onWeatherField?: (field: WeatherField) => void;
  /** Per-field station coverage; 0 means the feed carried no readings. */
  weatherAvailability?: Partial<Record<WeatherField, number>>;
  footer?: ReactNode;
}) {
  const [open, setOpen] = useState(true);
  const weatherOn = visible.weather ?? false;

  return (
    <div className="absolute left-2.5 top-2.5 z-20 w-[186px] overflow-hidden rounded-[3px] border border-[var(--line-strong)] bg-[var(--panel)]/95 backdrop-blur-[2px]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex h-[26px] w-full items-center justify-between border-b border-[var(--line)] bg-[var(--panel-2)] px-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--text-2)]"
      >
        Layers
        <svg
          width="9"
          height="9"
          viewBox="0 0 10 10"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          className={cn("transition-transform", open ? "" : "-rotate-90")}
          aria-hidden
        >
          <path d="M2 4l3 3 3-3" />
        </svg>
      </button>

      {open ? (
        <div className="p-1.5">
          {toggles.map((toggle) => {
            const on = (visible[toggle.key] ?? false) && !toggle.disabled;
            return (
              <button
                key={toggle.key}
                type="button"
                disabled={toggle.disabled}
                title={toggle.disabled ? toggle.disabledReason : undefined}
                onClick={() => onToggle(toggle.key)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-[2px] px-1.5 py-[3px] text-left text-[11.5px]",
                  toggle.disabled
                    ? "cursor-not-allowed text-[var(--text-3)]/60"
                    : on
                      ? "text-[var(--text)] hover:bg-[var(--panel-3)]"
                      : "text-[var(--text-3)] hover:bg-[var(--panel-3)]",
                )}
              >
                <Check on={on} disabled={toggle.disabled} />
                <span className="min-w-0 flex-1 truncate">{toggle.label}</span>
                {toggle.count != null ? (
                  <span className="num text-[10px] text-[var(--text-3)]">{toggle.count}</span>
                ) : null}
              </button>
            );
          })}

          {weatherField && onWeatherField ? (
            <div
              className={cn(
                "mt-1.5 border-t border-[var(--line)] pt-1.5 transition-opacity",
                weatherOn ? "opacity-100" : "opacity-45",
              )}
            >
              <div className="eyebrow mb-1 px-1.5 text-[9px]">Weather field</div>
              <div className="grid grid-cols-2 gap-[3px] px-1">
                {(Object.values(WEATHER_FIELDS) as FieldSpec[]).map((spec) => {
                  const coverage = weatherAvailability?.[spec.key] ?? 0;
                  const unavailable = coverage === 0;
                  const active = weatherField === spec.key;
                  return (
                    <button
                      key={spec.key}
                      type="button"
                      disabled={unavailable || !weatherOn}
                      title={
                        unavailable
                          ? `${spec.label} is not carried by this weather artefact`
                          : `${spec.label} — ${coverage} stations`
                      }
                      onClick={() => onWeatherField(spec.key)}
                      className={cn(
                        "truncate rounded-[2px] border px-1 py-[2px] text-[10px]",
                        unavailable
                          ? "cursor-not-allowed border-[var(--line)] text-[var(--text-3)]/50 line-through"
                          : active
                            ? "border-[var(--info)] bg-[var(--info-dim)] text-[var(--info)]"
                            : "border-[var(--line-strong)] text-[var(--text-3)] hover:text-[var(--text-2)]",
                      )}
                    >
                      {spec.label}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}

          {footer ? (
            <div className="mt-1.5 border-t border-[var(--line)] px-1.5 pt-1.5 text-[10px] leading-snug text-[var(--text-3)]">
              {footer}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/* --------------------------------------------------------------- legend -- */

export function MapLegend({
  weatherField,
  weatherActive,
  extra,
  note,
}: {
  weatherField?: WeatherField;
  weatherActive?: boolean;
  extra?: Array<{ label: string; color: string; shape?: "dot" | "ring" | "line" }>;
  note?: string;
}) {
  const spec = weatherField ? WEATHER_FIELDS[weatherField] : null;
  return (
    <div className="absolute bottom-2.5 left-2.5 z-20 flex max-w-[calc(100%-24px)] flex-col gap-1.5 rounded-[3px] border border-[var(--line-strong)] bg-[var(--panel)]/95 px-2.5 py-2 backdrop-blur-[2px]">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {[
          { label: "Severe", color: "#d05a4c" },
          { label: "Congested", color: "#d3a02f" },
          { label: "Normal", color: "#56b28d" },
        ].map((item) => (
          <span key={item.label} className="flex items-center gap-1.5 text-[10px] text-[var(--text-3)]">
            <span
              className="h-[7px] w-[7px] rounded-full border"
              style={{ borderColor: item.color, background: `${item.color}33` }}
            />
            {item.label}
          </span>
        ))}
        {extra?.map((item) => (
          <span key={item.label} className="flex items-center gap-1.5 text-[10px] text-[var(--text-3)]">
            {item.shape === "line" ? (
              <span className="h-[2px] w-4" style={{ background: item.color }} />
            ) : item.shape === "ring" ? (
              <span
                className="h-[7px] w-[7px] rounded-full border"
                style={{ borderColor: item.color }}
              />
            ) : (
              <span className="h-[7px] w-[7px] rounded-[1px]" style={{ background: item.color }} />
            )}
            {item.label}
          </span>
        ))}
      </div>

      {spec && weatherActive ? (
        <div className="border-t border-[var(--line)] pt-1.5">
          <div className="mb-1 flex items-baseline gap-2">
            <span className="eyebrow text-[9px]">{spec.label}</span>
            <span className="num text-[9.5px] text-[var(--text-3)]">{spec.unit}</span>
          </div>
          <div className="flex items-center gap-[1px]">
            {spec.colors.map((color, index) => (
              <span key={color} className="flex flex-col items-center">
                <span
                  className="block h-[8px] w-[26px]"
                  style={{ background: color, opacity: 0.28 + index * 0.11 }}
                />
                <span className="num mt-[2px] text-[8.5px] text-[var(--text-3)]">
                  {spec.bands[index] >= 1
                    ? spec.bands[index].toFixed(0)
                    : spec.bands[index].toFixed(2)}
                </span>
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {note ? (
        <div className="max-w-[430px] border-t border-[var(--line)] pt-1.5 text-[9.5px] leading-snug text-[var(--text-3)]">
          {note}
        </div>
      ) : null}
    </div>
  );
}
