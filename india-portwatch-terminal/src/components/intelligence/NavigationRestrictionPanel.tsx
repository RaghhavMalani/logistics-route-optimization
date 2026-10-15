import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { getBlob, getJson, postJson } from "@/services/api";
import { Button } from "@/components/ui/button";
import { formatUtc } from "@/components/kit/primitives";
import type { DecisionProblem } from "@/types/decisions";

interface BridgeNotice {
  noticeRef: string;
  title?: string;
  source: string;
  sourceStatus: string;
  status?: string;
  revisionId?: string;
  availableAt?: string;
  checkedAt: string;
  reason?: string;
  providerCreatedAt?: string;
  providerModifiedAt?: string;
  publicationPrecision?: string;
  restriction?: string;
  unaffectedAlternative?: string;
  confirmation?: string;
  originalWording?: string;
  responseSha256?: string;
  coordinates?: { lat: number; lon: number; basis: string };
  windows: {
    start: string;
    end: string;
    localDate: string;
    localStart: string;
    localEnd: string;
    timeZoneBasis: string;
  }[];
}
interface BridgeVoyage {
  id: string;
  name: string;
  portCode: string;
  cargo: string;
  operationalEpisode?: { id: string; voyageLegId: string };
  declaredPassage?: {
    sourceFamily?: string;
    id: string;
    passageAt: string;
    postPassageHours: number;
  };
}

function focusAsset(notice: BridgeNotice) {
  if (!notice.coordinates) return;
  window.dispatchEvent(
    new CustomEvent("portwatch:focus-constraint", {
      detail: {
        id: "WRIGHTSVILLE_SR74",
        name: notice.title,
        ...notice.coordinates,
        period: notice.windows
          .map(
            (w) =>
              `${w.localDate} ${w.localStart}–${w.localEnd} assumed local time`,
          )
          .join("; "),
      },
    }),
  );
}

