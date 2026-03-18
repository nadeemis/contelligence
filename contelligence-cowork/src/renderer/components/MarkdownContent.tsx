import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Shared custom components for ReactMarkdown rendering. */
const markdownComponents: import("react-markdown").Components = {
  h1: ({ children }) => <h1 className="text-base font-semibold mt-3 mb-1.5 text-foreground">{children}</h1>,
  h2: ({ children }) => <h2 className="text-[0.85rem] font-semibold mt-2.5 mb-1 text-foreground">{children}</h2>,
  h3: ({ children }) => <h3 className="text-[0.8rem] font-semibold mt-2 mb-1 text-foreground">{children}</h3>,
  h4: ({ children }) => <h4 className="text-[0.78rem] font-medium mt-1.5 mb-0.5 text-foreground">{children}</h4>,
  p: ({ children }) => <p className="text-[0.78rem] leading-relaxed mb-1.5 text-foreground/90">{children}</p>,
  ul: ({ children }) => <ul className="list-disc list-outside ml-4 mb-1.5 space-y-0.5 text-[0.78rem] text-foreground/90">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal list-outside ml-4 mb-1.5 space-y-0.5 text-[0.78rem] text-foreground/90">{children}</ol>,
  li: ({ children }) => <li className="text-[0.78rem] leading-relaxed">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-primary/40 pl-3 my-1.5 text-[0.76rem] italic text-muted-foreground">
      {children}
    </blockquote>
  ),
  code: ({ className, children, ...props }) => {
    const isBlock = className?.startsWith("language-");
    if (isBlock) {
      return (
        <pre className="rounded-md border border-border/50 bg-background/60 p-2.5 my-1.5 overflow-x-auto">
          <code className={`text-[0.72rem] font-mono leading-snug ${className ?? ""}`} {...props}>
            {children}
          </code>
        </pre>
      );
    }
    return (
      <code className="rounded bg-muted/60 px-1 py-0.5 text-[0.72rem] font-mono text-primary/90" {...props}>
        {children}
      </code>
    );
  },
  pre: ({ children }) => <>{children}</>,
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto rounded border border-border/50">
      <table className="w-full text-[0.72rem]">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-muted/40 border-b border-border/50">{children}</thead>,
  th: ({ children }) => <th className="px-2 py-1 text-left font-medium text-foreground/80">{children}</th>,
  td: ({ children }) => <td className="px-2 py-1 border-t border-border/30 text-foreground/80">{children}</td>,
  hr: () => <hr className="my-2 border-border/40" />,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
      {children}
    </a>
  ),
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  em: ({ children }) => <em className="italic text-foreground/80">{children}</em>,
};

interface MarkdownContentProps {
  children: string;
  className?: string;
}

export function MarkdownContent({ children, className }: MarkdownContentProps) {
  return (
    <div className={className ?? "max-w-none"}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
