import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Settings } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";

interface UserIdentity {
  machine: { username: string; fullName: string };
  azure?: { name: string; email: string; tenantId: string };
}

function getInitials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");
}

export function UserMenu() {
  const navigate = useNavigate();
  const [identity, setIdentity] = useState<UserIdentity | null>(null);
  const [azureStatus, setAzureStatus] = useState<{
    available: boolean;
    loggedIn: boolean;
  }>({ available: false, loggedIn: false });

  useEffect(() => {
    window.electronAPI?.getUserIdentity().then(setIdentity);
    window.electronAPI?.getAzureStatus().then(setAzureStatus);
  }, []);

  const displayName = identity?.machine.fullName || identity?.machine.username || "User";
  const initials = getInitials(displayName) || "U";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative text-muted-foreground hover:text-foreground">
          <Avatar className="h-7 w-7">
            <AvatarFallback className="text-xs bg-primary/10 text-primary">
              {initials}
            </AvatarFallback>
          </Avatar>
          {/* Status dot */}
          <span
            className={`absolute bottom-0.5 right-0.5 h-2 w-2 rounded-full ring-1 ring-background ${
              azureStatus.loggedIn
                ? "bg-emerald-500"
                : azureStatus.available
                  ? "bg-amber-500"
                  : "bg-muted-foreground/40"
            }`}
          />
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-72">
        {/* Machine identity */}
        <DropdownMenuLabel className="font-normal">
          <div className="flex flex-col gap-0.5">
            <p className="text-sm font-medium leading-none">{displayName}</p>
            {identity?.machine.username && (
              <p className="text-xs text-muted-foreground">
                @{identity.machine.username}
              </p>
            )}
          </div>
        </DropdownMenuLabel>

        <DropdownMenuSeparator />

        {/* Azure CLI status */}
        <DropdownMenuLabel className="font-normal text-xs">
          {!azureStatus.available ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <span className="h-2 w-2 rounded-full bg-muted-foreground/40 shrink-0" />
              <span>Azure CLI &mdash; Not installed (optional)</span>
            </div>
          ) : azureStatus.loggedIn ? (
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
                <span className="h-2 w-2 rounded-full bg-emerald-500 shrink-0" />
                <span>Azure CLI &mdash; Connected</span>
              </div>
              {identity?.azure && (
                <div className="pl-4 text-muted-foreground space-y-0.5">
                  <p className="truncate">{identity.azure.name}</p>
                  {identity.azure.tenantId && (
                    <p className="truncate">Tenant: {identity.azure.tenantId}</p>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400">
                <span className="h-2 w-2 rounded-full bg-amber-500 shrink-0" />
                <span>Azure CLI &mdash; Not logged in</span>
              </div>
              <p className="pl-4 text-muted-foreground">
                Run <code className="text-[10px] bg-muted px-1 py-0.5 rounded">az login</code> in a terminal
              </p>
            </div>
          )}
        </DropdownMenuLabel>

        <DropdownMenuSeparator />

        <DropdownMenuItem onClick={() => navigate("/settings")} className="cursor-pointer">
          <Settings className="mr-2 h-4 w-4" />
          Settings
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
