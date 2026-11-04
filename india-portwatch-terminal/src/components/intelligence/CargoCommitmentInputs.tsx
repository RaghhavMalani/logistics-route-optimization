import { Button } from "@/components/ui/button";
import type {
  CargoCommitmentDeclaration,
  CargoConnectionDeclaration,
} from "@/services/current-inputs";

const FIELD =
  "min-w-0 max-w-full rounded border border-[var(--line)] bg-[var(--panel-2)] px-1.5 py-1 text-[var(--text)]";

function TextField({
  label,
  value,
  onChange,
}: {
  label: string;
  value?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      {label}
      <input
        aria-label={label}
        className={FIELD}
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value?: number;
  onChange: (value: number | undefined) => void;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      {label}
      <input
        aria-label={label}
        className={FIELD}
        type="number"
        min={0}
        step="any"
        value={value != null && Number.isFinite(value) ? value : ""}
        onChange={(event) =>
          onChange(
            event.target.value === "" ? undefined : Number(event.target.value),
          )
        }
      />
    </label>
  );
}

function EligibilityField({
  label,
  value,
  onChange,
}: {
  label: string;
  value?: boolean;
  onChange: (value: boolean | undefined) => void;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      {label}
      <select
        aria-label={label}
        className={FIELD}
        value={value === undefined ? "" : String(value)}
        onChange={(event) =>
          onChange(
            event.target.value === ""
              ? undefined
              : event.target.value === "true",
          )
        }
      >
        <option value="">Unknown</option>
        <option value="true">Assumed eligible</option>
        <option value="false">Not eligible</option>
      </select>
    </label>
  );
}

function ConnectionInputs({
  value,
  onChange,
  prefix,
}: {
  value: CargoConnectionDeclaration;
  onChange: (value: CargoConnectionDeclaration) => void;
  prefix: "Booked" | "Later";
}) {
  const patch = (change: Partial<CargoConnectionDeclaration>) =>
    onChange({ ...value, ...change });
  return (
    <fieldset className="space-y-2 border border-[var(--line)] p-2">
      <legend>{prefix} onward sailing · declared assumptions</legend>
      <div className="grid min-w-0 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <TextField
          label={`${prefix} onward vessel ID`}
          value={value.vesselId}
          onChange={(vesselId) => patch({ vesselId })}
        />
        <TextField
          label={`${prefix} onward vessel name`}
          value={value.name}
          onChange={(name) => patch({ name })}
        />
        <TextField
          label={`${prefix} loading cutoff (aware ISO time)`}
          value={value.loadingCutoffAt}
          onChange={(loadingCutoffAt) =>
            patch({ loadingCutoffAt: loadingCutoffAt || undefined })
          }
        />
        <TextField
          label={`${prefix} departure (aware ISO time)`}
          value={value.departureAt}
          onChange={(departureAt) =>
            patch({ departureAt: departureAt || undefined })
          }
        />
        <TextField
          label={`${prefix} rotation ports (comma separated)`}
          value={value.onwardPorts?.join(", ")}
          onChange={(ports) =>
            patch({
              onwardPorts: ports
                ? ports
                    .split(",")
                    .map((port) => port.trim().toUpperCase())
                    .filter(Boolean)
                : undefined,
            })
          }
        />
        <NumberField
          label={`${prefix} available capacity (TEU)`}
          value={value.availableTeu}
          onChange={(availableTeu) => patch({ availableTeu })}
        />
        <NumberField
          label={`${prefix} remaining deadweight (t)`}
          value={value.availableDeadweightT}
          onChange={(availableDeadweightT) => patch({ availableDeadweightT })}
        />
        <NumberField
          label={`${prefix} available reefer plugs`}
          value={value.availableReeferPlugs}
          onChange={(availableReeferPlugs) => patch({ availableReeferPlugs })}
        />
        <EligibilityField
          label={`${prefix} dangerous-goods eligibility`}
          value={value.acceptsHazardous}
          onChange={(acceptsHazardous) => patch({ acceptsHazardous })}
        />
        <EligibilityField
          label={`${prefix} out-of-gauge eligibility`}
          value={value.acceptsOog}
          onChange={(acceptsOog) => patch({ acceptsOog })}
        />
      </div>
      <TextField
        label={`${prefix} schedule and capacity basis`}
        value={value.basis}
        onChange={(basis) => patch({ basis: basis || undefined })}
      />
    </fieldset>
  );
}

