import { forwardRef, type HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export const ScrollArea = forwardRef<
  HTMLDivElement,
  HTMLAttributes<HTMLDivElement>
>(({ className, children, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "relative overflow-y-auto overflow-x-hidden scrollbar-thin",
      className,
    )}
    {...props}
  >
    {children}
  </div>
));
ScrollArea.displayName = "ScrollArea";
