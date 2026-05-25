import { useEffect, useRef, useState } from "react";
import { MessageSquare, FolderOpen, Search } from "lucide-react";
import { Sidebar } from "@/components/Sidebar";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SearchPanel, type SearchPanelHandle } from "@/components/SearchPanel";
import { ChatPanel } from "@/components/ChatPanel";
import { LibraryPanel } from "@/components/LibraryPanel";

type TabKey = "search" | "chat" | "library";

export default function App() {
  const [tab, setTab] = useState<TabKey>("search");
  const searchRef = useRef<SearchPanelHandle>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setTab("search");
        // focus after the tab is mounted
        setTimeout(() => searchRef.current?.focus(), 0);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <main className="flex flex-1 flex-col overflow-hidden">
        <Tabs
          value={tab}
          defaultValue="search"
          onValueChange={(v) => setTab(v as TabKey)}
          className="flex h-full flex-col gap-0"
        >
          <div className="flex items-center justify-between border-b bg-card px-6 py-3">
            <TabsList>
              <TabsTrigger value="search">
                <Search className="h-4 w-4" /> Search
              </TabsTrigger>
              <TabsTrigger value="chat">
                <MessageSquare className="h-4 w-4" /> Chat
              </TabsTrigger>
              <TabsTrigger value="library">
                <FolderOpen className="h-4 w-4" /> Library
              </TabsTrigger>
            </TabsList>
            <div className="hidden text-xs text-muted-foreground sm:block">
              <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px]">
                ⌘K
              </kbd>{" "}
              to focus search
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-6">
            <TabsContent value="search" className="h-full">
              <SearchPanel ref={searchRef} />
            </TabsContent>
            <TabsContent value="chat" className="h-full">
              <ChatPanel />
            </TabsContent>
            <TabsContent value="library" className="h-full">
              <LibraryPanel />
            </TabsContent>
          </div>
        </Tabs>
      </main>
    </div>
  );
}
