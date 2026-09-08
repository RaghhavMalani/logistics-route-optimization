/**
 * The application shell: one top bar, one rail, one content region.
 *
 * The shell is where a viewer learns three things without asking — who they are
 * signed in as, which context they are looking at, and how fresh the twin is.
 * Everything else belongs to the screen.
 */

import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { ChevronDown, LogOut, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { useAuth, useWorkspace } from "@/auth/AuthProvider";
import { ROLE_PROFILE, ROLES, type Role } from "@/auth/types";
import { Pill, ProvenanceTag, formatUtc } from "@/components/kit/primitives";
import { cn } from "@/lib/utils";
import { useHealth, usePorts } from "@/services/hooks";
import { NAVIGATION, activeNavItem } from "./navigation";

/* ----------------------------------------------------------------- clock -- */

function useUtcClock(): string {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  if (!now) return "--:--:--";
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}:${pad(now.getUTCSeconds())}`;
}

/* ------------------------------------------------------------------ menu -- */

function Menu({
  label,
  children,
  align = "right",
  width = 218,
}: {
  label: ReactNode;
  children: (close: () => void) => ReactNode;
  align?: "left" | "right";
  width?: number;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex items-center gap-1.5 rounded-[2px] px-2 py-[4px] text-[11.5px] transition-colors",
          open
            ? "bg-[var(--panel-3)] text-[var(--text)]"
            : "text-[var(--text-2)] hover:bg-[var(--panel-3)] hover:text-[var(--text)]",
        )}
      >
        {label}
        <ChevronDown size={11} className={cn("transition-transform", open && "rotate-180")} />
      </button>
      {open ? (
        <div
          role="menu"
          style={{ width }}
          className={cn(
            "pw-fade absolute top-[calc(100%+4px)] z-50 overflow-hidden rounded-[3px] border border-[var(--line-strong)]",
            "bg-[var(--panel)] shadow-[0_12px_32px_rgba(0,0,0,0.55)]",
            align === "right" ? "right-0" : "left-0",
          )}
        >
          {children(() => setOpen(false))}
        </div>
      ) : null}
    </div>
  );
}

/* --------------------------------------------------------------- top bar -- */

function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden>
        <path d="M12 2 L21 12 L12 22 L3 12 Z" fill="none" stroke="var(--info)" strokeWidth="1.5" />
        <path d="M12 7.5 L16.5 12 L12 16.5 L7.5 12 Z" fill="var(--info)" opacity="0.85" />
      </svg>
      <span className="text-[12.5px] font-semibold tracking-[0.055em] text-[var(--text)]">
        INDIA PORTWATCH
      </span>
    </div>
  );
}

function ContextCrumb() {
  const { profile, isImpersonating, portCode } = useWorkspace();
  const ports = usePorts();
  const port = ports.data?.find((p) => p.code === portCode);

  return (
    <div className="flex min-w-0 items-center gap-2 text-[11.5px]">
      <span className="text-[var(--text-3)]">/</span>
      <span className="truncate font-medium uppercase tracking-[0.07em] text-[var(--text-2)]">
        {profile.label}
      </span>
      {profile.role === "PORT_OPERATOR" && port ? (
        <>
          <span className="text-[var(--text-3)]">/</span>
          <span className="truncate uppercase tracking-[0.07em] text-[var(--text-2)]">
            {port.name}
          </span>
        </>
      ) : null}
      {isImpersonating ? <Pill tone="unc">Viewing as</Pill> : null}
    </div>
  );
}

function SystemState() {
  const health = useHealth();
  const clock = useUtcClock();
  const data = health.data;

  const tone =
    data?.intelligence === "live"
      ? "ok"
      : data?.intelligence === "cached"
        ? "info"
        : data?.intelligence === "stale"
          ? "warn"
          : "crit";

  return (
    <div className="flex items-stretch">
      <div className="flex flex-col justify-center border-l border-[var(--line)] px-3.5">
        <span className="eyebrow text-[9px]">Model run</span>
        <span className="num text-[11px] text-[var(--text-2)]">
          {formatUtc(data?.lastRefreshUtc ?? null)}
        </span>
      </div>
      <div className="flex flex-col justify-center border-l border-[var(--line)] px-3.5">
        <span className="eyebrow text-[9px]">Sources</span>
        <span className="num text-[11px] text-[var(--text-2)]">
          {data ? `${(data.sources.readiness * 100).toFixed(0)}% ready` : "—"}
        </span>
      </div>
      <div className="flex flex-col justify-center gap-[3px] border-l border-[var(--line)] px-3.5">
        <span className="eyebrow text-[9px]">Twin state</span>
        <span className="flex items-center gap-1">
          {health.isError ? (
            <Pill tone="crit">API down</Pill>
          ) : (
            <>
              <Pill tone={tone}>{(data?.intelligence ?? "…").replace("_", " ")}</Pill>
              <ProvenanceTag
                status={data?.forecastOriginStatus ?? null}
                ageHours={data?.forecastOriginAgeHours ?? null}
                detail={`Forecast origin ${formatUtc(data?.forecastOrigin ?? null)}`}
              />
            </>
          )}
        </span>
      </div>
      <div className="flex flex-col justify-center border-l border-[var(--line)] px-3.5">
        <span className="eyebrow text-[9px]">UTC</span>
        <span className="num text-[11px] text-[var(--text)]">{clock}</span>
      </div>
    </div>
  );
}

function RoleSwitcher() {
  const { role, viewAs, setViewAs } = useAuth();
  const navigate = useNavigate();
  if (role !== "ADMIN") return null;

  return (
    <Menu
      align="left"
      width={252}
      label={
        <span className="flex items-center gap-1.5">
          <span className="eyebrow text-[9px]">View as</span>
          <span className="font-medium">{ROLE_PROFILE[viewAs ?? "ADMIN"].label}</span>
        </span>
      }
    >
      {(close) => (
        <div className="p-1">
          {ROLES.map((option: Role) => {
            const profile = ROLE_PROFILE[option];
            const active = (viewAs ?? "ADMIN") === option;
            return (
              <button
                key={option}
                type="button"
                role="menuitem"
                onClick={() => {
                  setViewAs(option);
                  close();
                  void navigate({ to: profile.home });
                }}
                className={cn(
                  "block w-full rounded-[2px] px-2 py-1.5 text-left transition-colors",
                  active ? "bg-[var(--panel-3)]" : "hover:bg-[var(--panel-2)]",
                )}
              >
                <span
                  className={cn(
                    "text-[12px] font-medium",
                    active ? "text-[var(--info)]" : "text-[var(--text)]",
                  )}
                >
                  {profile.label}
                </span>
                <span className="mt-0.5 block text-[10.5px] leading-snug text-[var(--text-3)]">
                  {profile.description}
                </span>
              </button>
            );
          })}
          <p className="border-t border-[var(--line)] px-2 pb-1 pt-1.5 text-[10px] leading-snug text-[var(--text-3)]">
            Switching context changes the workspace only. Command-level access is
            retained.
          </p>
        </div>
      )}
    </Menu>
  );
}

function ProfileMenu() {
  const { session, signOut, mode } = useAuth();
  const navigate = useNavigate();
  const user = session?.user;
  if (!user) return null;

  const initials = user.displayName
    .split(/[\s.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");

  return (
    <Menu
      label={
        <span className="flex items-center gap-2">
          <span className="grid h-[21px] w-[21px] place-items-center rounded-[2px] bg-[var(--panel-4)] text-[10px] font-semibold text-[var(--text-2)]">
            {initials}
          </span>
          <span className="hidden max-w-[128px] truncate xl:inline">{user.displayName}</span>
        </span>
      }
    >
      {(close) => (
        <div>
          <div className="border-b border-[var(--line)] px-3 py-2.5">
            <div className="text-[12px] font-medium text-[var(--text)]">{user.displayName}</div>
            <div className="num mt-0.5 text-[10.5px] text-[var(--text-3)]">{user.email}</div>
            <div className="mt-1.5 text-[10.5px] leading-snug text-[var(--text-2)]">
              {user.organisation}
            </div>
            <div className="mt-2 flex items-center gap-1.5">
              <Pill tone="info">{ROLE_PROFILE[user.role].label}</Pill>
              <Pill tone={mode === "demo" ? "unc" : "ok"}>{mode} auth</Pill>
            </div>
          </div>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              close();
              void signOut().then(() => navigate({ to: "/login" }));
            }}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] text-[var(--text-2)] transition-colors hover:bg-[var(--panel-2)] hover:text-[var(--text)]"
          >
            <LogOut size={12} />
            Sign out
          </button>
        </div>
      )}
    </Menu>
  );
}

/* ------------------------------------------------------------------ rail -- */

function SideNav({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const { role } = useWorkspace();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const items = NAVIGATION[role];
  const active = activeNavItem(items, pathname);
  const health = useHealth();
  const sources = health.data?.sources;

  return (
    <nav
      aria-label="Workspace"
      className={cn(
        "flex shrink-0 flex-col border-r border-[var(--line)] bg-[var(--panel)] transition-[width] duration-150",
        collapsed ? "w-[52px]" : "w-[var(--nav-w)]",
      )}
    >
      <div className="flex-1 overflow-y-auto py-1.5">
        {items.map((item) => {
          const Icon = item.icon;
          const isActive = active?.to === item.to;
          return (
            <Link
              key={item.to}
              to={item.to}
              title={collapsed ? `${item.label} — ${item.hint}` : item.hint}
              className={cn(
                "relative flex items-center gap-2.5 px-3 py-[7px] text-[12.5px] transition-colors",
                isActive
                  ? "bg-[var(--panel-3)] text-[var(--text)]"
                  : "text-[var(--text-3)] hover:bg-[var(--panel-2)] hover:text-[var(--text-2)]",
              )}
            >
              {isActive ? (
                <span className="absolute inset-y-0 left-0 w-[2px] bg-[var(--info)]" />
              ) : null}
              <Icon size={14} strokeWidth={1.7} className="shrink-0" />
              {collapsed ? null : <span className="truncate">{item.label}</span>}
            </Link>
          );
        })}
      </div>

      {!collapsed && sources ? (
        <div className="border-t border-[var(--line)] px-3 py-2.5">
          <Link
            to="/admin/data"
            className="eyebrow mb-1.5 block hover:text-[var(--text-2)]"
          >
            Feed readiness
          </Link>
          <div className="mb-2 h-[3px] w-full overflow-hidden rounded-[1px] bg-[var(--panel-3)]">
            <div
              className="h-full bg-[var(--info)]"
              style={{ width: `${sources.readiness * 100}%` }}
            />
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-[3px] text-[10.5px]">
            {(
              [
                ["Live", sources.live.length, "var(--ok)"],
                ["Cached", sources.cached.length, "var(--info)"],
                ["Stale", sources.stale.length, "var(--warn)"],
                ["Missing", sources.unavailable.length, "var(--crit)"],
              ] as const
            ).map(([label, count, color]) => (
              <span key={label} className="flex items-center justify-between gap-1">
                <span style={{ color }}>{label}</span>
                <span className="num text-[var(--text-3)]">{count}</span>
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <button
        type="button"
        onClick={onToggle}
        aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
        className="flex h-[30px] shrink-0 items-center gap-2 border-t border-[var(--line)] px-3.5 text-[var(--text-3)] transition-colors hover:text-[var(--text-2)]"
      >
        {collapsed ? <PanelLeftOpen size={13} /> : <PanelLeftClose size={13} />}
        {collapsed ? null : <span className="text-[11px]">Collapse</span>}
      </button>
    </nav>
  );
}

/* ----------------------------------------------------------------- shell -- */

export function AppShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);

  // 1366×768 is a supported operating resolution, and the rail costs 208px of
  // it. Start collapsed there and let the operator open it.
  useEffect(() => {
    const query = window.matchMedia("(max-width: 1439px)");
    const apply = () => setCollapsed(query.matches);
    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, []);

  return (
    <div className="fixed inset-0 flex flex-col bg-[var(--bg)]">
      <header className="flex h-[var(--topbar-h)] shrink-0 items-stretch border-b border-[var(--line)] bg-[var(--panel)]">
        <div className="flex min-w-0 flex-1 items-center gap-3 pl-4">
          <Brand />
          <ContextCrumb />
          <div className="ml-1">
            <RoleSwitcher />
          </div>
        </div>
        <SystemState />
        <div className="flex items-center border-l border-[var(--line)] px-2">
          <ProfileMenu />
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <SideNav collapsed={collapsed} onToggle={() => setCollapsed((v) => !v)} />
        <main className="min-h-0 min-w-0 flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
