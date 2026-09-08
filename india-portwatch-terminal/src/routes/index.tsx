import { createFileRoute } from "@tanstack/react-router";
import { Navigate } from "@tanstack/react-router";

import { useAuth } from "@/auth/AuthProvider";
import { ROLE_PROFILE } from "@/auth/types";

export const Route = createFileRoute("/")({ component: RootRedirect });

/**
 * The address bar's front door. It resolves to whichever workspace the signed-in
 * role owns, so there is no "generic" screen that every role shares.
 */
function RootRedirect() {
  const { status, role } = useAuth();

  if (status === "restoring") {
    return (
      <div className="fixed inset-0 grid place-items-center bg-[var(--bg)]">
        <span className="flex items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-[var(--text-3)]">
          <span className="pw-breathe h-1.5 w-1.5 rounded-full bg-[var(--info)]" />
          Restoring session
        </span>
      </div>
    );
  }
  if (status === "authenticated" && role) {
    return <Navigate to={ROLE_PROFILE[role].home} replace />;
  }
  return <Navigate to="/login" replace />;
}
