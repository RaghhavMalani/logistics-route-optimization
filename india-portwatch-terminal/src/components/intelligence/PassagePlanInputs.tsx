import { Button } from "@/components/ui/button";
import type {
  DeclaredPassagePlan,
  PassageConsumption,
  PassageRate,
} from "@/services/current-inputs";

const FIELD =
  "min-w-0 rounded border border-[var(--line)] bg-[var(--panel-2)] px-1.5 py-1 text-[var(--text)]";

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | undefined;
  onChange: (value: number | undefined) => void;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      {label}
      <input
        className={FIELD}
        aria-label={label}
        type="number"
        step="any"
        value={value != null && Number.isFinite(value) ? value : ""}
        onChange={(e) =>
          onChange(e.target.value === "" ? undefined : Number(e.target.value))
        }
      />
    </label>
  );
}

function TextField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string | undefined;
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      {label}
      <input
        className={FIELD}
        aria-label={label}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

/** Explicit declarations only. This form never derives observed position or operational rates. */
export function PassagePlanInputs({
  value,
  onChange,
  voyageEta,
  requestedArrival,
}: {
  value: DeclaredPassagePlan | null;
  onChange: (value: DeclaredPassagePlan | null) => void;
  voyageEta: string | null;
  requestedArrival: string;
}) {
  const patch = (change: Partial<DeclaredPassagePlan>) => {
    if (value) onChange({ ...value, ...change });
  };
  const patchFinance = (
    change: Partial<NonNullable<DeclaredPassagePlan["finance"]>>,
  ) => {
    if (value) patch({ finance: { ...value.finance, ...change } });
  };
  const patchConsumption = (change: Partial<PassageConsumption>) => {
    if (value?.finance?.consumption)
      patchFinance({
        consumption: { ...value.finance.consumption, ...change },
      });
  };
  const patchRate = (
    key: "fuelPrice" | "elapsedTimeRate",
    change: Partial<PassageRate>,
  ) => {
    const old = value?.finance?.[key];
    if (old) patchFinance({ [key]: { ...old, ...change } });
  };
  const initialise = () =>
    onChange({
      schemaVersion: 1,
      referenceKind: "AT_SEA",
      referenceAt: new Date().toISOString(),
      declaredAt: new Date().toISOString(),
      referenceLabel: "",
      remainingDistanceNm: Number.NaN,
      distanceBasis: "",
      baselineSpeedKn: Number.NaN,
      minSpeedKn: Number.NaN,
      maxSpeedKn: Number.NaN,
      baselineArrivalAt: voyageEta ?? undefined,
    });
  const simulatedPassage = () => {
    const now = new Date();
    const eta = Date.parse(voyageEta ?? "");
    const remainingHours = (eta - now.getTime()) / 3600000;
    if (!(remainingHours > 0)) return;
    const target =
      Math.max(eta, Date.parse(requestedArrival) || eta) + 4 * 3600000;
    const distance = remainingHours * 12;
    onChange({
      schemaVersion: 1,
      referenceKind: "AT_SEA",
      referenceAt: now.toISOString(),
      declaredAt: now.toISOString(),
      referenceLabel: "Simulated present-position declaration; no observed AIS",
      remainingDistanceNm: distance,
      distanceBasis:
        "SIMULATED operator scenario: remaining hours to the fictional voyage ETA × 12 kn. No surveyed route distance or observed position.",
      baselineSpeedKn: 12,
      minSpeedKn: 8,
      maxSpeedKn: 16,
      alternativeSpeedKn: distance / ((target - now.getTime()) / 3600000),
      baselineArrivalAt: voyageEta ?? undefined,
    });
  };
  const simulatedFinance = () => {
    if (!value) return;
    const now = new Date().toISOString();
    const validFrom = Number.isFinite(Date.parse(value.referenceAt))
      ? value.referenceAt
      : now;
    const validTo = new Date(
      Math.max(
        Date.parse(value.baselineArrivalAt ?? "") || Date.now(),
        Date.now(),
      ) +
        7 * 86400000,
    ).toISOString();
    patchFinance({
      currency: "USD",
      consumption: {
        referenceSpeedKn: 12,
        referencePropulsionTonnesPerDay: 24,
        auxiliaryTonnesPerDay: 2,
        anchorageTonnesPerDay: 2,
        departureHoldTonnesPerDay: 2,
        minSpeedKn: 8,
        maxSpeedKn: 16,
        loadCondition:
          "SIMULATED fixed load; cubic propulsion plus constant auxiliary demand",
        source:
          "Explicitly selected illustrative demo scenario, not a vessel measurement",
        declaredAt: now,
      },
      fuelPrice: {
        amount: 600,
        currency: "USD",
        per: "tonne",
        source:
          "Explicitly selected illustrative USD 600/t assumption; not a market quote",
        validFrom,
        validTo,
      },
    });
  };
  return (
    <fieldset
      className="space-y-2 border-t border-[var(--line)] pt-2"
      data-testid="passage-plan-inputs"
    >
      <legend className="font-medium">
        Optional declared passage, speed and cost
      </legend>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={value !== null}
          onChange={(e) => (e.target.checked ? initialise() : onChange(null))}
        />
        Include a declared remaining passage
      </label>
      <p>
        The default compares arrival windows only. A speed plan needs its own
        distance, reference and operating envelope. Fictional traffic is not
        observed AIS.
      </p>
      {value ? (
        <>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!voyageEta || Date.parse(voyageEta) <= Date.now()}
            onClick={simulatedPassage}
          >
            Use named simulated passage scenario
          </Button>
          <p>
            This deliberate scenario assumes 12 kn, an 8–16 kn envelope and
            distance equal to hours until the fictional ETA × 12. It targets a
            slower arrival four hours after the selected window, subject to the
            retained hourly forecast. It supplies no consumption or prices.
          </p>
          <div className="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-2">
            <label className="flex flex-col gap-1">
              Passage reference state
              <select
                className={FIELD}
                aria-label="Passage reference state"
                value={value.referenceKind}
                onChange={(e) =>
                  patch({
                    referenceKind: e.target
                      .value as DeclaredPassagePlan["referenceKind"],
                    departureDelayHours: undefined,
                    departureHoldPermitted: undefined,
                    departureHoldLocation: undefined,
                  })
                }
              >
                <option value="AT_SEA">
                  At sea — present position reference
                </option>
                <option value="NOT_DEPARTED">
                  Not departed — declared departure reference
                </option>
              </select>
            </label>
            <TextField
              label="Passage reference instant UTC (ISO 8601)"
              value={value.referenceAt}
              onChange={(referenceAt) => patch({ referenceAt })}
            />
            <TextField
              label="Position or departure reference and source"
              value={value.referenceLabel}
              onChange={(referenceLabel) => patch({ referenceLabel })}
            />
            <TextField
              label="Distance basis and simulation disclosure"
              value={value.distanceBasis}
              onChange={(distanceBasis) => patch({ distanceBasis })}
            />
            <NumberField
              label="Declared remaining distance (nm)"
              value={value.remainingDistanceNm}
              onChange={(remainingDistanceNm) =>
                patch({
                  remainingDistanceNm: remainingDistanceNm ?? Number.NaN,
                })
              }
            />
            <NumberField
              label="Baseline sailing speed (kn)"
              value={value.baselineSpeedKn}
              onChange={(baselineSpeedKn) =>
                patch({ baselineSpeedKn: baselineSpeedKn ?? Number.NaN })
              }
            />
            <NumberField
              label="Minimum permitted sailing speed (kn)"
              value={value.minSpeedKn}
              onChange={(minSpeedKn) =>
                patch({ minSpeedKn: minSpeedKn ?? Number.NaN })
              }
            />
            <NumberField
              label="Maximum permitted sailing speed (kn)"
              value={value.maxSpeedKn}
              onChange={(maxSpeedKn) =>
                patch({ maxSpeedKn: maxSpeedKn ?? Number.NaN })
              }
            />
            <NumberField
              label="Alternative sailing speed (kn; optional)"
              value={value.alternativeSpeedKn}
              onChange={(alternativeSpeedKn) => patch({ alternativeSpeedKn })}
            />
            <TextField
              label="Baseline approach ETA UTC (ISO 8601)"
              value={value.baselineArrivalAt}
              onChange={(baselineArrivalAt) =>
                patch({ baselineArrivalAt: baselineArrivalAt || undefined })
              }
            />
            <TextField
              label="Latest clear approach deadline UTC (optional ISO 8601)"
              value={value.deadlineAt}
              onChange={(deadlineAt) =>
                patch({ deadlineAt: deadlineAt || undefined })
              }
            />
          </div>
          {value.referenceKind === "NOT_DEPARTED" ? (
            <div className="space-y-2 border-l border-[var(--line)] pl-2">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={Boolean(value.departureHoldPermitted)}
                  onChange={(e) =>
                    patch({ departureHoldPermitted: e.target.checked })
                  }
                />
                Operator explicitly permits a hold at the declared departure
              </label>
              <NumberField
                label="Alternative departure delay (h; optional)"
                value={value.departureDelayHours}
                onChange={(departureDelayHours) =>
                  patch({ departureDelayHours })
                }
              />
              <TextField
                label="Permitted departure holding location"
                value={value.departureHoldLocation}
                onChange={(departureHoldLocation) =>
                  patch({ departureHoldLocation })
                }
              />
            </div>
          ) : (
            <p>
              Delay original departure: unavailable because this declaration is
              already at sea.
            </p>
          )}
          <details className="space-y-2">
            <summary>Declare consumption and relevant rates (optional)</summary>
            <p>
              Blank values stay unavailable. A bunker price alone cannot
              establish fuel use. Figures below are operator assumptions, not
              measured savings or tariffs.
            </p>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={simulatedFinance}
            >
              Use named illustrative consumption and price scenario
            </Button>
            <p>
              Explicit scenario: propulsion 24 t/day at 12 kn with a cubic speed
              relation; auxiliary 2 t/day; anchorage and departure hold each 2
              t/day; fixed simulated load, range 8–16 kn; assumed USD 600/t,
              valid from the reference through seven days after the baseline
              ETA. No charter, berth, delay or other rate is included.
            </p>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={Boolean(value.finance?.consumption)}
                onChange={(e) =>
                  patchFinance({
                    consumption: e.target.checked
                      ? {
                          referenceSpeedKn: Number.NaN,
                          referencePropulsionTonnesPerDay: Number.NaN,
                          minSpeedKn: value.minSpeedKn,
                          maxSpeedKn: value.maxSpeedKn,
                          loadCondition: "",
                          source: "",
                          declaredAt: new Date().toISOString(),
                        }
                      : undefined,
                  })
                }
              />
              Supply a consumption declaration
            </label>
            {value.finance?.consumption ? (
              <div className="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-2">
                <NumberField
                  label="Consumption reference speed (kn)"
                  value={value.finance.consumption.referenceSpeedKn}
                  onChange={(referenceSpeedKn) =>
                    patchConsumption({
                      referenceSpeedKn: referenceSpeedKn ?? Number.NaN,
                    })
                  }
                />
                <NumberField
                  label="Reference propulsion demand (t/day)"
                  value={
                    value.finance.consumption.referencePropulsionTonnesPerDay
                  }
                  onChange={(referencePropulsionTonnesPerDay) =>
                    patchConsumption({
                      referencePropulsionTonnesPerDay:
                        referencePropulsionTonnesPerDay ?? Number.NaN,
                    })
                  }
                />
                <NumberField
                  label="Sailing auxiliary demand (t/day; optional)"
                  value={value.finance.consumption.auxiliaryTonnesPerDay}
                  onChange={(auxiliaryTonnesPerDay) =>
                    patchConsumption({ auxiliaryTonnesPerDay })
                  }
                />
                <NumberField
                  label="Anchorage demand (t/day; optional)"
                  value={value.finance.consumption.anchorageTonnesPerDay}
                  onChange={(anchorageTonnesPerDay) =>
                    patchConsumption({ anchorageTonnesPerDay })
                  }
                />
                <NumberField
                  label="Departure holding demand (t/day; optional)"
                  value={value.finance.consumption.departureHoldTonnesPerDay}
                  onChange={(departureHoldTonnesPerDay) =>
                    patchConsumption({ departureHoldTonnesPerDay })
                  }
                />
                <NumberField
                  label="Consumption applicable minimum speed (kn)"
                  value={value.finance.consumption.minSpeedKn}
                  onChange={(minSpeedKn) =>
                    patchConsumption({ minSpeedKn: minSpeedKn ?? Number.NaN })
                  }
                />
                <NumberField
                  label="Consumption applicable maximum speed (kn)"
                  value={value.finance.consumption.maxSpeedKn}
                  onChange={(maxSpeedKn) =>
                    patchConsumption({ maxSpeedKn: maxSpeedKn ?? Number.NaN })
                  }
                />
                <TextField
                  label="Consumption load condition and assumptions"
                  value={value.finance.consumption.loadCondition}
                  onChange={(loadCondition) =>
                    patchConsumption({ loadCondition })
                  }
                />
                <TextField
                  label="Consumption declaration source"
                  value={value.finance.consumption.source}
                  onChange={(source) => patchConsumption({ source })}
                />
                <TextField
                  label="Consumption declaration time UTC"
                  value={value.finance.consumption.declaredAt}
                  onChange={(declaredAt) => patchConsumption({ declaredAt })}
                />
              </div>
            ) : null}
            {(["fuelPrice", "elapsedTimeRate"] as const).map((key) => {
              const rate = value.finance?.[key];
              const fuel = key === "fuelPrice";
              const label = fuel ? "Bunker price" : "Whole elapsed-time charge";
              return (
                <div
                  key={key}
                  className="space-y-2 border-t border-[var(--line)] pt-2"
                >
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={Boolean(rate)}
                      onChange={(e) =>
                        patchFinance({
                          [key]: e.target.checked
                            ? {
                                amount: Number.NaN,
                                currency: "",
                                per: fuel ? "tonne" : "hour",
                                source: "",
                                validFrom: "",
                                validTo: "",
                                ...(fuel
                                  ? {}
                                  : {
                                      applicability:
                                        "WHOLE_MODELED_ELAPSED" as const,
                                    }),
                              }
                            : undefined,
                        })
                      }
                    />
                    Supply {label.toLowerCase()}
                  </label>
                  {rate ? (
                    <div className="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-2">
                      <NumberField
                        label={`${label} amount`}
                        value={rate.amount}
                        onChange={(amount) =>
                          patchRate(key, { amount: amount ?? Number.NaN })
                        }
                      />
                      <TextField
                        label={`${label} currency`}
                        value={rate.currency}
                        onChange={(currency) => patchRate(key, { currency })}
                      />
                      {!fuel ? (
                        <label className="flex flex-col gap-1">
                          Elapsed charge unit
                          <select
                            className={FIELD}
                            aria-label="Elapsed charge unit"
                            value={rate.per}
                            onChange={(e) =>
                              patchRate(key, {
                                per: e.target.value as "hour" | "day",
                              })
                            }
                          >
                            <option value="hour">Per hour</option>
                            <option value="day">Per day</option>
                          </select>
                        </label>
                      ) : (
                        <p>Price unit: currency per tonne</p>
                      )}
                      <TextField
                        label={`${label} source and applicability`}
                        value={rate.source}
                        onChange={(source) => patchRate(key, { source })}
                      />
                      <TextField
                        label={`${label} valid from UTC`}
                        value={rate.validFrom}
                        onChange={(validFrom) => patchRate(key, { validFrom })}
                      />
                      <TextField
                        label={`${label} valid through UTC`}
                        value={rate.validTo}
                        onChange={(validTo) => patchRate(key, { validTo })}
                      />
                    </div>
                  ) : null}
                </div>
              );
            })}
            <p>
              An elapsed-time rate must apply to the whole modeled period. Do
              not also add overlapping charter, delay or holding charges. Mixed
              currencies require retained applicable FX; this form does not
              invent one.
            </p>
            <TextField
              label="Comparison currency (optional)"
              value={value.finance?.currency}
              onChange={(currency) =>
                patchFinance({ currency: currency || undefined })
              }
            />
          </details>
          <p>
            Each comparison freezes these declarations and the consumed
            forecast. Editing them creates a new comparison requiring new
            review; earlier approvals and advisories stay inspectable.
          </p>
        </>
      ) : null}
    </fieldset>
  );
}