/** A deliberate declaration creates fictional cargo in this visitor's voyage. */
export function CargoCommitmentInputs({
  value,
  onChange,
  voyageId,
  portCode,
  requestedArrival,
  passageEnabled,
}: {
  value: CargoCommitmentDeclaration | null;
  onChange: (value: CargoCommitmentDeclaration | null) => void;
  voyageId: string;
  portCode: string;
  requestedArrival: string;
  passageEnabled: boolean;
}) {
  const patch = (change: Partial<CargoCommitmentDeclaration>) => {
    if (value) onChange({ ...value, ...change });
  };
  const connection = (
    reference: number,
    later = false,
  ): CargoConnectionDeclaration => ({
    vesselId: later ? "FICTIONAL-ONWARD-LATER" : "FICTIONAL-ONWARD-BOOKED",
    name: later ? "Fictional next sailing" : "Fictional booked sailing",
    departureAt: new Date(
      reference + (later ? 38 : 14) * 3600000,
    ).toISOString(),
    loadingCutoffAt: new Date(
      reference + (later ? 36 : 12) * 3600000,
    ).toISOString(),
    onwardPorts: ["SGSIN"],
    availableTeu: 200,
    availableDeadweightT: 3000,
    availableReeferPlugs: 40,
    acceptsHazardous: true,
    acceptsOog: true,
    basis:
      "Explicitly selected illustrative sailing, cutoff and available capacities; no operator booking or terminal confirmation.",
  });
  const initialise = () => {
    const reference = Date.parse(requestedArrival);
    if (!Number.isFinite(reference)) return;
    onChange({
      schemaVersion: 1,
      fictionalShipment: true,
      voyageId,
      portCode,
      declaredAt: new Date().toISOString(),
      basis:
        "Explicitly selected fictional shipment and onward-connection scenario, owned by this visitor. All editable values are demonstration assumptions.",
      mustMeet: false,
      shipment: {
        shipmentId: `DEMO-CARGO-${crypto.randomUUID()}`,
        teu: 24,
        cargoClass: "dry",
        destinationPort: "SGSIN",
        weightT: 288,
      },
      transfer: {
        approachToStartHours: 2,
        basis:
          "Assume two hours from conditional clear approach to the start of discharge, including berth access and release prerequisites. This interval contains no cargo-model handling.",
        acceptedSchematicHandling: true,
        gangs: 1,
        mode: "DIRECT",
      },
      bookedConnection: connection(reference),
      laterConnections: [],
    });
  };
  return (
    <fieldset
      className="space-y-2 border-t border-[var(--line)] pt-2"
      data-testid="cargo-commitment-inputs"
    >
      <legend className="font-medium">
        Optional cargo connection commitment
      </legend>
      <p>
        Connect one fictional shipment to this owned voyage ({voyageId}) at{" "}
        {portCode}. The default passage comparison has no cargo constraint.
      </p>
      {!value ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={
            !passageEnabled || !Number.isFinite(Date.parse(requestedArrival))
          }
          onClick={initialise}
        >
          Use illustrative cargo connection scenario
        </Button>
      ) : (
        <>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => onChange(null)}
          >
            Remove cargo commitment
          </Button>
          <p>
            Selected illustrative scenario. Edit or clear values below. An empty
            cutoff, start basis or required capacity produces an unknown result.
            No official two-hour cutoff is inferred.
          </p>
          <label className="flex items-start gap-2">
            <input
              type="checkbox"
              checked={value.mustMeet}
              onChange={(event) => patch({ mustMeet: event.target.checked })}
            />
            Require this booked connection for passage approval
          </label>
          <p>
            Optional context does not change passage ranking. Only an explicitly
            required connection can block a passage choice. Changes create a new
            comparison with fresh review.
          </p>
          <div className="grid min-w-0 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            <TextField
              label="Fictional shipment ID"
              value={value.shipment.shipmentId}
              onChange={(shipmentId) =>
                patch({ shipment: { ...value.shipment, shipmentId } })
              }
            />
            <NumberField
              label="Shipment quantity (TEU)"
              value={value.shipment.teu}
              onChange={(teu) =>
                patch({ shipment: { ...value.shipment, teu } })
              }
            />
            <NumberField
              label="Shipment weight (t)"
              value={value.shipment.weightT}
              onChange={(weightT) =>
                patch({ shipment: { ...value.shipment, weightT } })
              }
            />
            <label className="flex min-w-0 flex-col gap-1">
              Cargo class
              <select
                aria-label="Cargo class"
                className={FIELD}
                value={value.shipment.cargoClass}
                onChange={(event) =>
                  patch({
                    shipment: {
                      ...value.shipment,
                      cargoClass: event.target
                        .value as CargoCommitmentDeclaration["shipment"]["cargoClass"],
                    },
                  })
                }
              >
                {["dry", "reefer", "hazardous", "oog", "empty"].map((kind) => (
                  <option key={kind} value={kind}>
                    {kind}
                  </option>
                ))}
              </select>
            </label>
            <TextField
              label="Shipment onward destination port"
              value={value.shipment.destinationPort}
              onChange={(destinationPort) =>
                patch({
                  shipment: {
                    ...value.shipment,
                    destinationPort: destinationPort.toUpperCase(),
                  },
                })
              }
            />
            <TextField
              label="Optional latest onward departure (aware ISO time)"
              value={value.shipment.latestDepartureAt}
              onChange={(latestDepartureAt) =>
                patch({
                  shipment: {
                    ...value.shipment,
                    latestDepartureAt: latestDepartureAt || undefined,
                  },
                })
              }
            />
            <NumberField
              label="Assumed approach to discharge-start interval (h)"
              value={value.transfer.approachToStartHours}
              onChange={(approachToStartHours) =>
                patch({ transfer: { ...value.transfer, approachToStartHours } })
              }
            />
            <NumberField
              label="Assumed handling gangs (whole number)"
              value={value.transfer.gangs}
              onChange={(gangs) =>
                patch({ transfer: { ...value.transfer, gangs } })
              }
            />
          </div>
          <TextField
            label="Approach to discharge-start basis"
            value={value.transfer.basis}
            onChange={(basis) =>
              patch({
                transfer: { ...value.transfer, basis: basis || undefined },
              })
            }
          />
          <label className="flex items-start gap-2">
            <input
              type="checkbox"
              checked={value.transfer.acceptedSchematicHandling}
              onChange={(event) =>
                patch({
                  transfer: {
                    ...value.transfer,
                    acceptedSchematicHandling: event.target.checked,
                  },
                })
              }
            />
            Accept the existing schematic handling model for this scenario
          </label>
          <p>
            Direct transfer under the declared gang count. The existing
            schematic model uses 24 TEU/h discharge and 22 TEU/h loading per
            gang, with class handling factors and 1.5 h transfer overhead. It
            counts each handling stage once; the approach interval adds none of
            them. These model constants are demonstration assumptions, not
            terminal performance. Simultaneous access and prerequisites are
            assumptions, not berth or customs clearance.
          </p>
          <ConnectionInputs
            prefix="Booked"
            value={value.bookedConnection}
            onChange={(bookedConnection) => patch({ bookedConnection })}
          />
          {value.laterConnections[0] ? (
            <>
              <ConnectionInputs
                prefix="Later"
                value={value.laterConnections[0]}
                onChange={(later) => patch({ laterConnections: [later] })}
              />
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => patch({ laterConnections: [] })}
              >
                Remove declared later sailing
              </Button>
            </>
          ) : (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() =>
                patch({
                  laterConnections: [
                    connection(Date.parse(requestedArrival), true),
                  ],
                })
              }
            >
              Declare an illustrative later sailing
            </Button>
          )}
          <TextField
            label="Cargo declaration provenance"
            value={value.basis}
            onChange={(basis) => patch({ basis })}
          />
          <p>
            Schedule times need an explicit UTC Z or offset. Final delivery,
            real booking, reserved capacity, contractual cargo charges and
            execution remain unavailable.
          </p>
        </>
      )}
      {!passageEnabled ? (
        <p>
          First include a declared remaining passage to evaluate a cargo
          connection.
        </p>
      ) : null}
    </fieldset>
  );
}
