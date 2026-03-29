import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  MessageSquare,
  List,
  CalendarClock,
  BookOpen,
  Network,
  Settings,
} from "lucide-react";

interface HelpDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-primary shrink-0" />
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      </div>
      <div className="pl-6 text-sm text-muted-foreground leading-relaxed space-y-1">
        {children}
      </div>
    </div>
  );
}

export function HelpDialog({ open, onOpenChange }: HelpDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Help &amp; Guide</DialogTitle>
          <DialogDescription>
            Learn how to use Contelligence Cowork to get the most out of your AI-powered content intelligence workflow.
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-[60vh] -mx-6 px-6">
          <div className="space-y-5 pb-2">
            <Section icon={MessageSquare} title="Chat">
              <p>
                The <strong>Chat</strong> page is where you interact with the AI agent. Type a message or instruction in the input box and press Enter to send it. The agent will process your request, potentially calling tools and retrieving content, and stream its response back in real time.
              </p>
              <p>
                You can attach files, ask follow-up questions, and give multi-step instructions. Each conversation is automatically saved as a session so you can return to it later.
              </p>
            </Section>

            <Section icon={List} title="Sessions">
              <p>
                The <strong>Sessions</strong> page lists all your past conversations. Each session shows the date, a summary, and the number of turns.
              </p>
              <p>
                Click on any session to view the full conversation history. You can resume a session by opening it and continuing to send messages — the agent retains the full context from the earlier turns.
              </p>
            </Section>

            <Section icon={CalendarClock} title="Schedules">
              <p>
                <strong>Schedules</strong> let you automate agent tasks on a recurring basis. You can create a schedule with a cron expression, an interval, or a webhook trigger.
              </p>
              <p>
                Each schedule has an instruction that the agent will execute when triggered. Use schedules for daily reports, periodic content digests, or any task you want to run automatically. You can pause, resume, or manually trigger any schedule.
              </p>
            </Section>

            <Section icon={BookOpen} title="Skills">
              <p>
                <strong>Skills</strong> are code-free domain knowledge packages that extend what the agent knows. Each skill contains curated instructions, reference material, and templates for a specific domain (e.g., contract analysis, financial research).
              </p>
              <p>
                Browse installed skills, create new ones, or edit existing skills from the Skills page. When a skill is active, the agent can draw on its knowledge to produce more accurate, domain-specific results.
              </p>
            </Section>

            <Section icon={Network} title="MCP Servers">
              <p>
                <strong>MCP Servers</strong> (Model Context Protocol) provide external tool access to the agent. They act as bridges to services like Azure, GitHub, or custom APIs.
              </p>
              <p>
                The MCP Servers page shows all configured servers and their connection status. You can add new servers, check health, and view the tools each server exposes. The agent automatically discovers and uses tools from connected MCP servers.
              </p>
            </Section>

            <Section icon={Settings} title="Settings">
              <p>
                The <strong>Settings</strong> page lets you configure the backend connection, API keys, model preferences, and other application options.
              </p>
              <p>
                Adjust the backend URL if running a remote agent, configure Azure OpenAI endpoints, and manage environment-specific settings. Changes are saved automatically and take effect on the next request.
              </p>
            </Section>
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
