import { useNavigate } from "@tanstack/react-router";
import { Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useAuth, useWorkspace } from "@/auth/AuthProvider";
import { ROLE_PROFILE, ROLES, type Role } from "@/auth/types";
import { useDemonstrationCatalogue } from "@/components/intelligence/DemonstrationScenarios";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { usePortRegistry, useScenarios } from "@/services/hooks";
import type { ScenarioDefinition } from "@/types/portwatch";
import { NAVIGATION } from "./navigation";
import { useTraffic } from "./traffic-context";
import { requestS10Command } from "./use-workspace-target";

export function WorkspaceCommandPalette() {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const [scenario, setScenario] = useState<ScenarioDefinition | null>(null);
  const [switchError, setSwitchError] = useState(false);
  const { role, profile } = useWorkspace();
  const { session, switchDemo, setViewAs } = useAuth();
  const navigate = useNavigate();
  const { source } = useTraffic();
  const { data: ports } = usePortRegistry();
  const { data: scenarios } = useScenarios(open);
  const companyDemo = role === "SHIPPING_COMPANY" && session?.mode === "demo";
  const { data: demo } = useDemonstrationCatalogue(open && companyDemo);
  useEffect(() => {
    const handle = (event: KeyboardEvent) => {
      if (
        !(event.metaKey || event.ctrlKey) ||
        event.shiftKey ||
        event.altKey ||
        event.key.toLowerCase() !== "k"
      )
        return;
      event.preventDefault();
      setOpen((value) => !value);
    };
    document.addEventListener("keydown", handle);
    return () => document.removeEventListener("keydown", handle);
  }, []);

  const hulls = useMemo(() => {
    const search = term.trim().toLowerCase();
    if (!open || search.length < 2) return [];
    const scoped = role === "SHIPPING_COMPANY" || role === "VESSEL_OPERATOR";
    return source
      .roster()
      .filter(
        (row) =>
          (!scoped || row.owned) &&
          [row.name, row.replayId].some((value) =>
            value.toLowerCase().includes(search),
          ),
      )
      .slice(0, 12);
  }, [open, role, source, term]);
  const change = (next: boolean) => {
    setOpen(next);
    if (!next) {
      setTerm("");
      setScenario(null);
      setSwitchError(false);
    }
  };
  const go = (href: string) => {
    change(false);
    void navigate({ href });
  };
  const target = (
    key: string,
    value: string,
    route = profile.home,
    run = false,
  ) => {
    const command = String(Date.now());
    if (run) requestS10Command(command);
    go(`${route}?${new URLSearchParams({ [key]: value, command })}`);
  };
  const changeRole = async (next: Role) => {
    if (session?.mode === "demo") {
      try {
        await switchDemo(next);
        change(false);
      } catch {
        setSwitchError(true);
      }
    } else {
      setViewAs(next);
      go(ROLE_PROFILE[next].home);
    }
  };

  return (
    <Dialog open={open} onOpenChange={change}>
      <DialogTrigger asChild>
        <button
          type="button"
          aria-label="Open command palette"
          aria-keyshortcuts="Meta+K Control+K"
          className="flex items-center gap-1 rounded border border-[var(--line)] px-1.5 py-0.5 text-xs text-[var(--text-2)]"
        >
          <Search size={13} aria-hidden="true" />
          <kbd className="hidden sm:inline">⌘K</kbd>
        </button>
      </DialogTrigger>
      <DialogContent className="gap-0 overflow-hidden bg-[var(--panel)] p-0">
        <DialogTitle className="px-3 pt-3 text-sm">Command palette</DialogTitle>
        <DialogDescription className="px-3 pb-2 text-xs text-[var(--text-3)]">
          Open a workspace page or search for a port, hull or scenario.
        </DialogDescription>
        {switchError ? (
          <p role="status" className="px-3 pb-2 text-xs">
            Role switch failed. Try again.
          </p>
        ) : null}
        {scenario ? (
          <section className="border-t border-[var(--line)] p-3">
            <p className="eyebrow">Modelled scenario</p>
            <h3 className="my-1 font-semibold">{scenario.name}</h3>
            <p className="text-sm">{scenario.desc}</p>
            <p className="mt-1 text-sm">{scenario.question}</p>
            <button
              type="button"
              className="mt-3 text-sm underline"
              onClick={() => setScenario(null)}
            >
              Back to search
            </button>
          </section>
        ) : (
          <Command loop className="bg-[var(--panel)] text-[var(--text)]">
            <CommandInput
              value={term}
              onValueChange={setTerm}
              placeholder="Pages, ports, hulls, scenarios"
            />
            <CommandList>
              <CommandEmpty>No matching results.</CommandEmpty>
              <CommandGroup heading="Navigation">
                {NAVIGATION[role].map((item) => (
                  <CommandItem
                    key={item.to}
                    keywords={[item.hint]}
                    onSelect={() => go(item.to)}
                  >
                    <item.icon aria-hidden="true" />
                    {item.label}
                  </CommandItem>
                ))}
                <CommandItem value="Research" onSelect={() => go("/research")}>
                  Research
                </CommandItem>
              </CommandGroup>
              {session?.mode === "demo" ||
              session?.user.role === "NATIONAL_ADMIN" ? (
                <CommandGroup heading="Switch role">
                  {ROLES.filter((next) => next !== role).map((next) => (
                    <CommandItem
                      key={next}
                      keywords={["role", next]}
                      onSelect={() => void changeRole(next)}
                    >
                      {ROLE_PROFILE[next].label}
                    </CommandItem>
                  ))}
                </CommandGroup>
              ) : null}
              {term.trim().length >= 2 ? (
                <>
                  <CommandGroup heading="Ports">
                    {ports
                      ?.filter((port) => port.location)
                      .map((port) => (
                        <CommandItem
                          key={port.code}
                          value={port.short}
                          keywords={[port.name, port.code]}
                          onSelect={() => target("port", port.code)}
                        >
                          {port.name} · {port.code}
                        </CommandItem>
                      ))}
                  </CommandGroup>
                  <CommandGroup heading="Hulls">
                    {hulls.map((hull) => (
                      <CommandItem
                        key={hull.id}
                        keywords={[hull.replayId]}
                        onSelect={() => target("hull", hull.id)}
                      >
                        {hull.name}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                  <CommandGroup heading="Scenarios">
                    {demo?.scenarios.map((row) => (
                      <CommandItem
                        key={row.id}
                        onSelect={() => target("scenario", row.id)}
                      >
                        {row.id} · {row.title}
                      </CommandItem>
                    ))}
                    {demo?.scenarios.some((row) => row.id === "S10") ? (
                      <CommandItem
                        onSelect={() =>
                          target("scenario", "S10", profile.home, true)
                        }
                      >
                        Run S10 with fictional inputs
                      </CommandItem>
                    ) : null}
                    {scenarios?.map((row) => (
                      <CommandItem
                        key={row.key}
                        keywords={[row.key]}
                        onSelect={() =>
                          role === "NATIONAL_ADMIN"
                            ? target("scenario", row.key, "/admin/scenarios")
                            : setScenario(row)
                        }
                      >
                        {row.name}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </>
              ) : null}
            </CommandList>
          </Command>
        )}
      </DialogContent>
    </Dialog>
  );
}
