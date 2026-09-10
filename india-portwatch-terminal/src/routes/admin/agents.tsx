/**
 * The agent architecture, as a screen.
 *
 * Not a chat surface — that is the console, which floats over the operational
 * screens. This is the *documentation of the machine*: which agents exist, what
 * each is allowed to call, where the numbers come from, and exactly where the
 * line between proposing and executing sits.
 *
 * The tool catalogue is grouped by access level with the EXECUTE tools shown
 * last and marked. That grouping is the safety model made visible: an operator
 * auditing this product should be able to see, on one screen, that no agent can
 * reach an EXECUTE tool and why.
 */

import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

import { AgentConsole } from "@/components/agent/AgentConsole";
import { Page, PageBody, PageHeader, Panel, Section } from "@/components/kit/layout";
import { Pill, type Tone } from "@/components/kit/primitives";
import { ScreenFallback } from "@/components/kit/states";
import { cn } from "@/lib/utils";
import { useAgentArchitecture, useToolCatalogue } from "@/services/os-hooks";
import type { ToolAccess } from "@/types/portwatch-os";

export const Route = createFileRoute("/admin/agents")({ component: AgentsScreen });

const ACCESS_TONE: Record<ToolAccess, Tone> = {
  READ: "info",
  SIMULATE: "unc",
  PROPOSE: "warn",
  EXECUTE: "crit",
};

const ACCESS_ORDER: ToolAccess[] = ["READ", "SIMULATE", "PROPOSE", "EXECUTE"];

