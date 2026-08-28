import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Panel, Chip, Bar, Sparkline } from "@/components/terminal/ui";
import { fetchPortSnapshot } from "@/services/ports";
import { listGatingWeights } from "@/services/modelService";
import { fetchModelPipelineStatuses } from "@/services/model";

export const Route = createFileRoute("/model")({
  validateSearch: (search: Record<string, unknown>) => ({
    port: typeof search.port === "string" ? search.port : "INMAA",
  }),
  component: ModelPage,
});

const sparks = [
  [0.3, 0.4, 0.5, 0.55, 0.6, 0.62, 0.65, 0.71],
  [0.5, 0.6, 0.62, 0.55, 0.5, 0.52, 0.58, 0.63],
  [0.4, 0.42, 0.48, 0.5, 0.55, 0.53, 0.56, 0.58],
  [0.3, 0.32, 0.35, 0.4, 0.42, 0.44, 0.44, 0.44],
  [0.4, 0.5, 0.6, 0.65, 0.7, 0.72, 0.75, 0.77],
  [0.5, 0.55, 0.6, 0.62, 0.65, 0.68, 0.7, 0.69],
  [0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.72, 0.74],
];

function ModelPage() {
  const { port: portQuery } = Route.useSearch();
  const portDataQuery = useQuery({
    queryKey: ["port", portQuery],
    queryFn: () => fetchPortSnapshot(portQuery),
    staleTime: 30_000,
  });

  const pipelineQuery = useQuery({
    queryKey: ["model-pipeline"],
    queryFn: fetchModelPipelineStatuses,
    staleTime: 60_000,
  });

  if (portDataQuery.isLoading || pipelineQuery.isLoading) {
    return (
      <div className="h-full grid place-items-center text-[var(--color-cyan)] text-[12px] tracking-[0.2em]">
        LOADING LIVE MODEL OUTPUTS...
      </div>
    );
  }

  if (
    portDataQuery.isError ||
    pipelineQuery.isError ||
    !portDataQuery.data ||
    !pipelineQuery.data
  ) {
    return (
      <div className="h-full grid place-items-center text-[var(--color-red)] text-[12px] tracking-[0.2em]">
        MODEL API UNAVAILABLE
      </div>
    );
  }

  const port = portDataQuery.data;
  const pipeline = pipelineQuery.data;
  const gatingWeights = listGatingWeights();

  return (
    <div className="h-full grid grid-rows-[auto_1fr_auto] gap-2">
      <Panel
        title={`AI PIPELINE · ${port.name.toUpperCase()} · WEATHER → NEWS/NLP → SAR/AIS → DEMAND → HSMM → TFT → DECISION`}
      >
        <div className="p-3 flex items-stretch gap-2">
          {pipeline.map((s, i) => (
            <div key={s.key} className="flex-1 panel p-2 relative">
              <div className="flex items-center justify-between">
                <span className="label-xs">{s.key}</span>
                <Chip
                  tone={
                    s.confidence > 0.85
                      ? "mint"
                      : s.confidence > 0.7
                        ? "cyan"
                        : "amber"
                  }
                >
                  {(s.confidence * 100).toFixed(0)}%
                </Chip>
              </div>
              <div className="text-[11px] text-[var(--color-foreground)] mt-1">
                {s.name}
              </div>
              <Sparkline
                data={sparks[i]}
                tone={s.score > 0.7 ? "red" : s.score > 0.5 ? "amber" : "mint"}
                height={28}
              />
              <div className="mt-1 text-[9px] text-[var(--color-muted-foreground)]">
                {s.effectOnForecast}
              </div>
              {i < pipeline.length - 1 && (
                <span className="absolute -right-[10px] top-1/2 -translate-y-1/2 text-[var(--color-cyan)] animate-blink">
                  ▶
                </span>
              )}
            </div>
          ))}
        </div>
      </Panel>

      <div className="min-h-0 grid grid-cols-[1.4fr_1fr] gap-2">
        <Panel title="EXPERT CHAIN · INPUT → EFFECT">
          <div className="p-2">
            <div className="grid grid-cols-[70px_1fr_1fr_60px_50px_80px] gap-2 label-xs px-1 pb-1 border-b border-[var(--color-line)]">
              <span>MODULE</span>
              <span>INPUT SIGNAL</span>
              <span>EFFECT ON FORECAST</span>
              <span className="text-right">SCORE</span>
              <span className="text-right">CONF</span>
              <span className="text-right">TS</span>
            </div>
            {pipeline.map((step) => (
              <div
                key={step.key}
                className="grid grid-cols-[70px_1fr_1fr_60px_50px_80px] gap-2 items-center px-1 py-1.5 border-b border-[var(--color-line)]/40 text-[10px]"
              >
                <Chip
                  tone={
                    step.key === "DEC"
                      ? "cyan"
                      : step.key === "HSMM"
                        ? "amber"
                        : step.key === "TFT"
                          ? "cyan"
                          : "muted"
                  }
                >
                  {step.key}
                </Chip>
                <span className="text-[var(--color-foreground)]">
                  {step.inputSignal}
                </span>
                <span className="text-[var(--color-muted-foreground)]">
                  {step.effectOnForecast}
                </span>
                <span className="text-right tabular-nums">
                  {step.score.toFixed(2)}
                </span>
                <span className="text-right tabular-nums text-[var(--color-cyan)]">
                  {step.confidence.toFixed(2)}
                </span>
                <span className="text-right tabular-nums text-[var(--color-muted-foreground)]">
                  {step.timestamp}
                </span>
              </div>
            ))}
          </div>
        </Panel>

        <div className="grid grid-rows-2 gap-2 min-h-0">
          <Panel title="MoE GATING WEIGHTS">
            <div className="p-3 space-y-1.5 text-[11px]">
              {gatingWeights.map(({ key, value }) => (
                <div
                  key={key}
                  className="grid grid-cols-[54px_1fr_40px] items-center gap-2"
                >
                  <span className="text-[var(--color-cyan)]">{key}</span>
                  <Bar value={value} tone="cyan" />
                  <span className="text-right tabular-nums">
                    {(value * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          </Panel>
          <Panel title="MODEL CARDS">
            <div className="p-3 text-[10px] space-y-1.5">
              <ModelCard
                n="tft-fusion-v4.2"
                p={["horizon=10d", "quantile=[.1,.5,.9]", "params=18.4M"]}
              />
              <ModelCard
                n="hsmm-regime-v3.1"
                p={["states=4", "dwell=Weibull", "fit=EM"]}
              />
              <ModelCard
                n="sar-detector-v2"
                p={["backbone=YOLO-v8", "mAP=0.81", "cloud-inv"]}
              />
              <ModelCard
                n="nlp-tone-v1.3"
                p={["encoder=xlm-r", "gdelt+reuters", "sent=[-1,+1]"]}
              />
            </div>
          </Panel>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2">
        <MiniModel
          label="INFER LATENCY"
          value="182"
          unit="ms"
          tone="mint"
          data={[210, 200, 195, 190, 188, 185, 182]}
        />
        <MiniModel
          label="THROUGHPUT"
          value="1.2k"
          unit="req/s"
          tone="cyan"
          data={[0.9, 1.0, 1.05, 1.1, 1.15, 1.18, 1.2]}
        />
        <MiniModel
          label="DRIFT (PSI)"
          value="0.09"
          tone="amber"
          data={[0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09]}
        />
        <MiniModel
          label="ENSEMBLE CONF."
          value="0.86"
          tone="cyan"
          data={[0.78, 0.8, 0.82, 0.83, 0.85, 0.86, 0.86]}
        />
      </div>
    </div>
  );
}
function ModelCard({ n, p }: { n: string; p: string[] }) {
  return (
    <div className="panel px-2 py-1.5">
      <div className="flex justify-between">
        <span className="text-[var(--color-cyan)]">{n}</span>
        <Chip tone="mint">HEALTHY</Chip>
      </div>
      <div className="text-[9px] text-[var(--color-muted-foreground)] flex flex-wrap gap-2 mt-0.5">
        {p.map((x) => (
          <span key={x}>{x}</span>
        ))}
      </div>
    </div>
  );
}
function MiniModel({
  label,
  value,
  unit,
  tone,
  data,
}: {
  label: string;
  value: string;
  unit?: string;
  tone: "cyan" | "mint" | "amber" | "red";
  data: number[];
}) {
  const toneCls: Record<string, string> = {
    cyan: "text-[var(--color-cyan)]",
    mint: "text-[var(--color-mint)]",
    amber: "text-[var(--color-amber)]",
    red: "text-[var(--color-red)]",
  };
  return (
    <div className="panel px-3 py-2">
      <div className="flex justify-between items-baseline">
        <span className="label-xs">{label}</span>
        <span className={"text-[16px] tabular-nums " + toneCls[tone]}>
          {value}
          {unit && (
            <span className="text-[10px] text-[var(--color-muted-foreground)] ml-1">
              {unit}
            </span>
          )}
        </span>
      </div>
      <Sparkline data={data} tone={tone} height={22} />
    </div>
  );
}
