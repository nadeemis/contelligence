import { useState } from "react";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/AppSidebar";
import { Bell, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Outlet } from "react-router-dom";
import { UserMenu } from "@/components/UserMenu";
import { HelpDialog } from "@/components/HelpDialog";

const isElectron = typeof window !== "undefined" && !!window.electronAPI;
const isMac = isElectron && navigator.platform.toLowerCase().includes("mac");

export function AppLayout() {
  const [helpOpen, setHelpOpen] = useState(false);

  return (
    <SidebarProvider>
      <div className="min-h-screen flex w-full">
        <AppSidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <header className={`h-14 flex items-center justify-between border-b border-border px-4 bg-card/50 backdrop-blur-sm shrink-0 ${isMac ? "electron-drag-region pl-20" : ""}`}>
            <div className="flex items-center gap-2 electron-no-drag">
              <SidebarTrigger className="text-muted-foreground hover:text-foreground" />
            </div>
            <div className="flex items-center gap-2 electron-no-drag">
              <Button variant="ghost" size="icon" className="text-muted-foreground hover:text-foreground" onClick={() => setHelpOpen(true)}>
                <Info className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" className="text-muted-foreground hover:text-foreground">
                <Bell className="h-4 w-4" />
              </Button>
              <UserMenu />
            </div>
          </header>
          <main className="flex-1 overflow-auto p-6">
            <Outlet />
          </main>
        </div>
      </div>
      <HelpDialog open={helpOpen} onOpenChange={setHelpOpen} />
    </SidebarProvider>
  );
}