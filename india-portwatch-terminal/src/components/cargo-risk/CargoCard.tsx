import { Box, Diamond, Snowflake } from "lucide-react";
import { money, percent, tone } from "./view-model";
import { formatUtc } from "@/components/kit/primitives";
import type { CargoDeclaration, CargoLoss } from "./types";

const driverColours = [
  "var(--chart-5)",
  "var(--chart-2)",
  "var(--chart-4)",
  "var(--text-3)",
  "var(--warn)",
];

export function Source({ children }: { children: string }) {
  return (
    <span className="cargo-source" title={children}>
      {children.split(" · ")[0].split(": ")[0]}
    </span>
  );
}

export function CargoCard({
  cargo,
  loss,
  currency,
}: {
  cargo: CargoDeclaration;
  loss: CargoLoss;
  currency: string;
}) {
  const Icon =
    cargo.handlingClass?.value === "reefer"
      ? Snowflake
      : cargo.handlingClass?.value === "DG"
        ? Diamond
        : Box;
  const drivers = Object.entries(loss.drivers)
    .filter(([, driver]) => driver.expected > 0)
    .sort(([, a], [, b]) => b.expected - a.expected);
  const driverTotal = drivers.reduce(
    (total, [, driver]) => total + driver.expected,
    0,
  );
  const insured = loss.insuredValue;
  return (
    <article className="cargo-risk-card" data-testid="cargo-risk-card">
      <header>
        <Icon size={15} aria-hidden />
        <div>
          <strong>{cargo.name}</strong>
          <small>
            {cargo.id} · {cargo.handlingClass?.value ?? "Class unknown"}
          </small>
        </div>
        <span className={"cargo-tone cargo-tone-" + tone(loss)}>
          {tone(loss) === "crit" || tone(loss) === "warn"
            ? "At risk"
            : tone(loss) === "ok"
              ? "On track"
              : "Unknown"}
        </span>
      </header>
      <dl>
        <div>
          <dt>Insured value</dt>
          <dd>
            {insured
              ? money(Number(insured.value.amount), insured.value.currency)
              : "Unknown"}{" "}
            {insured && (
              <Source>
                {insured.basis.toUpperCase() + " · " + insured.source}
              </Source>
            )}
          </dd>
        </div>
        <div>
          <dt>Deadline</dt>
          <dd>
            {cargo.deadline ? formatUtc(cargo.deadline) : "Unknown"}{" "}
            {loss.deadlineBasis && <Source>{loss.deadlineBasis}</Source>}
          </dd>
        </div>
        <div>
          <dt>Expected extra vs keep</dt>
          <dd>
            {loss.expectedExtraCost
              ? money(loss.expectedExtraCost.estimate, currency)
              : "Unknown"}{" "}
            <Source>MODELLED · paired known subtotal</Source>
          </dd>
        </div>
      </dl>
      {loss.onTime && (
        <div className="cargo-progress" data-tone={tone(loss)}>
          <span>
            On time <b>{percent(loss.onTime.estimate)}</b>{" "}
            <Source>MODELLED · sampled delivery against deadline</Source>
          </span>
          <meter
            min={0}
            max={1}
            value={loss.onTime.estimate}
            aria-label="Modelled probability of on-time delivery"
          />
        </div>
      )}
      {driverTotal > 0 && (
        <div
          className="cargo-drivers"
          role="img"
          aria-label="Expected known cost by driver"
        >
          {drivers.map(([name, driver], index) => (
            <span
              key={name}
              style={{
                width: percent(driver.expected / driverTotal),
                background: driverColours[index % driverColours.length],
              }}
              title={
                name.replaceAll("_", " ") +
                " · " +
                money(driver.expected, currency) +
                " · " +
                driver.basis.join(" / ")
              }
            />
          ))}
        </div>
      )}
      <details>
        <summary>Cost drivers and sources</summary>
        <ul>
          {drivers.map(([name, driver]) => (
            <li key={name}>
              {name.replaceAll("_", " ")} · {money(driver.expected, currency)}{" "}
              <Source>{driver.basis.join(" · ")}</Source>
            </li>
          ))}
          {Object.entries(loss.unknown).map(([name, reason]) => (
            <li key={name}>
              {name.replaceAll("_", " ")} · Unknown. {reason}
            </li>
          ))}
          {cargo.deliveryClock && <li>{cargo.deliveryClock}</li>}
        </ul>
      </details>
    </article>
  );
}
