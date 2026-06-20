import {
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  FolderOpen,
  MessageSquare,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
} from "lucide-react";
import { Sidebar } from "@/components/Sidebar";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SearchPanel, type SearchPanelHandle } from "@/components/SearchPanel";
import { ChatPanel } from "@/components/ChatPanel";
import { LibraryPanel } from "@/components/LibraryPanel";
import { GraphPanel } from "@/components/GraphPanel";
import { useChatWorkspace } from "@/hooks/useChatWorkspace";

type TabKey = "search" | "chat" | "library" | "graph";

const SIDEBAR_WIDTH_KEY = "dante-dashboard-sidebar-width";
const SIDEBAR_COLLAPSED_KEY = "dante-dashboard-sidebar-collapsed";

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function readStoredNumber(key: string, fallback: number, min: number, max: number) {
  if (typeof window === "undefined") return fallback;
  const stored = Number(window.localStorage.getItem(key));
  return Number.isFinite(stored) ? clamp(stored, min, max) : fallback;
}

function readStoredBoolean(key: string, fallback: boolean) {
  if (typeof window === "undefined") return fallback;
  const stored = window.localStorage.getItem(key);
  if (stored === "true") return true;
  if (stored === "false") return false;
  return fallback;
}

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  return Boolean(
    target.closest(
      'input, textarea, select, button, [contenteditable="true"], [role="textbox"], [role="combobox"]',
    ),
  );
}

export default function App() {
  const [tab, setTab] = useState<TabKey>("search");
  const [sidebarWidth, setSidebarWidth] = useState(() =>
    readStoredNumber(SIDEBAR_WIDTH_KEY, 320, 260, 480),
  );
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() =>
    readStoredBoolean(SIDEBAR_COLLAPSED_KEY, false),
  );
  const searchRef = useRef<SearchPanelHandle>(null);
  const chatWorkspace = useChatWorkspace();

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth));
  }, [sidebarWidth]);

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(sidebarCollapsed));
  }, [sidebarCollapsed]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setTab("search");
        // focus after the tab is mounted
        setTimeout(() => searchRef.current?.focus(), 0);
      }
      if (
        (e.metaKey || e.ctrlKey) &&
        !e.altKey &&
        !e.shiftKey &&
        !e.repeat &&
        e.key.toLowerCase() === "b" &&
        !isEditableTarget(e.target)
      ) {
        e.preventDefault();
        setSidebarCollapsed((current) => !current);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const startSidebarResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (window.innerWidth < 768) return;
    event.preventDefault();

    const startX = event.clientX;
    const startWidth = sidebarWidth;

    const onMove = (moveEvent: PointerEvent) => {
      const nextWidth = startWidth + moveEvent.clientX - startX;
      setSidebarWidth(clamp(nextWidth, 260, 480));
    };

    const onUp = () => {
      document.body.classList.remove("is-resizing-panel");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };

    document.body.classList.add("is-resizing-panel");
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  return (
    <div className="app-shell flex h-screen flex-col overflow-hidden bg-background md:flex-row">
      {!sidebarCollapsed && (
        <Sidebar
          width={sidebarWidth}
          onResizeStart={startSidebarResize}
          onCollapse={() => setSidebarCollapsed(true)}
          workspace={chatWorkspace}
        />
      )}
      <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <Tabs
          value={tab}
          defaultValue="search"
          onValueChange={(v) => setTab(v as TabKey)}
          className="flex h-full min-w-0 flex-col gap-0"
        >
          <div className="app-topbar app-window-drag comfortable-scrollbar flex items-center justify-between gap-3 overflow-x-auto border-b px-4 py-3 md:px-6">
            <div className="flex min-w-0 items-center gap-2">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="app-shell-icon-button h-9 w-9 shrink-0"
                onClick={() => setSidebarCollapsed((current) => !current)}
                aria-label={
                  sidebarCollapsed
                    ? "Show navigation sidebar"
                    : "Hide navigation sidebar"
                }
                title={
                  sidebarCollapsed
                    ? "Show navigation sidebar"
                    : "Hide navigation sidebar"
                }
              >
                {sidebarCollapsed ? (
                  <PanelLeftOpen className="h-4 w-4" />
                ) : (
                  <PanelLeftClose className="h-4 w-4" />
                )}
              </Button>
              <TabsList className="min-w-max">
                <TabsTrigger value="search">
                  <Search className="h-4 w-4" /> Search
                </TabsTrigger>
                <TabsTrigger value="chat">
                  <MessageSquare className="h-4 w-4" /> Chat
                </TabsTrigger>
                <TabsTrigger value="library">
                  <FolderOpen className="h-4 w-4" /> Library
                </TabsTrigger>
                <TabsTrigger value="graph">
                  <Network className="h-4 w-4" /> Graph
                </TabsTrigger>
              </TabsList>
            </div>
            <div className="hidden text-xs text-muted-foreground sm:block">
              <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px]">
                ⌘K
              </kbd>{" "}
              to focus search
            </div>
          </div>

          <div className="app-content comfortable-scrollbar flex-1 overflow-y-auto p-4 md:p-6">
            <TabsContent value="search" className="h-full">
              <SearchPanel ref={searchRef} />
            </TabsContent>
            <TabsContent value="chat" className="h-full">
              <ChatPanel workspace={chatWorkspace} />
            </TabsContent>
            <TabsContent value="library" className="h-full">
              <LibraryPanel />
            </TabsContent>
            <TabsContent value="graph" className="h-full">
              <GraphPanel />
            </TabsContent>
          </div>
        </Tabs>
      </main>
    </div>
  );
}
