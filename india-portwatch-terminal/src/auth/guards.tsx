/**
 * Route guards.
 *
 * Two components and nothing else, so there is exactly one place where the
 * question "may this person see this screen?" is answered:
 *
 *   RoleGuard   wraps a workspace layout; sends anonymous visitors to /login
 *               and out-of-scope roles to their own home.
 *   PublicOnly  wraps /login; sends an already-signed-in operator onward.
 */

import { Navigate, useRouterState } from "@tanstack/react-router";
import { useRef, type ReactNode } from "react";

import { useAuth } from "./AuthProvider";
import { ROLE_PROFILE, isRoleAllowed, type Role } from "./types";

function SessionCheck({ label }: { label: string }) {
  return (
    <div className="grid h-full w-full place-items-center bg-[var(--bg)]">
      <div className="flex items-center gap-2 text-[11px] tracking-[0.14em] text-[var(--text-3)] uppercase">
        <span className="pw-breathe h-1.5 w-1.5 rounded-full bg-[var(--info)]" />
        {label}
      </div>
    </div>
  );
}

export function RoleGuard({
  allow,
  children,
}: {
  allow: Role[];
  children: ReactNode;
}) {
  const { status, role } = useAuth();
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  /**
   * The address the visitor actually asked for.
   *
   * The layout stays mounted through the redirect, so by the time the guard
   * re-renders `pathname` is already `/login` and the return address would
   * point at the sign-in screen itself. Capture it on first render instead.
   */
  const requested = useRef(pathname);

  if (status === "restoring") return <SessionCheck label="Restoring session" />;
  if (status === "anonymous" || !role) {
    const next = requested.current;
    return (
      <Navigate
        to="/login"
        search={next && next !== "/" && !next.startsWith("/login") ? { next } : {}}
        replace
      />
    );
  }
  if (!allow.includes(role) || !isRoleAllowed(role, pathname)) {
    return <Navigate to={ROLE_PROFILE[role].home} replace />;
  }
  return <>{children}</>;
}

export function PublicOnly({ children }: { children: ReactNode }) {
  const { status, role } = useAuth();

  if (status === "restoring") return <SessionCheck label="Checking session" />;
  if (status === "authenticated" && role) {
    return <Navigate to={ROLE_PROFILE[role].home} replace />;
  }
  return <>{children}</>;
}

/**
 * Roles permitted into each workspace root.
 *
 * A shipping company reaches the vessel workspace because a fleet desk drills
 * into one of its own ships; it does not reach the port workspace, because a
 * carrier has no business inside a port authority's control room. National
 * command reaches everything, which is the only reason the "view as" switcher
 * can exist.
 */
export const VESSEL_ACCESS: Role[] = [
  "VESSEL_OPERATOR",
  "SHIPPING_COMPANY",
  "NATIONAL_ADMIN",
];
export const COMPANY_ACCESS: Role[] = ["SHIPPING_COMPANY", "NATIONAL_ADMIN"];
export const PORT_ACCESS: Role[] = ["PORT_AUTHORITY", "NATIONAL_ADMIN"];
export const ADMIN_ACCESS: Role[] = ["NATIONAL_ADMIN"];
