import {
  cloneElement,
  isValidElement,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";
import { cn } from "@/lib/utils";

interface TooltipProps {
  content: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  className?: string;
  children: ReactElement;
}

export function Tooltip({
  content,
  side = "top",
  className,
  children,
}: TooltipProps) {
  const [open, setOpen] = useState(false);

  if (!isValidElement(children)) return children;
  const trigger = cloneElement(children, {
    onMouseEnter: () => setOpen(true),
    onMouseLeave: () => setOpen(false),
    onFocus: () => setOpen(true),
    onBlur: () => setOpen(false),
  } as Record<string, unknown>);

  const positions: Record<string, string> = {
    top: "bottom-full left-1/2 -translate-x-1/2 mb-1.5",
    bottom: "top-full left-1/2 -translate-x-1/2 mt-1.5",
    left: "right-full top-1/2 -translate-y-1/2 mr-1.5",
    right: "left-full top-1/2 -translate-y-1/2 ml-1.5",
  };

  return (
    <span className="relative inline-flex">
      {trigger}
      {open && (
        <span
          role="tooltip"
          className={cn(
            "pointer-events-none absolute z-50 whitespace-nowrap rounded-md border bg-popover px-2 py-1 text-xs text-popover-foreground shadow-md",
            positions[side],
            className,
          )}
        >
          {content}
        </span>
      )}
    </span>
  );
}

// shadcn-compatible re-exports — our Tooltip is single-component so the
// Provider/Trigger/Content wrappers are no-ops mapped to our component.
export const TooltipProvider = ({ children }: { children: ReactNode }) => (
  <>{children}</>
);
