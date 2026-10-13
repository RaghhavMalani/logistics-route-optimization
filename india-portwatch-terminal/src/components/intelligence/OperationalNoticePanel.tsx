import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { getJson, postJson } from "@/services/api";
import { Button } from "@/components/ui/button";
import { formatUtc } from "@/components/kit/primitives";
import type { DecisionProblem } from "@/types/decisions";

interface Notice {
  revisionId?: string;
  noticeRef: string;
  title?: string;
  sourceStatus: string;
  status?: string;
  source: string;
  pdfSource?: string;
  publishedDate?: string;
  availableAt?: string;
  checkedAt: string;
  withdrawsAt?: string;
  area?: string;
  restriction?: string;
  unaffectedAlternative?: string;
  confirmation?: string;
  reason?: string;
  responseSha256?: string;
  pdfSha256?: string;
  windows: {
    start: string;
    end: string;
    closureStartDate: string;
    closureEndDate: string;
    firstOperationalTide: string;
    calculationSupported: boolean;
    reason?: string;
  }[];
}
interface Plan {
  id: string;
  passageAt: string;
  route: string[];
  postPassageHours: number;
}
interface Voyage {
  id: string;
  name: string;
  laneCode: string;
  portCode: string;
  cargo: string;
  declaredPassage?: Plan;
}

