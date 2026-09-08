import { Link } from "@tanstack/react-router";

import { useWorkspace } from "@/auth/AuthProvider";
import { Page, PageBody, PageHeader } from "@/components/kit/layout";
import { EmptyState } from "@/components/kit/states";
import { NAVIGATION } from "./navigation";

/**
 * An unknown address inside a workspace.
 *
 * Without this the shell renders with an empty content region, which reads as
 * a screen that failed to load rather than an address that does not exist.
 */
export function WorkspaceNotFound() {
  const { role, profile } = useWorkspace();

  return (
    <Page>
      <PageHeader title="Screen not found" context={<span>{profile.label} workspace</span>} />
      <PageBody>
        <EmptyState
          tone="warn"
          title="No screen at this address"
          detail={`Nothing is registered here in the ${profile.label} workspace.`}
          action={
            <div className="flex flex-wrap justify-center gap-2">
              {NAVIGATION[role].map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  className="rounded-[2px] border border-[var(--line-strong)] px-2.5 py-[5px] text-[11.5px] text-[var(--text-2)] hover:text-[var(--text)]"
                >
                  {item.label}
                </Link>
              ))}
            </div>
          }
        />
      </PageBody>
    </Page>
  );
}
