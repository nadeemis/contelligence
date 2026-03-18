import {
  LayoutDashboard,
  MessageSquare,
  List,
  CalendarClock,
  BarChart3,
  Bot,
  BookOpen,
  Settings,
} from "lucide-react";
import { NavLink } from "@/components/NavLink";
import { AgentStatus } from "@/components/AgentStatus";
import { useLocation } from "react-router-dom";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarHeader,
  SidebarFooter,
  useSidebar,
} from "@/components/ui/sidebar";

const navItems = [
  { title: "Dashboard", url: "/", icon: LayoutDashboard },
  { title: "Chat", url: "/chat", icon: MessageSquare },
  { title: "Sessions", url: "/sessions", icon: List },
  { title: "Schedules", url: "/schedules", icon: CalendarClock },
  { title: "Metrics", url: "/metrics", icon: BarChart3 },
  { title: "Agents", url: "/agents", icon: Bot },
  { title: "Skills", url: "/skills", icon: BookOpen },
  { title: "Settings", url: "/settings", icon: Settings },
];

export function AppSidebar() {
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  const location = useLocation();

  return (
    <Sidebar collapsible="icon" className="border-r border-border pt-5">
      <SidebarHeader className="p-4">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <img src="/Contelligence-logo.png" alt="Contelligence Logo" />
          </div>
          {!collapsed && (
            <span className="text-lg font-bold text-foreground tracking-tight font-display">
              Contelligence
            </span>
          )}
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton asChild>
                    <NavLink
                      to={item.url}
                      end={item.url === "/"}
                      className="flex items-center gap-3 rounded-lg px-3 py-2 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                      activeClassName="bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary"
                    >
                      <item.icon className="h-4 w-4 shrink-0" />
                      {!collapsed && <span>{item.title}</span>}
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="p-4">
        {!collapsed && <AgentStatus />}
      </SidebarFooter>
    </Sidebar>
  );
}