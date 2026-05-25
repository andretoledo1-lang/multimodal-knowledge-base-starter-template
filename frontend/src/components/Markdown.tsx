import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

const components: Components = {
  h1: ({ className, ...props }) => (
    <h1
      className={cn(
        "mt-4 mb-2 text-base font-semibold tracking-tight first:mt-0",
        className,
      )}
      {...props}
    />
  ),
  h2: ({ className, ...props }) => (
    <h2
      className={cn(
        "mt-4 mb-2 text-[15px] font-semibold tracking-tight first:mt-0",
        className,
      )}
      {...props}
    />
  ),
  h3: ({ className, ...props }) => (
    <h3
      className={cn("mt-3 mb-1.5 text-sm font-semibold first:mt-0", className)}
      {...props}
    />
  ),
  h4: ({ className, ...props }) => (
    <h4
      className={cn("mt-3 mb-1 text-sm font-semibold first:mt-0", className)}
      {...props}
    />
  ),
  p: ({ className, ...props }) => (
    <p
      className={cn("leading-relaxed [&:not(:last-child)]:mb-2", className)}
      {...props}
    />
  ),
  ul: ({ className, ...props }) => (
    <ul
      className={cn(
        "mb-2 list-disc space-y-1 pl-5 last:mb-0 marker:text-muted-foreground",
        className,
      )}
      {...props}
    />
  ),
  ol: ({ className, ...props }) => (
    <ol
      className={cn(
        "mb-2 list-decimal space-y-1 pl-5 last:mb-0 marker:text-muted-foreground",
        className,
      )}
      {...props}
    />
  ),
  li: ({ className, ...props }) => (
    <li
      className={cn(
        "leading-relaxed [&>p]:mb-0 [&>ul]:mt-1 [&>ol]:mt-1",
        className,
      )}
      {...props}
    />
  ),
  a: ({ className, ...props }) => (
    <a
      className={cn(
        "font-medium text-primary underline underline-offset-2 hover:no-underline",
        className,
      )}
      target="_blank"
      rel="noreferrer"
      {...props}
    />
  ),
  strong: ({ className, ...props }) => (
    <strong className={cn("font-semibold", className)} {...props} />
  ),
  em: ({ className, ...props }) => (
    <em className={cn("italic", className)} {...props} />
  ),
  code: ({ className, children, ...props }) => {
    const text = String(children ?? "");
    const isBlock = /language-/.test(className ?? "") || text.includes("\n");
    if (isBlock) {
      return (
        <code className={cn("font-mono text-xs", className)} {...props}>
          {children}
        </code>
      );
    }
    return (
      <code
        className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.85em]"
        {...props}
      >
        {children}
      </code>
    );
  },
  pre: ({ className, ...props }) => (
    <pre
      className={cn(
        "mb-2 overflow-x-auto rounded-md border bg-muted/50 p-3 text-xs leading-relaxed last:mb-0",
        className,
      )}
      {...props}
    />
  ),
  blockquote: ({ className, ...props }) => (
    <blockquote
      className={cn(
        "mb-2 border-l-2 border-border pl-3 italic text-muted-foreground last:mb-0",
        className,
      )}
      {...props}
    />
  ),
  table: ({ className, ...props }) => (
    <div className="mb-2 overflow-x-auto last:mb-0">
      <table
        className={cn(
          "w-full border-collapse overflow-hidden rounded-md border text-xs",
          className,
        )}
        {...props}
      />
    </div>
  ),
  thead: ({ className, ...props }) => (
    <thead className={cn("bg-muted/60", className)} {...props} />
  ),
  th: ({ className, ...props }) => (
    <th
      className={cn(
        "border-b border-border px-2.5 py-1.5 text-left font-semibold",
        className,
      )}
      {...props}
    />
  ),
  td: ({ className, ...props }) => (
    <td
      className={cn(
        "border-b border-border px-2.5 py-1.5 align-top last:border-b-0",
        className,
      )}
      {...props}
    />
  ),
  hr: ({ className, ...props }) => (
    <hr className={cn("my-3 border-border", className)} {...props} />
  ),
};

export function Markdown({
  children,
  className,
}: {
  children: string;
  className?: string;
}) {
  return (
    <div className={cn("text-sm", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
