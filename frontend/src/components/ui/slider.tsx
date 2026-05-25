import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export type SliderProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type">;

export const Slider = forwardRef<HTMLInputElement, SliderProps>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      type="range"
      className={cn(
        "h-2 w-full cursor-pointer appearance-none rounded-full bg-secondary accent-primary",
        className,
      )}
      {...props}
    />
  ),
);
Slider.displayName = "Slider";