function AgentsScreen() {
  const architecture = useAgentArchitecture();
  const catalogue = useToolCatalogue("EXECUTE");
  const [openAgent, setOpenAgent] = useState<string | null>(null);
  const [openTool, setOpenTool] = useState<string | null>(null);

  if (architecture.isLoading || architecture.isError) {
    return (
      <ScreenFallback
        title="Agents"
        context={<span>Orchestration, tools and the approval boundary</span>}
        isLoading={architecture.isLoading}
        error={architecture.error}
        retry={() => void architecture.refetch()}
        label="Reading the agent registry"
      />
    );
  }

  const data = architecture.data!;
  const tools = catalogue.data?.tools ?? [];

  return (
    <Page>
      <PageHeader
        title="Agents"
        context={<span>Orchestration, tools and the approval boundary</span>}
        meta={
          <>
            <span className="num">{data.agents.length} specialists</span>
            <span className="num">{data.intents.length} intents</span>
            <span className="num">{tools.length} tools</span>
          </>
        }
      />

      <PageBody>
        <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="space-y-3">
            <Panel title="The boundary" testId="agent-boundary">
              <Section title="Who may do what">
                <p className="text-[10.5px] leading-relaxed text-[var(--text-2)]">
                  {data.boundary.note}
                </p>
                <div className="mt-2 space-y-1.5">
                  {ACCESS_ORDER.map((level) => {
                    const names = catalogue.data?.byAccess?.[level] ?? [];
                    return (
                      <div
                        key={level}
                        className={cn(
                          "rounded-[2px] border px-2 py-1.5",
                          level === "EXECUTE"
                            ? "border-[var(--crit)]/50 bg-[var(--crit-dim)]/15"
                            : "border-[var(--line)]",
                        )}
                      >
                        <div className="flex items-baseline gap-2">
                          <Pill tone={ACCESS_TONE[level]}>{level}</Pill>
                          <span className="num text-[10px] text-[var(--text-3)]">
                            {names.length} tools
                          </span>
                        </div>
                        <p className="mt-1 text-[10px] leading-snug text-[var(--text-3)]">
                          {catalogue.data?.boundary?.[level.toLowerCase()] ?? ""}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </Section>
            </Panel>

            <Panel title="Command agent">
              <Section title={data.command.name}>
                <p className="text-[10.5px] leading-relaxed text-[var(--text-2)]">
                  {data.command.purpose}
                </p>
                <div className="mt-1.5">
                  <Pill tone="warn">ceiling {data.command.maxAccess}</Pill>
                </div>
              </Section>
              <Section title="Intents">
                <ul className="space-y-1.5">
                  {data.intents.map((intent) => (
                    <li key={intent.key}>
                      <div className="flex items-baseline gap-2">
                        <span className="text-[11px] text-[var(--text)]">
                          {intent.label}
                        </span>
                        {intent.highImpact ? <Pill tone="warn">critic</Pill> : null}
                      </div>
                      <div className="num mt-[2px] text-[9.5px] text-[var(--text-3)]">
                        {intent.agents.join(" → ")}
                      </div>
                      <p className="mt-[2px] text-[9.5px] leading-snug text-[var(--text-3)]">
                        {intent.description}
                      </p>
                    </li>
                  ))}
                </ul>
              </Section>
            </Panel>

            <Panel title="Critic" testId="agent-critic-card">
              <Section title={data.critic.purpose}>
                <div className="flex flex-wrap gap-1">
                  {data.critic.verdicts.map((verdict) => (
                    <Pill
                      key={verdict}
                      tone={
                        verdict === "APPROVED"
                          ? "ok"
                          : verdict === "MODIFIED"
                            ? "unc"
                            : "crit"
                      }
                    >
                      {verdict}
                    </Pill>
                  ))}
                </div>
                <ul className="mt-1.5 space-y-0.5">
                  {data.critic.checks.map((check) => (
                    <li key={check} className="num text-[10px] text-[var(--text-3)]">
                      {check.replace(/_/g, " ")}
                    </li>
                  ))}
                </ul>
                <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--unc)]">
                  {data.critic.note}
                </p>
              </Section>
            </Panel>
          </div>

          <div className="space-y-3">
            <Panel title="Specialists" note={`${data.agents.length}`} testId="agent-list">
              {data.agents.map((agent) => (
                <div key={agent.name} className="border-b border-[var(--line)]/60 last:border-0">
                  <button
                    type="button"
                    onClick={() =>
                      setOpenAgent(openAgent === agent.name ? null : agent.name)
                    }
                    className="w-full px-2 py-1.5 text-left hover:bg-[var(--panel-2)]"
                  >
                    <div className="flex items-baseline gap-2">
                      <span className="text-[11.5px] font-medium uppercase tracking-[0.05em] text-[var(--text)]">
                        {agent.name.replace(/_/g, " ")}
                      </span>
                      <Pill tone={ACCESS_TONE[agent.maxAccess as ToolAccess] ?? "neutral"}>
                        {agent.maxAccess}
                      </Pill>
                      <span className="num ml-auto text-[9.5px] text-[var(--text-3)]">
                        {agent.allowedTools.length} tools
                      </span>
                    </div>
                    <p className="mt-[3px] text-[10.5px] leading-snug text-[var(--text-2)]">
                      {agent.purpose}
                    </p>
                  </button>
                  {openAgent === agent.name ? (
                    <div className="space-y-2 border-t border-[var(--line)]/60 bg-[var(--panel-2)]/40 px-3 py-2">
                      <section>
                        <h4 className="eyebrow text-[8.5px]">Allowed tools</h4>
                        <ul className="mt-1 space-y-0.5">
                          {agent.allowedTools.map((tool) => (
                            <li key={tool} className="num text-[9.5px] text-[var(--text-2)]">
                              {tool}
                            </li>
                          ))}
                        </ul>
                      </section>
                      <section>
                        <h4 className="eyebrow text-[8.5px]">Failure modes</h4>
                        <ul className="mt-1 space-y-0.5">
                          {agent.failureModes.map((mode) => (
                            <li
                              key={mode}
                              className="text-[9.5px] leading-snug text-[var(--text-3)]"
                            >
                              {mode}
                            </li>
                          ))}
                        </ul>
                      </section>
                    </div>
                  ) : null}
                </div>
              ))}
            </Panel>

            <Panel
              title="Tool catalogue"
              note={`${tools.length}`}
              testId="tool-catalogue"
              scroll
              className="max-h-[520px]"
            >
              {ACCESS_ORDER.map((level) => {
                const group = tools.filter((tool) => tool.access === level);
                if (!group.length) return null;
                return (
                  <Section
                    key={level}
                    title={level}
                    right={<Pill tone={ACCESS_TONE[level]}>{group.length}</Pill>}
                  >
                    {group.map((tool) => (
                      <div key={tool.name} className="border-b border-[var(--line)]/40 py-1 last:border-0">
                        <button
                          type="button"
                          onClick={() =>
                            setOpenTool(openTool === tool.name ? null : tool.name)
                          }
                          className="w-full text-left"
                        >
                          <div className="num text-[10.5px] text-[var(--text)]">
                            {tool.name}
                          </div>
                          <p className="mt-[2px] text-[9.5px] leading-snug text-[var(--text-3)]">
                            {tool.description}
                          </p>
                        </button>
                        {openTool === tool.name ? (
                          <div className="mt-1 space-y-1 rounded-[2px] bg-[var(--panel-2)]/50 p-1.5">
                            <div>
                              <span className="eyebrow text-[8px]">Computed by</span>
                              <div className="num text-[9.5px] text-[var(--text-2)]">
                                {tool.computedBy || "unstated"}
                              </div>
                            </div>
                            <div>
                              <span className="eyebrow text-[8px]">Returns</span>
                              <div className="text-[9.5px] text-[var(--text-3)]">
                                {tool.returns}
                              </div>
                            </div>
                            {Object.keys(tool.inputSchema.properties).length ? (
                              <div>
                                <span className="eyebrow text-[8px]">Arguments</span>
                                <ul className="space-y-0.5">
                                  {Object.entries(tool.inputSchema.properties).map(
                                    ([key, value]) => (
                                      <li key={key} className="text-[9.5px]">
                                        <span className="num text-[var(--text-2)]">
                                          {key}
                                        </span>
                                        {tool.inputSchema.required.includes(key) ? (
                                          <span className="ml-1 text-[8.5px] text-[var(--warn)]">
                                            required
                                          </span>
                                        ) : null}
                                        <span className="ml-1 text-[var(--text-3)]">
                                          {value.description}
                                        </span>
                                      </li>
                                    ),
                                  )}
                                </ul>
                              </div>
                            ) : null}
                            {tool.failureModes.length ? (
                              <div>
                                <span className="eyebrow text-[8px]">Fails when</span>
                                <ul className="space-y-0.5">
                                  {tool.failureModes.map((mode) => (
                                    <li
                                      key={mode}
                                      className="text-[9.5px] text-[var(--text-3)]"
                                    >
                                      {mode}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </Section>
                );
              })}
            </Panel>
          </div>
        </div>
      </PageBody>

      <div className="pointer-events-none absolute bottom-4 right-4 z-30">
        <AgentConsole />
      </div>
    </Page>
  );
}
