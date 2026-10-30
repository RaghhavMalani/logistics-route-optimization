import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import * as Dialog from "@radix-ui/react-dialog";

type Panel = "layers" | "timeline";
type Access = {
  mobile: boolean;
  active: Panel | null;
  open: (panel: Panel, trigger: HTMLElement) => void;
  close: () => void;
  returnFocus: () => void;
};
const MapPanels = createContext<Access | null>(null);

/** One responsive panel owner. Map, selection and filter state stay mounted. */
export function MapPanelAccess({ children }: { children: ReactNode }) {
  const [mobile, setMobile] = useState(false);
  const [active, setActive] = useState<Panel | null>(null);
  const trigger = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 699px)");
    const update = () => {
      setMobile(query.matches);
      if (!query.matches) setActive(null);
    };
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  const open = useCallback((panel: Panel, element: HTMLElement) => {
    trigger.current = element;
    setActive(panel);
  }, []);
  const close = useCallback(() => setActive(null), []);
  const returnFocus = useCallback(() => {
    if (trigger.current?.isConnected) trigger.current.focus();
  }, []);
  const value = useMemo(
    () => ({ mobile, active, open, close, returnFocus }),
    [mobile, active, open, close, returnFocus],
  );
  return <MapPanels.Provider value={value}>{children}</MapPanels.Provider>;
}

export function useMapPanelAccess() {
  return useContext(MapPanels);
}

export function MobileMapPanel({
  panel,
  title,
  children,
}: {
  panel: Panel;
  title: string;
  children: ReactNode;
}) {
  const access = useMapPanelAccess();
  if (!access?.mobile) return null;
  return (
    <Dialog.Root
      open={access.active === panel}
      onOpenChange={(open) => {
        if (!open) access.close();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[100] bg-black/60" />
        <Dialog.Content
          data-testid={`mobile-map-${panel}`}
          className="fixed inset-x-3 top-[8vh] bottom-[8vh] z-[101] flex min-w-0 flex-col rounded border border-[var(--line-strong)] bg-[var(--panel)] text-sm shadow-2xl"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            access.returnFocus();
          }}
        >
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--line)] p-3">
            <Dialog.Title className="font-semibold">{title}</Dialog.Title>
            <Dialog.Close className="rounded border border-[var(--line-strong)] px-2 py-1 focus-visible:outline focus-visible:outline-2">
              Return to inspector
            </Dialog.Close>
          </div>
          <Dialog.Description className="px-3 pt-3 text-xs text-[var(--text-2)]">
            The selected vessel, option and map position are retained. These
            controls use the same workspace state.
          </Dialog.Description>
          <div className="min-h-0 flex-1 overflow-y-auto p-3 [overflow-wrap:anywhere]">
            {children}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