export function OperationalNoticePanel({
  onDecision,
}: {
  onDecision?: (p: DecisionProblem) => void;
}) {
  const { session, identityHeaders } = useAuth();
  const client = useQueryClient();
  const [vesselId, setVesselId] = useState("PWD-001");
  const [passageAt, setPassageAt] = useState("2026-10-15T11:00");
  const [hours, setHours] = useState(180);
  const [confirmed, setConfirmed] = useState(false);
  const [dimensions, setDimensions] = useState({
    loaM: 140,
    beamM: 19,
    draughtM: 6,
    airDraughtM: 25,
  });
  const [digest, setDigest] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["operational-notices", identityHeaders],
    queryFn: ({ signal }) =>
      getJson<{ notices: Notice[]; voyages: Voyage[]; meaning: string }>(
        "/intelligence/operational-notices",
        identityHeaders,
        { signal, timeoutMs: 60000 },
      ),
    enabled: session?.mode === "demo",
    staleTime: 60000,
    retry: 1,
  });
  const notice = q.data?.notices[0];
  const voyage = q.data?.voyages.find((v) => v.id === vesselId);
  const declare = useMutation({
    mutationFn: () =>
      postJson(
        "/intelligence/notice-passage-plan",
        {
          vesselId,
          areaId: "EASTHAM_80_LOCK",
          direction: "OUTBOUND",
          passageAt: passageAt + ":00Z",
          postPassageHours: hours,
          characteristics: dimensions,
          alternativeAccess: "NOT_VERIFIED",
          declarationConfirmed: confirmed,
        },
        identityHeaders,
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["operational-notices"] });
      void client.invalidateQueries({ queryKey: ["company"] });
    },
  });
  const compare = useMutation({
    mutationFn: () =>
      postJson<DecisionProblem>(
        "/intelligence/notice-comparison",
        { vesselId, revisionId: notice?.revisionId },
        identityHeaders,
      ),
    onSuccess: (p) => {
      void client.invalidateQueries({
        queryKey: ["saved-intelligence-comparisons"],
      });
      onDecision?.(p);
    },
  });
  const raw = useQuery({
    queryKey: ["notice-original", digest, identityHeaders],
    enabled: !!digest,
    queryFn: ({ signal }) =>
      getJson<{
        sha256: string;
        mediaType: string;
        response?: string;
        base64?: string;
      }>(`/intelligence/notice-evidence/${digest}`, identityHeaders, {
        signal,
      }),
  });
  if (session?.mode !== "demo") return null;
  return (
    <section
      className="mt-3 border border-[var(--line)] p-3 text-[11px] space-y-2"
      data-testid="operational-notice-panel"
    >
      <h3 className="text-xs">
        Published restriction → declared voyage → scheduled access
      </h3>
      {q.isPending ? (
        <p>Checking the authority's original notice…</p>
      ) : q.isError ? (
        <p role="alert">Authority source unavailable: {q.error.message}</p>
      ) : notice ? (
        <>
          <details open>
            <summary>
              {notice.noticeRef} · {notice.title} · {notice.sourceStatus} /{" "}
              {notice.status ?? "UNAVAILABLE"}
            </summary>
            <p>{notice.restriction ?? notice.reason}</p>
            <p>
              Area: {notice.area ?? "Unavailable"}. Publication{" "}
              {notice.publishedDate ?? "Unavailable"} (date precision) · first
              receipt {formatUtc(notice.availableAt ?? null)} · checked{" "}
              {formatUtc(notice.checkedAt)}.
            </p>
            <p>
              Withdrawal {formatUtc(notice.withdrawsAt ?? null)}.{" "}
              {notice.unaffectedAlternative}
            </p>
            {notice.windows.map((w) => (
              <p key={w.start}>
                Closed {w.closureStartDate}–{w.closureEndDate} · first published
                operational tide {formatUtc(w.firstOperationalTide)}.{" "}
                {!w.calculationSupported
                  ? `Calculation blocked: ${w.reason}`
                  : "Conditional scheduled access; actual slot and reopening unavailable."}
              </p>
            ))}
            <p>{notice.confirmation}</p>
            <a
              href={notice.pdfSource ?? notice.source}
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              Authority original
            </a>{" "}
            {notice.responseSha256 ? (
              <button
                className="underline"
                onClick={() => setDigest(notice.responseSha256!)}
              >
                Inspect retained index
              </button>
            ) : null}{" "}
            {notice.pdfSha256 ? (
              <button
                className="underline"
                onClick={() => setDigest(notice.pdfSha256!)}
              >
                Inspect retained notice PDF
              </button>
            ) : null}
          </details>
          <p>
            {q.data?.meaning} Vessel characteristics are declared inputs; this
            notice closes the stated lock for all vessels. They do not establish
            lock or canal clearance.
          </p>
          {onDecision && session.user.role === "SHIPPING_COMPANY" ? (
            <fieldset className="border border-[var(--line)] p-2 space-y-2">
              <legend>
                Declare the fictional voyage's actual planned lock route
              </legend>
              <label className="block">
                Voyage{" "}
                <select
                  aria-label="Restriction voyage"
                  value={vesselId}
                  onChange={(e) => {
                    setVesselId(e.target.value);
                    setConfirmed(false);
                  }}
                  className="bg-[var(--panel-2)]"
                >
                  {q.data?.voyages
                    .filter((v) => v.laneCode === "EUR_IND")
                    .map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name}
                      </option>
                    ))}
                </select>
              </label>
              <p>
                Manchester Ship Canal → Eastham 80-foot Lock (outbound) → Suez →{" "}
                {voyage?.portCode}. Cargo: {voyage?.cargo}. This future
                itinerary is a visitor declaration; the schematic map position
                is not used to assert exposure.
              </p>
              <label className="block">
                Requested passage (UTC){" "}
                <input
                  aria-label="Requested restriction passage UTC"
                  type="datetime-local"
                  value={passageAt}
                  onChange={(e) => {
                    setPassageAt(e.target.value);
                    setConfirmed(false);
                  }}
                  className="max-w-full bg-[var(--panel-2)]"
                />
              </label>
              <label className="block">
                Assumed onward travel (h){" "}
                <input
                  aria-label="Post-passage travel hours"
                  type="number"
                  min={24}
                  max={720}
                  value={hours}
                  onChange={(e) => {
                    setHours(Number(e.target.value));
                    setConfirmed(false);
                  }}
                  className="w-20 bg-[var(--panel-2)]"
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
                        aria-label={`Declared ${key}`}
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
                        className="w-16 bg-[var(--panel-2)]"
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
                I declare these fictional voyage inputs. Alternate-lock
                suitability/booking are unverified; onward duration is an
                assumption. Saving updates this visitor's requested destination
                arrival.
              </label>
              <Button
                size="sm"
                disabled={!confirmed || !passageAt || declare.isPending}
                onClick={() => declare.mutate()}
              >
                Save declared passage plan
              </Button>
              {voyage?.declaredPassage ? (
                <p>
                  Saved declaration: {voyage.declaredPassage.route.join(" → ")}{" "}
                  · {formatUtc(voyage.declaredPassage.passageAt)} · onward{" "}
                  {voyage.declaredPassage.postPassageHours} h.
                </p>
              ) : null}
              <Button
                size="sm"
                disabled={
                  !voyage?.declaredPassage ||
                  notice.sourceStatus !== "CURRENT" ||
                  notice.status !== "SCHEDULED" ||
                  compare.isPending
                }
                onClick={() => compare.mutate()}
              >
                Compare restriction passage windows
              </Button>
            </fieldset>
          ) : null}
        </>
      ) : null}
      {declare.isError || compare.isError ? (
        <p role="alert">{declare.error?.message ?? compare.error?.message}</p>
      ) : null}
      {digest ? (
        <details open className="max-h-52 overflow-auto">
          <summary>Retained original · {digest}</summary>
          {raw.isError ? (
            <p role="alert">Original unavailable.</p>
          ) : raw.data?.base64 ? (
            <a
              className="underline"
              download={`${digest}.pdf`}
              href={`data:application/pdf;base64,${raw.data.base64}`}
            >
              Download hash-verified original PDF
            </a>
          ) : (
            <pre className="whitespace-pre-wrap break-all">
              {raw.data?.response ?? "Loading original…"}
            </pre>
          )}
        </details>
      ) : null}
    </section>
  );
}
