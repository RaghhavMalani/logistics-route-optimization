/**
 * The financial twin's evidence: what can be priced, from what, and the
 * public tariffs held with the page, section and verbatim text each rate
 * was read from.
 *
 * A primitive with no rate says so. A public tariff is labelled PUBLIC_TARIFF
 * -- what the port publishes, not what any carrier pays -- and a schedule
 * outside its validity is shown as lapsed, never used. An operator's
 * assumption is named and labelled. There is no default figure anywhere on
 * this panel, and that absence is the point of it.
 */

import { Panel, Section } from "@/components/kit/layout";
import { Pill, type Tone } from "@/components/kit/primitives";
import { useFinanceBasis, useFinanceTariffs } from "@/services/decisions";

const SOURCE_TONE: Record<string, Tone> = {
  CUSTOMER_CONTRACT: "ok",
  PORT_TARIFF: "info",
  PUBLIC_TARIFF: "info",
  MARKET_DATA: "neutral",
  USER_ASSUMPTION: "unc",
};

export function FinanceBasisPanel({ scope }: { scope?: string | null }) {
  const basis = useFinanceBasis(scope);
  const tariffs = useFinanceTariffs();
  const coverage = basis.data?.coverage ?? {};
  const priced = Object.values(coverage).filter((c) => c.available).length;
  return (
    <>
      <Panel
        title="Cost basis"
        note={
          basis.data ? `${priced}/${Object.keys(coverage).length} priced` : "…"
        }
        testId="finance-basis"
        className="shrink-0 rounded-none border-x-0 border-t-0"
      >
        <Section title={scope ? `Scope ${scope}` : "Any scope"}>
          <ul className="space-y-[3px]">
            {Object.entries(coverage).map(([key, row]) => (
              <li
                key={key}
                data-testid="basis-primitive"
                data-available={row.available}
                className="flex flex-col"
              >
                <span className="flex items-center gap-1.5 text-[10px]">
                  <span className="min-w-0 flex-1 truncate text-[var(--text)]">
                    {row.label}
                  </span>
                  {row.available ? (
                    <Pill tone={SOURCE_TONE[row.sourceType ?? ""] ?? "neutral"}>
                      {row.isAssumption ? "ASSUMPTION" : row.sourceType}
                    </Pill>
                  ) : (
                    <Pill tone="neutral">unavailable</Pill>
                  )}
                </span>
                <span className="text-[10px] leading-snug text-[var(--text-3)]">
                  {row.available ? row.source : row.reason}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-[10px] leading-snug text-[var(--text-3)]">
            {basis.data?.note}
          </p>
        </Section>
      </Panel>
      <Panel
        title="Public tariffs"
        note={tariffs.data ? `${tariffs.data.schedules.length} schedules` : "…"}
        testId="finance-tariffs"
        className="shrink-0 rounded-none border-x-0 border-t-0"
      >
        {(tariffs.data?.schedules ?? []).map((schedule) => {
          const lapsed = schedule.validTo
            ? Date.parse(schedule.validTo) < Date.now()
            : false;
          return (
            <Section key={schedule.scheduleId} title={schedule.scope}>
              <p className="text-[10px] leading-snug text-[var(--text)]">
                {schedule.title}
              </p>
              <div className="mt-0.5 flex flex-wrap items-center gap-1">
                <Pill tone="info">PUBLIC_TARIFF</Pill>
                <Pill tone={lapsed ? "warn" : "ok"}>
                  {lapsed ? "lapsed" : "in force"}
                </Pill>
                <Pill tone="unc">
                  reuse {schedule.reuse.toLowerCase().replace("_", " ")}
                </Pill>
                <span className="num text-[10px] text-[var(--text-3)]">
                  {schedule.validFrom?.slice(0, 10)} →{" "}
                  {schedule.validTo?.slice(0, 10)}
                </span>
              </div>
              <a
                href={String(schedule.provenance.url)}
                target="_blank"
                rel="noreferrer"
                className="block truncate text-[10px] text-[var(--info)] hover:underline"
              >
                {String(schedule.provenance.url)}
              </a>
              <p className="num text-[10px] text-[var(--text-3)]">
                retrieved {String(schedule.provenance.retrievedAt).slice(0, 16)}
                Z · sha256 {String(schedule.provenance.sha256).slice(0, 12)}… ·{" "}
                {String(schedule.provenance.pages)} pages
              </p>
              <ul className="mt-1 space-y-1">
                {schedule.rates.slice(0, 6).map((rate, index) => (
                  <li
                    key={`${rate.primitive}-${index}`}
                    data-testid="tariff-rate"
                    className="flex flex-col"
                  >
                    <span className="num flex items-center gap-1.5 text-[10.5px] text-[var(--text)]">
                      <span className="min-w-0 flex-1 truncate">
                        {rate.label}
                      </span>
                      <span>
                        {rate.currency} {rate.value} /{" "}
                        {rate.unit.replace("_", "-")}
                      </span>
                    </span>
                    <span className="text-[10px] leading-snug text-[var(--text-3)]">
                      p.{String(rate.provenance.page)} ·{" "}
                      {String(rate.provenance.section)} · “
                      {String(rate.provenance.verbatim).slice(0, 90)}…”
                    </span>
                  </li>
                ))}
                {schedule.rates.length > 6 ? (
                  <li className="text-[10px] text-[var(--text-3)]">
                    {schedule.rates.length - 6} further rates in the schedule.
                  </li>
                ) : null}
              </ul>
              {schedule.notes.map((note) => (
                <p
                  key={note}
                  className="mt-1 text-[10px] leading-snug text-[var(--text-3)]"
                >
                  {note}
                </p>
              ))}
            </Section>
          );
        })}
        {tariffs.data?.investigated?.length ? (
          <Section title="Also investigated">
            {tariffs.data.investigated.map((row, index) => (
              <p
                key={index}
                className="text-[10px] leading-snug text-[var(--text-3)]"
              >
                <span className="text-[var(--text-2)]">
                  {String(row.authority)}
                </span>{" "}
                — {String(row.finding)}
              </p>
            ))}
          </Section>
        ) : null}
      </Panel>
    </>
  );
}
