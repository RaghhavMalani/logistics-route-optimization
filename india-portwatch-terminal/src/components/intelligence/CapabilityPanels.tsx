import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { Panel, Section } from "@/components/kit/layout";
import { Pill, formatUtc } from "@/components/kit/primitives";
import { Button } from "@/components/ui/button";
import { getJson } from "@/services/api";
import type { WeatherInspection, PortCamera } from "@/services/intelligence";
import { useRegisterCamera } from "@/services/intelligence";
import { WeatherVerificationPanel } from "./WeatherVerificationPanel";

interface Feedback {
  forecasts: WeatherInspection[];
  total: number;
  resolved: number;
  pending: number;
  note: string;
  scores: {
    portCode: string;
    variable: string;
    horizonDays: number;
    samples: number;
    independentTargets?: number;
    forecastSnapshots?: number;
    provider?: string;
    outcomeSource?: string;
    rawMae: number;
    correctedMae: number;
  }[];
}
interface Experiment {
  status: string;
  target?: string;
  promotion?: string;
  shadowInferenceAvailable?: boolean;
  scores?: {
    model: string;
    validationMae: number;
    testMae: number;
    coverage80: number;
  }[];
  test?: {
    name: string;
    meanReward: number;
    violations: number;
    rejectedActions: number;
    episodes: number;
  }[];
}
export function WeatherLearningPanel({ portCode }: { portCode?: string }) {
  const { identityHeaders } = useAuth();
  const [variable, setVariable] = useState("wind_speed");
  const result = useQuery({
    queryKey: ["weather-feedback", portCode, variable],
    queryFn: ({ signal }) =>
      getJson<Feedback>(
        `/weather/feedback?variable=${variable}${portCode ? `&portCode=${portCode}` : ""}&limit=100`,
        identityHeaders,
        { signal },
      ),
    staleTime: 30000,
  });
  return (
    <Panel
      title="Weather-error learning"
      note="Original → corrected → observed"
    >
      <Section title="Forecast inspection">
        <label className="text-xs">
          Variable{" "}
          <select
            aria-label="Weather feedback variable"
            value={variable}
            onChange={(e) => setVariable(e.target.value)}
            className="ml-2 bg-[var(--surface)]"
          >
            {[
              "wind_speed",
              "wind_gust",
              "rainfall",
              "wave_height",
              "visibility",
            ].map((v) => (
              <option key={v} value={v}>
                {v.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
        {result.isError ? (
          <p className="mt-2 text-xs">
            Weather archive unavailable.{" "}
            <button onClick={() => void result.refetch()}>Retry</button>
          </p>
        ) : null}
        {result.isPending ? (
          <p className="text-xs">Reading retained forecasts…</p>
        ) : null}
        {result.data ? (
          <>
            <WeatherVerificationPanel portCode={portCode} variable={variable} />
            <p className="my-2 text-[11px] text-[var(--text-3)]">
              {result.data.total} retained forecasts · {result.data.resolved}{" "}
              matched forecast snapshots. Independent target counts appear
              below. Corrections use only outcomes available before the forecast
              origin. Public forecast origins record receipt availability when
              provider issue time is unknown. Daily targets retain their units
              and statistic.
            </p>
            <div className="max-h-64 overflow-auto">
              <table className="w-full text-left text-[10.5px] num">
                <thead>
                  <tr>
                    {[
                      "Port / lead",
                      "Origin / target",
                      "Original",
                      "Corrected",
                      "Observed",
                      "Error: raw / corrected",
                      "Correction",
                    ].map((h) => (
                      <th
                        key={h}
                        className="p-1 font-normal text-[var(--text-3)]"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.data.forecasts.map((f) => (
                    <tr key={f.id} className="border-t border-[var(--line)]">
                      <td className="p-1">
                        {f.portCode} +{f.horizonDays}d<br />
                        {f.unit}
                      </td>
                      <td className="p-1">
                        {formatUtc(f.issuedAt)}
                        <br />
                        {f.targetDate}
                      </td>
                      <td className="p-1">{f.original.toFixed(2)}</td>
                      <td className="p-1">{f.corrected.toFixed(2)}</td>
                      <td className="p-1">
                        {f.observed?.toFixed(2) ?? "Pending"}
                        <br />
                        {f.observationSource}
                      </td>
                      <td className="p-1">
                        {f.observed == null
                          ? "Pending"
                          : `${(f.original - f.observed).toFixed(2)} / ${(f.corrected - f.observed).toFixed(2)}`}
                      </td>
                      <td className="p-1">
                        <span title={f.correction.reason}>
                          {f.correction.status}
                        </span>
                        <br />
                        {f.correction.sampleCount} outcomes
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!result.data.forecasts.length ? (
                <p className="py-3 text-xs">
                  No retained forecast matches this port and variable.
                </p>
              ) : null}
            </div>
            {result.data.scores.map((s) => (
              <p
                key={`${s.portCode}-${s.variable}-${s.provider}-${s.horizonDays}-${s.outcomeSource}`}
                className="text-[10.5px]"
              >
                {s.portCode} · {s.provider} · {s.outcomeSource} · +
                {s.horizonDays}d: raw MAE {s.rawMae.toFixed(2)} → corrected{" "}
                {s.correctedMae.toFixed(2)} ({s.independentTargets ?? s.samples}{" "}
                independent targets; {s.forecastSnapshots ?? s.samples}{" "}
                receipts)
              </p>
            ))}
            <p className="mt-2 text-[10.5px] text-[var(--text-3)]">
              {result.data.note} Signed error is forecast minus observed in the
              row's unit. Weather prediction error and operational-effect error
              are scored separately in the outcome ledger.
            </p>
          </>
        ) : null}
      </Section>
    </Panel>
  );
}

export function ModelExperimentsPanel() {
  const { identityHeaders } = useAuth();
  const q = useQuery({
    queryKey: ["model-experiments"],
    queryFn: ({ signal }) =>
      getJson<{
        neural_fusion: Experiment;
        constrained_rl: Experiment;
        freshness: Record<string, unknown>;
      }>("/learning/experiments", identityHeaders, { signal }),
  });
  return (
    <Panel
      title="Candidate models and policies"
      note="Measured experiments · operator review"
    >
      {q.isError ? (
        <Section title="Unavailable">
          <Button onClick={() => void q.refetch()}>Retry</Button>
        </Section>
      ) : null}
      {q.data ? (
        <>
          <Section title="Forecast freshness">
            <p className="text-[11px]">
              Generated {formatUtc(String(q.data.freshness.exportedAt ?? ""))} ·
              source {formatUtc(String(q.data.freshness.forecastOrigin ?? ""))}{" "}
              · {String(q.data.freshness.forecastOriginStatus)} ·{" "}
              {String(q.data.freshness.forecastOriginAgeHours)}h source age
            </p>
            <p className="text-[10.5px] text-[var(--text-3)]">
              Targets {String(q.data.freshness.targetFrom)} →{" "}
              {String(q.data.freshness.targetThrough)} ·{" "}
              {String(q.data.freshness.futureTargetDays ?? 0)} future days
              remaining · {String(q.data.freshness.targetStatus)}. A new export
              does not make an old source observation current.
            </p>
          </Section>
          <Section title="Neural specialist fusion">
            <Pill>{q.data.neural_fusion.status}</Pill>
            <p className="my-2 text-[10.5px]">
              {q.data.neural_fusion.target} · shadow inference{" "}
              {q.data.neural_fusion.shadowInferenceAvailable
                ? "available"
                : "pending"}
            </p>
            <table className="w-full text-[11px] num text-left">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Validation MAE</th>
                  <th>Test MAE</th>
                  <th>80% coverage</th>
                </tr>
              </thead>
              <tbody>
                {q.data.neural_fusion.scores?.map((s) => (
                  <tr key={s.model}>
                    <td>{s.model}</td>
                    <td>{s.validationMae}</td>
                    <td>{s.testMae}</td>
                    <td>{(s.coverage80 * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[10.5px] text-[var(--text-3)]">
              Training, validation, calibration and test targets are separated
              in time. The retained report describes the original rejected
              experiment. Revised training hides dropped specialists' inputs as
              well as their output weights; evaluation on a new chronological
              period is pending. Unarchived source ages, weather and regime
              vintages were excluded.
            </p>
          </Section>
          <Section title="Constrained sequential RL">
            <Pill>{q.data.constrained_rl.status}</Pill>
            <table className="w-full text-[11px] num text-left">
              <thead>
                <tr>
                  <th>Policy</th>
                  <th>Test reward</th>
                  <th>Violations / refused</th>
                </tr>
              </thead>
              <tbody>
                {q.data.constrained_rl.test?.map((s) => (
                  <tr key={s.name}>
                    <td>{s.name}</td>
                    <td>{s.meanReward}</td>
                    <td>
                      {s.violations} / {s.rejectedActions}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[10.5px] text-[var(--text-3)]">
              Separate scenario seeds for training, validation and test. Results
              measure this simulator. {q.data.constrained_rl.promotion}
            </p>
          </Section>
        </>
      ) : (
        <Section title="Reading experiments">
          <p className="text-xs">Loading candidate results…</p>
        </Section>
      )}
    </Panel>
  );
}

export function PortCameraPanel({ portCode }: { portCode: string }) {
  const { identityHeaders, session } = useAuth();
  const [open, setOpen] = useState(false);
  const register = useRegisterCamera(identityHeaders);
  const [draft, setDraft] = useState({
    id: "",
    name: "",
    lat: "",
    lon: "",
    mediaUrl: "",
    coverage: "",
    source: "",
    rightsBasis: "",
  });
  const q = useQuery({
    queryKey: ["camera-evidence", portCode],
    queryFn: ({ signal }) =>
      getJson<{
        cameras: PortCamera[];
        evidence: {
          id: string;
          observedAt: string;
          summary: string;
          coverage: string;
          operationalUse: string;
        }[];
      }>(`/intelligence/cameras?portCode=${portCode}`, identityHeaders, {
        signal,
      }),
    enabled: open,
  });
  return (
    <div className="absolute bottom-[150px] right-3 z-30 pointer-events-auto">
      <Button
        size="sm"
        variant="outline"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        Camera evidence
      </Button>
      {open ? (
        <div className="absolute bottom-10 right-0 w-[min(440px,85vw)] max-h-[65vh] overflow-auto rounded border border-[var(--line)] bg-[var(--panel)] shadow-xl p-3">
          <div className="flex justify-between mb-3">
            <strong className="text-xs">
              {portCode} · Authorized viewpoints
            </strong>
            <button
              aria-label="Close camera evidence"
              onClick={() => setOpen(false)}
            >
              ×
            </button>
          </div>
          {q.isPending ? (
            <p className="text-xs">Reading camera register…</p>
          ) : null}
          {q.isError ? (
            <p className="text-xs">Camera register unavailable.</p>
          ) : null}
          {q.data && !q.data.cameras.length ? (
            <p className="text-xs text-[var(--text-3)]">
              No authorized camera is configured for this{" "}
              {session?.mode === "demo" ? "visitor’s demo" : "port"}.
              Fixed-viewpoint CV accepts timestamped local frames, an empty
              reference, coverage and reviewed occupancy labels. Results stay
              unavailable until footage is supplied.
            </p>
          ) : null}
          {q.data?.cameras.map((c) => (
            <div key={c.id} className="my-3 text-xs">
              <strong>{c.name}</strong> <Pill>{c.health}</Pill>
              <p>{c.coverage}</p>
              <p className="text-[var(--text-3)]">
                {c.rightsBasis} · pose {c.poseBasis} ·{" "}
                {c.lastFrameAt ?? "Frame timestamp unverified"}
              </p>
              {c.mediaUrl && c.enabled ? (
                c.feedType === "image" ? (
                  <img
                    src={c.mediaUrl}
                    alt={c.name}
                    className="w-full"
                    referrerPolicy="no-referrer"
                  />
                ) : c.feedType === "mp4" || c.feedType === "webm" ? (
                  <video src={c.mediaUrl} controls className="w-full" />
                ) : (
                  <a href={c.mediaUrl} target="_blank" rel="noreferrer">
                    Open authorized feed
                  </a>
                )
              ) : null}
            </div>
          ))}
          {q.data?.evidence.map((e) => (
            <div key={e.id} className="text-xs my-3">
              <Pill>{e.operationalUse}</Pill>
              <p>{e.summary}</p>
              <p>
                {formatUtc(e.observedAt)} · {e.coverage}
              </p>
            </div>
          ))}
          {session?.mode === "production" ? (
            <form
              className="mt-3 border-t border-[var(--line)] pt-3 text-xs"
              onSubmit={(e) => {
                e.preventDefault();
                void register
                  .mutateAsync({
                    ...draft,
                    portCode,
                    lat: Number(draft.lat),
                    lon: Number(draft.lon),
                    mediaUrl: draft.mediaUrl || null,
                    viewpoint: "berth",
                    feedType: "image",
                    access: "port_authority",
                    poseBasis: "operator_supplied",
                  })
                  .then(() => q.refetch())
                  .catch(() => undefined);
              }}
            >
              <strong>Register an authorized viewpoint</strong>
              <p className="my-2 text-[var(--text-3)]">
                A registration retains your coverage and permission basis.
                Stream health and computer-vision accuracy remain unverified.
              </p>
              {(Object.keys(draft) as (keyof typeof draft)[]).map((key) => (
                <label key={key} className="block my-2">
                  {
                    {
                      id: "Camera id",
                      name: "Name",
                      lat: "Latitude",
                      lon: "Longitude",
                      mediaUrl: "HTTPS image feed (optional)",
                      coverage: "Visible coverage",
                      source: "Source / operator",
                      rightsBasis: "Permission basis",
                    }[key]
                  }
                  <input
                    required={key !== "mediaUrl"}
                    value={draft[key]}
                    onChange={(e) =>
                      setDraft({ ...draft, [key]: e.target.value })
                    }
                    type={
                      key === "mediaUrl"
                        ? "url"
                        : key === "lat" || key === "lon"
                          ? "number"
                          : "text"
                    }
                    step="any"
                    className="block mt-1 w-full border border-[var(--line)] rounded bg-[var(--surface)] p-1.5"
                  />
                </label>
              ))}
              <Button size="sm" type="submit" disabled={register.isPending}>
                Register viewpoint
              </Button>
              {register.isError ? (
                <p className="mt-2">
                  Registration failed. Check the fields and this account’s port
                  membership.
                </p>
              ) : null}
            </form>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