export function NavigationRestrictionPanel({
  onDecision,
}: {
  onDecision?: (problem: DecisionProblem) => void;
}) {
  const { session, identityHeaders } = useAuth();
  const client = useQueryClient();
  const [vesselId, setVesselId] = useState("PWD-001");
  const [passage, setPassage] = useState("2026-10-17T12:00");
  const [hours, setHours] = useState(180);
  const [confirmed, setConfirmed] = useState(false);
  const [newCall, setNewCall] = useState(false);
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const [dimensions, setDimensions] = useState({
    loaM: 70,
    beamM: 12,
    draughtM: 3,
    airDraughtM: 9,
  });
  const q = useQuery({
    queryKey: ["navigation-restrictions", identityHeaders],
    queryFn: ({ signal }) =>
      getJson<{
        notices: BridgeNotice[];
        voyages: BridgeVoyage[];
        meaning: string;
      }>("/intelligence/navigation-restrictions", identityHeaders, {
        signal,
        timeoutMs: 60000,
      }),
    enabled: session?.mode === "demo",
    staleTime: 60000,
    retry: 1,
  });
  const notice = q.data?.notices[0];
  const vessel = q.data?.voyages.find((v) => v.id === vesselId);
  const invalidate = () => {
    void client.invalidateQueries({ queryKey: ["navigation-restrictions"] });
    void client.invalidateQueries({ queryKey: ["company"] });
  };
  const nextCall = useMutation({
    mutationFn: () =>
      postJson(
        "/intelligence/operational-calls",
        {
          vesselId,
          requestedArrival: new Date(
            Date.parse(passage + ":00Z") + hours * 3600000,
          ).toISOString(),
          requestId,
          newCallConfirmed: newCall,
        },
        identityHeaders,
      ),
    onSuccess: () => {
      invalidate();
      setNewCall(false);
      setConfirmed(false);
      setRequestId(crypto.randomUUID());
    },
  });
  const save = useMutation({
    mutationFn: () =>
      postJson(
        "/intelligence/navigation-passage-plan",
        {
          vesselId,
          areaId: "WRIGHTSVILLE_SR74",
          passageAt: passage + ":00Z",
          postPassageHours: hours,
          characteristics: dimensions,
          openingRequired: true,
          emergencyTransit: false,
          timezoneAssumption: "America/New_York",
          passageConfirmed: confirmed,
        },
        identityHeaders,
      ),
    onSuccess: invalidate,
  });
  const compare = useMutation({
    mutationFn: () =>
      postJson<DecisionProblem>(
        "/intelligence/navigation-comparison",
        { vesselId, revisionId: notice?.revisionId },
        identityHeaders,
      ),
    onSuccess: (p) => {
      if (notice) focusAsset(notice);
      void client.invalidateQueries({
        queryKey: ["saved-intelligence-comparisons"],
      });
      onDecision?.(p);
    },
  });
  const canPropose = !!onDecision && session?.user.role === "SHIPPING_COMPANY";
  const original = useMutation({
    mutationFn: () =>
      getBlob(`/intelligence/feedback/evidence/${notice?.responseSha256}`),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${notice?.responseSha256}.geojson`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
  });
  if (session?.mode !== "demo") return null;
  return (
    <details
      className="my-2 border border-[var(--line)] p-3 text-[11px]"
      data-testid="navigation-restriction-panel"
      open
    >
      <summary>
        Official bridge notice → declared passage → conditional decision
      </summary>
      {q.isPending ? (
        <p>Checking retained NAVCEN MSI…</p>
      ) : q.isError ? (
        <p role="alert">Source unavailable: {q.error.message}</p>
      ) : notice ? (
        <>
          <p>
            {notice.noticeRef} · {notice.title} · {notice.sourceStatus} /{" "}
            {notice.status ?? "UNAVAILABLE"}
          </p>
          <p>{notice.restriction ?? notice.reason}</p>
          <p>{notice.unaffectedAlternative}</p>
          <p>
            Provider created {formatUtc(notice.providerCreatedAt ?? null)} ·
            modified {formatUtc(notice.providerModifiedAt ?? null)}. Publication
            instant unverified; first application receipt{" "}
            {formatUtc(notice.availableAt ?? null)} · checked{" "}
            {formatUtc(notice.checkedAt)}.
          </p>
          {notice.windows.map((w) => (
            <p key={w.start}>
              Closed-position interval {w.localDate} {w.localStart}–{w.localEnd}
              . UTC planning interval {formatUtc(w.start)}–{formatUtc(w.end)}.{" "}
              {w.timeZoneBasis}.
            </p>
          ))}
          <p>{notice.confirmation}</p>
          <p>{q.data?.meaning}</p>
          <a
            className="underline"
            href={notice.source}
            target="_blank"
            rel="noreferrer"
          >
            Official original GeoJSON
          </a>{" "}
          {notice.responseSha256 ? (
            <Button
              size="sm"
              variant="outline"
              disabled={original.isPending}
              onClick={() => original.mutate()}
            >
              Retained hash-verified original
            </Button>
          ) : null}
          {notice.coordinates ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => focusAsset(notice)}
            >
              Show bridge constraint on original map
            </Button>
          ) : null}
          <details>
            <summary>Inspect literal authority wording and hash</summary>
            <p className="whitespace-pre-wrap">{notice.originalWording}</p>
            <p className="break-all">{notice.responseSha256}</p>
          </details>
          {canPropose ? (
            <fieldset className="border border-[var(--line)] p-2 space-y-2">
              <legend>
                Declare ordinary fictional passage requiring a bridge opening
              </legend>
              <label className="block">
                Voyage{" "}
                <select
                  aria-label="Bridge restriction voyage"
                  value={vesselId}
                  onChange={(e) => {
                    setVesselId(e.target.value);
                    setConfirmed(false);
                    setNewCall(false);
                    setRequestId(crypto.randomUUID());
                  }}
                  className="bg-[var(--panel-2)]"
                >
                  {q.data?.voyages.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.name} · {v.portCode}
                    </option>
                  ))}
                </select>
              </label>
              <p>
                Explicit bridge passage → {vessel?.portCode}; cargo{" "}
                {vessel?.cargo}. This is a declared fictional itinerary, not a
                validated ocean route or tracked movement.
              </p>
              <label className="block">
                Requested bridge passage (UTC){" "}
                <input
                  aria-label="Bridge passage UTC"
                  type="datetime-local"
                  value={passage}
                  onChange={(e) => {
                    setPassage(e.target.value);
                    setConfirmed(false);
                    setRequestId(crypto.randomUUID());
                  }}
                  className="bg-[var(--panel-2)] max-w-full"
                />
              </label>
              <label className="block">
                Assumed onward travel (h){" "}
                <input
                  aria-label="Bridge onward travel hours"
                  type="number"
                  min={24}
                  max={720}
                  value={hours}
                  onChange={(e) => {
                    setHours(Number(e.target.value));
                    setConfirmed(false);
                    setRequestId(crypto.randomUUID());
                  }}
                  className="bg-[var(--panel-2)] w-20"
                />
              </label>
              <div className="flex flex-wrap gap-2">
                {(["loaM", "beamM", "draughtM", "airDraughtM"] as const).map(
                  (key) => (
                    <label key={key}>
                      {
                        {
                          loaM: "Length",
                          beamM: "Beam",
                          draughtM: "Draught",
                          airDraughtM: "Air draught",
                        }[key]
                      }{" "}
                      (m){" "}
                      <input
                        aria-label={`Bridge declared ${key}`}
                        type="number"
                        min={0.1}
                        value={dimensions[key]}
                        onChange={(e) => {
                          setDimensions((d) => ({
                            ...d,
                            [key]: Number(e.target.value),
                          }));
                          setConfirmed(false);
                        }}
                        className="bg-[var(--panel-2)] w-16"
                      />
                    </label>
                  ),
                )}
              </div>
              <label className="flex gap-2">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                I declare this passage needs an opening, is not emergency
                transit, and confirm America/New_York as the geographic
                local-zone assumption. Actual water level, clearance, route
                suitability and opening are unverified.
              </label>
              <Button
                size="sm"
                disabled={!confirmed || !passage || save.isPending}
                onClick={() => save.mutate()}
              >
                Save bridge passage for this call
              </Button>
              <p>
                Call{" "}
                {vessel?.operationalEpisode?.id ??
                  "Created on first declaration"}
                . Saving an ETA or evidence revision keeps this call.
              </p>
              {vessel?.declaredPassage?.sourceFamily === "NAVCEN_MSI" ? (
                <p>
                  Saved bridge request{" "}
                  {formatUtc(vessel.declaredPassage.passageAt)} · assumed onward
                  travel {vessel.declaredPassage.postPassageHours} h.
                </p>
              ) : null}
              <Button
                size="sm"
                disabled={
                  vessel?.declaredPassage?.sourceFamily !== "NAVCEN_MSI" ||
                  notice.sourceStatus !== "CURRENT" ||
                  notice.status !== "SCHEDULED" ||
                  compare.isPending
                }
                onClick={() => compare.mutate()}
              >
                Compare bridge passage windows
              </Button>
              <details>
                <summary>
                  Start a distinct next call without resetting this visitor
                </summary>
                <label className="flex gap-2">
                  <input
                    type="checkbox"
                    checked={newCall}
                    onChange={(e) => setNewCall(e.target.checked)}
                  />
                  This is a genuinely new call, not an ETA edit or evidence
                  refresh. Prior approvals and advisories remain saved.
                </label>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!newCall || !passage || nextCall.isPending}
                  onClick={() => nextCall.mutate()}
                >
                  Create distinct next call
                </Button>
              </details>
            </fieldset>
          ) : null}
        </>
      ) : null}
      {save.isError || compare.isError || nextCall.isError ? (
        <p role="alert">
          {save.error?.message ??
            compare.error?.message ??
            nextCall.error?.message}
        </p>
      ) : null}
      {original.isError ? (
        <p role="alert">Original unavailable: {original.error.message}</p>
      ) : null}
    </details>
  );
}
