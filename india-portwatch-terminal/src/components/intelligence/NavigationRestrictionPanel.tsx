import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { getBlob, postJson } from "@/services/api";
import {
  getRollingIntelligence,
  reviewSelection,
  type NavigationNotice,
} from "@/services/rolling-intelligence";
import { Button } from "@/components/ui/button";
import { formatUtc } from "@/components/kit/primitives";
import type { DecisionProblem } from "@/types/decisions";

function focusAsset(notice: NavigationNotice) {
  if (!notice.coordinates) return;
  window.dispatchEvent(
    new CustomEvent("portwatch:focus-constraint", {
      detail: {
        id: notice.areaId ?? notice.noticeId,
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
  const [noticeId, setNoticeId] = useState("");
  const [view, setView] = useState("event");
  const [limit, setLimit] = useState(30);
  const [passage, setPassage] = useState("");
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
    queryFn: ({ signal }) => getRollingIntelligence(identityHeaders, signal),
    enabled: session?.mode === "demo",
    staleTime: 60000,
    refetchInterval: 60000,
    retry: 1,
  });
  useEffect(() => {
    const selected = reviewSelection();
    if (selected.noticeId) setNoticeId(selected.noticeId);
    if (selected.vesselId) setVesselId(selected.vesselId);
  }, []);
  const notice =
    q.data?.notices.find((n) => n.noticeId === noticeId) ??
    q.data?.notices.find(
      (n) => n.extractionStatus === "SUPPORTED" && n.status === "SCHEDULED",
    ) ??
    q.data?.notices.find((n) => n.extractionStatus === "SUPPORTED") ??
    q.data?.notices[0];
  const vessel = q.data?.voyages.find((v) => v.id === vesselId);
  const plan = notice?.areaId
    ? (vessel?.declaredPassages?.[notice.areaId] ??
      (vessel?.declaredPassage?.areaId === notice.areaId
        ? vessel.declaredPassage
        : null))
    : null;
  const relation = q.data?.exposureQueue.find(
    (r) => r.noticeId === notice?.noticeId && r.vesselId === vesselId,
  );
  const rows = (q.data?.exposureQueue ?? []).filter((r) =>
    view === "voyage"
      ? r.vesselId === vesselId
      : r.noticeId === notice?.noticeId,
  );
  const zone = notice?.windows[0]?.timeZone;
  const nextWindow = notice?.windows.find(
    (w) => Date.parse(w.start) > Date.now(),
  );
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
          noticeId: notice?.noticeId,
          areaId: notice?.areaId,
          passageAt: passage + ":00Z",
          postPassageHours: hours,
          characteristics: dimensions,
          openingRequired: true,
          emergencyTransit: false,
          timezoneAssumption: zone,
          passageConfirmed: confirmed,
        },
        identityHeaders,
      ),
    onSuccess: invalidate,
  });
  const lead = useMutation({
    mutationFn: () =>
      postJson(
        "/intelligence/exposure-lead",
        { vesselId, noticeId: notice?.noticeId, possible: true },
        identityHeaders,
      ),
    onSuccess: invalidate,
  });
  const compare = useMutation({
    mutationFn: () =>
      postJson<DecisionProblem>(
        "/intelligence/navigation-comparison",
        {
          vesselId,
          noticeId: notice?.noticeId,
          revisionId: notice?.revisionId,
        },
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
        Rolling official notices → voyage exposure → supported decisions
      </summary>
      {q.isPending ? (
        <p>Checking retained NAVCEN MSI…</p>
      ) : q.isError ? (
        <p role="alert">Source unavailable: {q.error.message}</p>
      ) : notice ? (
        <>
          <p>
            Source {q.data?.sourceStatus} · checked{" "}
            {formatUtc(q.data?.checkedAt ?? null)}. Discovery is broader than
            reviewed calculation coverage.
          </p>
          <div className="flex flex-wrap gap-3 my-2">
            <label>
              Source event{" "}
              <select
                aria-label="Official source event"
                value={notice.noticeId}
                onChange={(e) => {
                  setNoticeId(e.target.value);
                  setConfirmed(false);
                  setLimit(30);
                }}
                className="bg-[var(--panel-2)] border border-[var(--line)] max-w-full w-72"
              >
                {(q.data?.notices ?? []).map((n) => (
                  <option key={n.noticeId} value={n.noticeId}>
                    {n.providerNoticeId ?? n.noticeId} ·{" "}
                    {n.title ?? n.noticeRef} · {n.status} /{" "}
                    {n.extractionStatus ?? "UNSUPPORTED"}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Voyage{" "}
              <select
                aria-label="Exposure voyage"
                value={vesselId}
                className="bg-[var(--panel-2)] border border-[var(--line)]"
                onChange={(e) => {
                  setVesselId(e.target.value);
                  setConfirmed(false);
                  setNewCall(false);
                  setRequestId(crypto.randomUUID());
                }}
              >
                {q.data?.voyages.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name} · {v.portCode}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Inspect relations{" "}
              <select
                aria-label="Exposure direction"
                value={view}
                onChange={(e) => {
                  setView(e.target.value);
                  setLimit(30);
                }}
                className="bg-[var(--panel-2)] border border-[var(--line)]"
              >
                <option value="event">Event → voyages</option>
                <option value="voyage">Voyage → events</option>
              </select>
            </label>
          </div>
          <p>
            {q.data?.notices.length ?? 0} discovered notices ·{" "}
            {q.data?.notices.filter((n) => n.extractionStatus === "SUPPORTED")
              .length ?? 0}{" "}
            extraction-supported notices. A supported parser does not establish
            current applicability or observed closure.
          </p>
          <details open className="border border-[var(--line)] p-2 my-2">
            <summary>
              Review queue · {rows.length} event/voyage relations
            </summary>
            <p>
              Heuristic review priority uses declared exposure, source status
              and time to declared passage. It is not a disruption probability.
            </p>
            <div className="max-h-64 overflow-auto">
              {rows.slice(0, limit).map((r) => (
                <div
                  key={`${r.noticeId}-${r.vesselId}`}
                  className="border-t border-[var(--line)] py-2"
                >
                  <button
                    className="underline text-left"
                    onClick={() => {
                      setNoticeId(r.noticeId);
                      setVesselId(r.vesselId);
                      setConfirmed(false);
                    }}
                  >
                    #{r.priority.rank} · {r.title} → {r.vesselName}
                  </button>
                  <p>
                    {r.status} · source {r.sourceValidity ?? r.sourceStatus} ·{" "}
                    {r.calculable
                      ? "Conditional comparison available"
                      : "No numerical action"}
                  </p>
                  <p>{r.reason}</p>
                  <p>{r.calculationReason}</p>
                  <p>
                    Passage {formatUtc(r.passageAt ?? null)} · missing{" "}
                    {r.missingInputs.join(", ") ||
                      "none for this matching rule"}
                    .
                  </p>
                  <details>
                    <summary>Matching and priority evidence</summary>
                    <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all">
                      {JSON.stringify(r, null, 2)}
                    </pre>
                  </details>
                </div>
              ))}
            </div>
            {rows.length > limit ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setLimit((n) => n + 30)}
              >
                Show next 30 relations
              </Button>
            ) : null}
          </details>
          <p>
            {notice.noticeRef} · {notice.title} · {notice.sourceStatus} /{" "}
            {notice.status ?? "UNAVAILABLE"}
          </p>
          {notice.extractionMode === "HISTORICAL_EXTRACTION_REPLAY" ? (
            <p role="status">
              Historical extraction replay from a retained original. Source
              first received {formatUtc(notice.sourceFirstReceivedAt ?? null)};
              this extraction available {formatUtc(notice.availableAt ?? null)}.
              Current source is unavailable; new numerical actions are blocked.
            </p>
          ) : null}
          <p>
            Extraction {notice.extractionStatus ?? "UNSUPPORTED"} ·{" "}
            {notice.reason ?? "Reviewed source semantics"}.{" "}
            {relation?.calculationReason}
          </p>
          {canPropose && notice.areaId ? (
            <Button
              size="sm"
              variant="outline"
              disabled={lead.isPending}
              onClick={() => lead.mutate()}
            >
              Mark possible passage; needs confirmation
            </Button>
          ) : null}
          {lead.isSuccess ? (
            <p role="status">
              Possible passage recorded as a review lead. No confirmed route,
              applicability, delay or change to the current arrival is asserted.
            </p>
          ) : null}
          <p>{notice.restriction ?? notice.reason}</p>
          <p>{notice.unaffectedAlternative}</p>
          <p>
            Provider created {formatUtc(notice.providerCreatedAt ?? null)} ·
            modified {formatUtc(notice.providerModifiedAt ?? null)}. Publication
            instant unverified; extraction/revision available{" "}
            {formatUtc(notice.availableAt ?? null)} · checked{" "}
            {formatUtc(notice.checkedAt)}.
          </p>
          {notice.windows.map((w) => (
            <p key={w.start}>
              Closed-position interval {w.localDate} {w.localStart}–{w.localEnd}
              . UTC planning interval {formatUtc(w.start)}–{formatUtc(w.end)}.{" "}
              {w.timeZoneBasis}.{" "}
              {Date.parse(w.end) <= Date.now()
                ? "Elapsed published window; actual occurrence remains unverified."
                : "Scheduled window; actual access is unconfirmed."}
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
          {canPropose && notice.areaId && notice.windows.length > 0 ? (
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
              <Button
                size="sm"
                variant="outline"
                disabled={!nextWindow}
                onClick={() => {
                  if (!nextWindow) return;
                  setPassage(nextWindow.start.slice(0, 16));
                  setConfirmed(false);
                  setRequestId(crypto.randomUUID());
                }}
              >
                Use next restriction start as requested UTC passage
              </Button>
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
                transit, and confirm {zone ?? "the unavailable local zone"} as
                the geographic local-zone assumption. Actual water level,
                clearance, route suitability and opening are unverified.
              </label>
              <Button
                size="sm"
                disabled={!confirmed || !passage || !zone || save.isPending}
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
              {plan?.sourceFamily === "NAVCEN_MSI" ? (
                <p>
                  Saved bridge request {formatUtc(plan.passageAt)} · assumed
                  onward travel {plan.postPassageHours} h.
                </p>
              ) : null}
              <Button
                size="sm"
                disabled={!relation?.calculable || compare.isPending}
                onClick={() => compare.mutate()}
              >
                Compare selected restriction passage windows
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
          <details>
            <summary>
              Supported families, geography and source-use limits
            </summary>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all">
              {JSON.stringify(q.data?.sourceRegistry, null, 2)}
            </pre>
          </details>
        </>
      ) : (
        <p>
          No source events available. Collection failure or an empty product
          does not establish non-occurrence.
        </p>
      )}
      {save.isError || compare.isError || nextCall.isError || lead.isError ? (
        <p role="alert">
          {save.error?.message ??
            compare.error?.message ??
            nextCall.error?.message ??
            lead.error?.message}
        </p>
      ) : null}
      {original.isError ? (
        <p role="alert">Original unavailable: {original.error.message}</p>
      ) : null}
    </details>
  );
}
