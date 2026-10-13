import { lazy, Suspense, useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Camera,
  ChevronRight,
  CloudSun,
  Globe2,
  Newspaper,
  TrendingUp,
} from "lucide-react";
import {
  normalizeFeedType,
  isVideoFeedType,
} from "gods-eye-view/sources/cctv-types";
import { useAuth, useWorkspace } from "@/auth/AuthProvider";
import { useWorld } from "@/world/WorldContext";
import { useWorldClock } from "@/services/lenses";
import {
  useIntelligence,
  useRegisterCamera,
  type IntelligenceContext,
  type PortCamera,
  type WeatherInspection,
} from "@/services/intelligence";
import "./intelligence.css";

const Globe = lazy(() => import("./IntelligenceGlobe"));
const TABS = [
  { id: "news", label: "Events", icon: Newspaper },
  { id: "economics", label: "Economics", icon: TrendingUp },
  { id: "weather", label: "Forecasts", icon: CloudSun },
  { id: "cameras", label: "Cameras", icon: Camera },
] as const;
type Tab = (typeof TABS)[number]["id"];
const format = (value: number | null) =>
  value == null ? "Pending" : value.toFixed(1);
const time = (value: string | null) =>
  value
    ? new Date(value).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "Unavailable";

export default function IntelligenceWorkspace({
  onClose,
  initialPort,
}: {
  onClose(): void;
  initialPort?: string | null;
}) {
  const world = useWorld();
  const clock = useWorldClock();
  const { identityHeaders, session } = useAuth();
  const { role, portCode: authorityPort } = useWorkspace();
  const [tab, setTab] = useState<Tab>("news");
  const [quakes, setQuakes] = useState(false);
  const [port, setPort] = useState<string | null>(
    initialPort ?? world.portCode,
  );
  const [event, setEvent] = useState<string | null>(world.eventId);
  const [weatherVariable, setWeatherVariable] = useState("wind_speed");
  const context = useIntelligence(
    port,
    identityHeaders,
    weatherVariable,
    clock.data ? `${clock.data.mode}:${clock.data.anchor ?? ""}` : "unknown",
  );
  const selectPort = (code: string | null) => {
    setPort(code);
    setEvent(null);
    world.selectPort(code);
  };
  const selectEvent = (id: string) => {
    setEvent(id);
    world.selectEvent(id);
  };
  const canRegister =
    session?.mode === "production" &&
    (role === "NATIONAL_ADMIN" || role === "PORT_AUTHORITY") &&
    context.data?.clockMode === "LIVE" &&
    clock.data?.mode === "LIVE" &&
    !clock.isError;

  return (
    <section
      className="intel-workspace"
      aria-label="Global intelligence workspace"
      data-testid="intelligence-workspace"
    >
      <header className="intel-header">
        <button className="intel-back" onClick={onClose}>
          <ArrowLeft size={16} /> Shipping workspace
        </button>
        <div className="intel-title">
          <Globe2 size={20} />
          <div>
            <h1>Global intelligence</h1>
            <p>Worldwide signals. Local shipping consequence.</p>
          </div>
        </div>
        <div className="intel-clock">
          <span>{context.data?.clockMode ?? "Connecting"}</span>
          <time>
            {context.data ? time(context.data.asOf) : "Reading world clock"}
          </time>
        </div>
      </header>
      {context.isPending ? (
        <div className="intel-loading" role="status">
          <div className="intel-skeleton" />
          <p>Connecting events, economic context and port evidence…</p>
        </div>
      ) : context.isError ? (
        <div className="intel-loading" role="alert">
          <h2>Intelligence context unavailable</h2>
          <p>{context.error.message}</p>
          <button onClick={() => void context.refetch()}>
            Retry connection
          </button>
        </div>
      ) : context.data ? (
        <div className="intel-body">
          <aside className="intel-left" aria-label="Scope and sources">
            <label className="intel-field">
              Investigation scope
              <select
                value={port ?? ""}
                onChange={(e) => selectPort(e.target.value || null)}
                data-testid="intelligence-port-select"
              >
                <option value="">All {context.data.ports.length} ports</option>
                {context.data.ports.map((p) => (
                  <option key={p.code} value={p.code}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="intel-section-heading">Connected signals</div>
            <div className="intel-layer">
              <span>Port network</span>
              <b>{context.data.ports.length}</b>
            </div>
            <div className="intel-layer">
              <span>Reported events</span>
              <b>{context.data.news.events.length}</b>
            </div>
            <div className="intel-layer">
              <span>Economic series</span>
              <b>
                {context.data.economics.filter((q) => q.value !== null).length}{" "}
                / 3
              </b>
            </div>
            <div className="intel-layer">
              <span>Registered cameras</span>
              <b>{context.data.cameras.length}</b>
            </div>
            <label className="intel-layer intel-check">
              <span>
                Global earthquakes <small>USGS · observed</small>
              </span>
              <input
                type="checkbox"
                checked={quakes}
                disabled={context.data.clockMode !== "LIVE"}
                onChange={(e) => setQuakes(e.target.checked)}
              />
            </label>
            <div className="intel-learning-summary">
              <CloudSun size={19} />
              <h2>Weather learning</h2>
              <strong>
                {context.data.weatherFeedback.resolved}
                <span> resolved forecasts</span>
              </strong>
              <p>
                {context.data.weatherFeedback.pending} waiting for verified
                outcomes.
              </p>
              <button onClick={() => setTab("weather")}>
                Inspect forecast errors <ChevronRight size={14} />
              </button>
            </div>
            <div className="intel-source-note">
              <p>
                Each signal keeps its source and timestamp. A global event
                becomes a shipping recommendation through the existing exposure
                and decision engine.
              </p>
            </div>
            <details className="intel-integration">
              <summary>Integration coverage</summary>
              <p>
                Using{" "}
                <a
                  href={context.data.integration.repository}
                  target="_blank"
                  rel="noreferrer"
                >
                  God’s Eye View
                </a>
                , MIT code. Revision{" "}
                {context.data.integration.revision.slice(0, 8)}.
              </p>
              <p>
                Connected: {context.data.integration.implemented.join(", ")}.
              </p>
              <p>
                Next adapters: {context.data.integration.pending.join(", ")}.
              </p>
            </details>
          </aside>
          <main className="intel-scene" aria-label="Global scene">
            <Suspense
              fallback={
                <div className="intel-scene-message" role="status">
                  Loading globe renderer…
                </div>
              }
            >
              <Globe
                context={context.data}
                portCode={port}
                eventId={event}
                earthquakes={quakes}
                headers={identityHeaders}
                onPort={(code) => selectPort(code)}
                onEvent={selectEvent}
              />
            </Suspense>
            <div className="intel-scene-key">
              <span className="intel-port-key">Ports</span>
              <span className="intel-event-key">Reported events</span>
              <span>Cameras</span>
            </div>
          </main>
          <aside className="intel-right" aria-label="Signal evidence">
            <div
              className="intel-tabs"
              role="tablist"
              aria-label="Evidence categories"
            >
              {TABS.map((t) => (
                <button
                  key={t.id}
                  role="tab"
                  id={`intel-tab-${t.id}`}
                  aria-selected={tab === t.id}
                  aria-controls={`intel-panel-${t.id}`}
                  tabIndex={tab === t.id ? 0 : -1}
                  onClick={() => setTab(t.id)}
                  onKeyDown={(e) => {
                    const index = TABS.findIndex((item) => item.id === t.id);
                    const next =
                      e.key === "ArrowRight"
                        ? (index + 1) % TABS.length
                        : e.key === "ArrowLeft"
                          ? (index + TABS.length - 1) % TABS.length
                          : e.key === "Home"
                            ? 0
                            : e.key === "End"
                              ? TABS.length - 1
                              : null;
                    if (next === null) return;
                    e.preventDefault();
                    setTab(TABS[next].id);
                    e.currentTarget.parentElement
                      ?.querySelectorAll<HTMLButtonElement>("[role=tab]")
                      [next]?.focus();
                  }}
                >
                  <t.icon size={16} />
                  <span>{t.label}</span>
                </button>
              ))}
            </div>
            <div
              className="intel-tab-content"
              role="tabpanel"
              id={`intel-panel-${tab}`}
              aria-labelledby={`intel-tab-${tab}`}
            >
              {tab === "news" ? (
                <NewsPanel
                  context={context.data}
                  eventId={event}
                  onSelect={selectEvent}
                  onDecide={() => {
                    world.setLens("INTELLIGENCE");
                    onClose();
                  }}
                />
              ) : null}
              {tab === "economics" ? (
                <EconomicsPanel context={context.data} />
              ) : null}
              {tab === "weather" ? (
                <WeatherPanel
                  context={context.data}
                  variable={weatherVariable}
                  onVariable={setWeatherVariable}
                />
              ) : null}
              {tab === "cameras" ? (
                <CameraPanel
                  context={context.data}
                  headers={identityHeaders}
                  canRegister={canRegister}
                  historical={
                    context.data.clockMode !== "LIVE" ||
                    clock.data?.mode !== "LIVE" ||
                    clock.isError
                  }
                  authorityPort={
                    role === "PORT_AUTHORITY" ? authorityPort : null
                  }
                />
              ) : null}
            </div>
            {context.isFetching ? (
              <div className="intel-refresh" role="status">
                Refreshing source context…
              </div>
            ) : null}
          </aside>
        </div>
      ) : null}
    </section>
  );
}

function NewsPanel({
  context,
  eventId,
  onSelect,
  onDecide,
}: {
  context: IntelligenceContext;
  eventId: string | null;
  onSelect(id: string): void;
  onDecide(): void;
}) {
  const event = context.news.events.find((e) => e.eventId === eventId);
  const impact = context.news.impacts.find((e) => e.eventId === eventId);
  return (
    <>
      <div className="intel-panel-heading">
        <h2>Events and shipping exposure</h2>
        <span>{context.news.status}</span>
      </div>
      {context.news.events.length === 0 ? (
        <Empty
          title="No events available in this scope"
          detail={
            context.news.reason ??
            "The current register has no reported events for this port or clock. Widen the scope to investigate."
          }
        />
      ) : null}
      {context.news.events.map((e) => (
        <button
          className={`intel-event-row ${eventId === e.eventId ? "selected" : ""}`}
          key={e.eventId}
          onClick={() => onSelect(e.eventId)}
        >
          <span>{e.categoryLabel}</span>
          <strong>{e.title}</strong>
          <small>
            {e.sources.length} source reports · {time(e.lastSeen)}
          </small>
        </button>
      ))}
      {event ? (
        <article className="intel-impact">
          <h3>Impact chain</h3>
          <p>{event.title}</p>
          <ol>
            <li>
              Reported event{" "}
              <small>
                {event.coordinates
                  ? "Location supplied by the event register"
                  : "Location unavailable"}
              </small>
            </li>
            <li>
              {impact?.lanes.length
                ? impact.lanes.map((l) => l.laneName).join(", ")
                : "No exposed trade lane established"}
            </li>
            <li>
              {impact?.ports.length
                ? impact.ports.map((p) => p.portCode).join(", ")
                : "No port exposure established"}
            </li>
          </ol>
          {impact?.actions.map((action, i) => (
            <p key={i} className="intel-action-note">
              {action.label}
            </p>
          ))}
          <p className="intel-muted">
            Structural exposure shows a connection. Delay and cost require a
            vessel, its timing and a simulated option.
          </p>
          <div className="intel-evidence-links">
            {event.sources.map((source, i) =>
              source.url && /^https?:\/\//.test(source.url) ? (
                <a key={i} href={source.url} target="_blank" rel="noreferrer">
                  {source.outlet} ↗
                </a>
              ) : (
                <span key={i}>{source.outlet}</span>
              ),
            )}
          </div>
          <button className="intel-primary" onClick={onDecide}>
            Open shipping decisions <ChevronRight size={14} />
          </button>
        </article>
      ) : null}
    </>
  );
}

function EconomicsPanel({ context }: { context: IntelligenceContext }) {
  return (
    <>
      <div className="intel-panel-heading">
        <h2>Economic context</h2>
        <span>FRED</span>
      </div>
      <p className="intel-muted">
        Global market context for fuel, settlement and operating costs. Quotes
        keep their observation dates.
      </p>
      {context.economics.map((q) => (
        <article className="intel-quote" key={q.id}>
          <div>
            <h3>{q.label}</h3>
            <span className={q.status === "STALE" ? "intel-stale" : ""}>
              {q.status}
            </span>
          </div>
          <strong>
            {q.value == null
              ? "Unavailable"
              : q.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            <small>{q.unit}</small>
          </strong>
          <p>
            {q.changePct == null
              ? "No previous observation"
              : `${q.changePct > 0 ? "+" : ""}${q.changePct.toFixed(2)}% from previous observation`}
          </p>
          <time>{time(q.observedAt)}</time>
          <p>{q.shippingConnection}</p>
          <a href={q.source} target="_blank" rel="noreferrer">
            View source series ↗
          </a>
        </article>
      ))}
      <p className="intel-muted">
        Realized voyage savings are unavailable until operational costs and
        outcomes are recorded.
      </p>
    </>
  );
}

function WeatherPanel({
  context,
  variable,
  onVariable,
}: {
  context: IntelligenceContext;
  variable: string;
  onVariable(value: string): void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const feedback = context.weatherFeedback;
  const rows = feedback.forecasts.filter((row) => row.variable === variable);
  const inspection = rows.find((row) => row.id === selected) ?? rows[0];
  return (
    <>
      <div className="intel-panel-heading">
        <h2>Forecast error inspection</h2>
        <span>Verified outcomes</span>
      </div>
      <p className="intel-muted">{feedback.note}</p>
      <label className="intel-field">
        Weather variable
        <select
          value={variable}
          onChange={(e) => {
            onVariable(e.target.value);
            setSelected(null);
          }}
        >
          <option value="wind_speed">Maximum wind</option>
          <option value="wind_gust">Maximum gust</option>
          <option value="rainfall">Daily rainfall</option>
          <option value="wave_height">Maximum wave height</option>
          <option value="visibility">Mean visibility</option>
        </select>
      </label>
      {typeof feedback.matchingForecasts === "number" &&
      feedback.matchingForecasts > rows.length ? (
        <p className="intel-muted">
          Showing the latest {rows.length} of {feedback.matchingForecasts}{" "}
          stored forecasts for this variable. Select a port to narrow the
          history.
        </p>
      ) : null}
      {rows.length === 0 ? (
        <Empty
          title="Collecting forecast snapshots"
          detail="The next successful weather refresh will record future daily forecasts for every port. Verification waits until the daily aggregate ends and a matching observation arrives."
        />
      ) : (
        <>
          <div className="intel-forecast-list">
            {rows.map((row) => (
              <button
                key={row.id}
                className={inspection?.id === row.id ? "selected" : ""}
                onClick={() => setSelected(row.id)}
              >
                <span>
                  {row.portCode} · +{row.horizonDays}d
                </span>
                <strong>{row.targetDate}</strong>
                <small>
                  {row.status === "resolved"
                    ? "Outcome available"
                    : "Awaiting observation"}
                </small>
              </button>
            ))}
          </div>
          {inspection ? <ForecastInspection row={inspection} /> : null}
        </>
      )}
      {feedback.scores
        .filter((row) => row.variable === variable)
        .map((score) => (
          <div
            className="intel-score"
            key={`${score.portCode}-${score.provider}-${score.horizonDays}`}
          >
            <strong>
              {score.portCode} · +{score.horizonDays}d · {score.samples} samples
            </strong>
            <span>
              MAE {score.rawMae.toFixed(2)} → {score.correctedMae.toFixed(2)}{" "}
              {score.unit}
            </span>
          </div>
        ))}
    </>
  );
}

function ForecastInspection({ row }: { row: WeatherInspection }) {
  return (
    <article className="intel-inspection" data-testid="forecast-inspection">
      <h3>
        {row.portCode} · {row.variable.replaceAll("_", " ")} · +
        {row.horizonDays} days
      </h3>
      <div className="intel-forecast-values">
        <div>
          <span>Original</span>
          <strong>{format(row.original)}</strong>
        </div>
        <div>
          <span>Corrected</span>
          <strong>{format(row.corrected)}</strong>
        </div>
        <div>
          <span>Observed</span>
          <strong>{format(row.observed)}</strong>
        </div>
      </div>
      <p>
        {row.unit} · {row.provider}
      </p>
      <dl>
        <dt>Retrieved</dt>
        <dd>{time(row.issuedAt)}</dd>
        <dt>Target ends</dt>
        <dd>{time(row.validAt)}</dd>
        <dt>Outcome source</dt>
        <dd>{row.observationSource ?? "Awaiting verified observation"}</dd>
      </dl>
      <h4>
        {row.correction.status} · {row.correction.sampleCount} independent
        targets
      </h4>
      <p>{row.correction.reason}</p>
      {row.low != null && row.high != null ? (
        <p>
          Empirical 80% residual interval: {row.low.toFixed(1)}–
          {row.high.toFixed(1)} {row.unit}
        </p>
      ) : (
        <p className="intel-muted">
          A learned uncertainty interval is not available yet.
        </p>
      )}
    </article>
  );
}

function CameraPanel({
  context,
  headers,
  canRegister,
  authorityPort,
  historical,
}: {
  context: IntelligenceContext;
  headers: Record<string, string>;
  canRegister: boolean;
  authorityPort: string | null;
  historical: boolean;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [registering, setRegistering] = useState(false);
  const camera =
    context.cameras.find((c) => c.id === selected) ?? context.cameras[0];
  return (
    <>
      <div className="intel-panel-heading">
        <h2>Port viewpoints</h2>
        <span>{context.cameras.length} registered</span>
      </div>
      <p className="intel-muted">
        Coverage belongs to each camera's visible area. A single viewpoint
        cannot establish conditions across a port.
      </p>
      {context.cameras.length === 0 ? (
        <Empty
          title="No camera feeds registered"
          detail="Connect public streams or feeds supplied by the port authority. No port CCTV coverage is assumed."
        />
      ) : null}
      {context.cameras.map((c) => (
        <button
          key={c.id}
          onClick={() => setSelected(c.id)}
          className={`intel-camera-row ${camera?.id === c.id ? "selected" : ""}`}
        >
          <Camera size={16} />
          <span>
            <strong>{c.name}</strong>
            <small>
              {c.portCode} · {c.viewpoint} · {c.health}
            </small>
          </span>
        </button>
      ))}
      {camera ? (
        <>
          <CameraMedia
            key={`${camera.id}-${context.clockMode}`}
            camera={camera}
            historical={historical}
          />
          <div className="intel-camera-coverage">
            <h3>Visible coverage</h3>
            <p>{camera.coverage}</p>
            <small>Pose: {camera.poseBasis.replaceAll("_", " ")}</small>
            <p>Source: {camera.source}</p>
            <p>{camera.healthNote}</p>
          </div>
          {context.cameraEvidence
            .filter((e) => e.cameraId === camera.id)
            .map((e) => (
              <article className="intel-camera-evidence" key={e.id}>
                <strong>{e.summary}</strong>
                <p>
                  {time(e.observedAt)} · {(e.confidence * 100).toFixed(0)}%
                  confidence
                </p>
                <span>
                  {e.operationalUse.replaceAll("_", " ")} ·{" "}
                  {e.method.replaceAll("_", " ")}
                </span>
                <small>{e.source}</small>
              </article>
            ))}
        </>
      ) : null}
      {canRegister ? (
        <>
          <button
            className="intel-primary"
            onClick={() => setRegistering(!registering)}
          >
            {registering ? "Close registration" : "Register camera viewpoint"}
          </button>
          {registering ? (
            <CameraForm
              context={context}
              headers={headers}
              authorityPort={authorityPort}
              onSaved={() => setRegistering(false)}
            />
          ) : null}
        </>
      ) : null}
      {!canRegister && context.clockMode === "LIVE" ? (
        <p className="intel-muted">
          Camera registration requires a verified authority account. Demo roles
          do not grant private camera access.
        </p>
      ) : null}
    </>
  );
}

function CameraMedia({
  camera,
  historical,
}: {
  camera: PortCamera;
  historical: boolean;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const [status, setStatus] = useState("Source timestamp unverified");
  const feedType = normalizeFeedType(camera.feedType);
  useEffect(() => {
    if (
      historical ||
      feedType !== "hls" ||
      !video.current ||
      !camera.enabled ||
      !camera.mediaUrl
    )
      return;
    const element = video.current;
    let disposed = false;
    let cleanup: (() => void) | undefined;
    if (element.canPlayType("application/vnd.apple.mpegurl")) {
      element.src = camera.mediaUrl;
      return () => {
        element.removeAttribute("src");
        element.load();
      };
    }
    void import("hls.js")
      .then(({ default: Hls }) => {
        if (disposed) return;
        if (!Hls.isSupported()) {
          setStatus("HLS playback is unavailable in this browser");
          return;
        }
        const player = new Hls();
        cleanup = () => player.destroy();
        player.on(Hls.Events.ERROR, (_event, data) => {
          if (data.fatal) setStatus("Camera stream is unavailable");
        });
        player.loadSource(camera.mediaUrl!);
        player.attachMedia(element);
      })
      .catch(() => setStatus("Camera player could not load"));
    return () => {
      disposed = true;
      cleanup?.();
      element.removeAttribute("src");
      element.load();
    };
  }, [feedType, camera.enabled, camera.mediaUrl, historical]);
  return (
    <div className="intel-camera-media">
      {historical ? (
        <Empty
          title="Live feed withheld during replay"
          detail="No archived camera media is available for this time. Current registry metadata is shown for reference."
        />
      ) : !camera.enabled || !camera.mediaUrl ? (
        <Empty
          title="Feed unconfigured"
          detail="This viewpoint has no active media URL."
        />
      ) : isVideoFeedType(feedType) ? (
        <video
          ref={video}
          src={feedType === "hls" ? undefined : camera.mediaUrl}
          controls
          muted
          playsInline
          preload="none"
          onError={() => setStatus("Camera stream is unavailable")}
          aria-label={camera.name}
        />
      ) : (
        <img
          src={camera.mediaUrl}
          alt={`${camera.name}: ${camera.coverage}`}
          referrerPolicy="no-referrer"
          onError={() => setStatus("Camera image is unavailable")}
        />
      )}
      <p role="status">{status}</p>
    </div>
  );
}

function CameraForm({
  context,
  headers,
  authorityPort,
  onSaved,
}: {
  context: IntelligenceContext;
  headers: Record<string, string>;
  authorityPort: string | null;
  onSaved(): void;
}) {
  const register = useRegisterCamera(headers);
  return (
    <form
      className="intel-camera-form"
      onSubmit={(e) => {
        e.preventDefault();
        const fields = new FormData(e.currentTarget);
        const code = String(fields.get("portCode"));
        const port = context.ports.find((p) => p.code === code)!;
        register.mutate(
          {
            id: String(fields.get("id")),
            portCode: code,
            name: String(fields.get("name")),
            lat: port.location.lat,
            lon: port.location.lon,
            poseBasis: "estimated",
            coverage: String(fields.get("coverage")),
            viewpoint: String(fields.get("viewpoint")),
            mediaUrl: String(fields.get("mediaUrl")).trim() || null,
            feedType: String(fields.get("feedType")),
            access: String(fields.get("access")),
            source: String(fields.get("source")),
            rightsBasis: String(fields.get("rightsBasis")),
            enabled: true,
          },
          { onSuccess: onSaved },
        );
      }}
    >
      <label className="intel-field">
        Port
        <select
          name="portCode"
          defaultValue={
            authorityPort ?? context.selectedPort ?? context.ports[0]?.code
          }
        >
          {context.ports
            .filter((p) => !authorityPort || authorityPort === p.code)
            .map((p) => (
              <option value={p.code} key={p.code}>
                {p.name}
              </option>
            ))}
        </select>
      </label>
      <label className="intel-field">
        Camera ID
        <input
          name="id"
          required
          pattern="[a-zA-Z0-9_-]{1,80}"
          placeholder="port-berth-camera-01"
        />
      </label>
      <label className="intel-field">
        Viewpoint name
        <input name="name" required maxLength={120} />
      </label>
      <label className="intel-field">
        Coverage description
        <textarea
          name="coverage"
          required
          maxLength={400}
          placeholder="Describe the quay, gate or approach visible in this feed"
        />
      </label>
      <label className="intel-field">
        Viewpoint
        <select name="viewpoint">
          <option>berth</option>
          <option>gate</option>
          <option>anchorage</option>
          <option>channel</option>
          <option>yard</option>
        </select>
      </label>
      <label className="intel-field">
        Feed URL
        <input name="mediaUrl" type="url" placeholder="https://" />
      </label>
      <label className="intel-field">
        Media type
        <select name="feedType">
          <option value="image">Image</option>
          <option value="mjpeg">MJPEG</option>
          <option value="mp4">MP4</option>
          <option value="webm">WebM</option>
          <option value="hls">HLS</option>
        </select>
      </label>
      <label className="intel-field">
        Who can view
        <select name="access">
          <option value="port_authority">
            Port authority and national command
          </option>
          <option value="public">All workspaces</option>
        </select>
      </label>
      <label className="intel-field">
        Source / feed owner
        <input name="source" required maxLength={200} />
      </label>
      <label className="intel-field">
        Permission or public licence basis
        <textarea name="rightsBasis" required maxLength={500} />
      </label>
      <p className="intel-muted">
        Initial marker uses the port's catalogued position, labelled estimated.
        Surveyed camera coordinates can be supplied through the registry API.
      </p>
      {register.isError ? <p role="alert">{register.error.message}</p> : null}
      <button
        className="intel-primary"
        type="submit"
        disabled={register.isPending}
      >
        {register.isPending ? "Saving viewpoint…" : "Save camera"}
      </button>
    </form>
  );
}

function Empty({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="intel-empty">
      <h3>{title}</h3>
      <p>{detail}</p>
    </div>
  );
}
