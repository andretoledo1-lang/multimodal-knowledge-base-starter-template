import { MODALITY, type Modality, cn } from "@/lib/utils";

interface ModalityBadgeProps {
  modality: string;
  className?: string;
  showLabel?: boolean;
}

export function ModalityBadge({
  modality,
  className,
  showLabel = true,
}: ModalityBadgeProps) {
  const key = (modality in MODALITY ? modality : "unknown") as
    | Modality
    | "unknown";
  const { color, icon: Icon, label } = MODALITY[key];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
        color,
        className,
      )}
    >
      <Icon className="h-3 w-3" />
      {showLabel && label}
    </span>
  );
}
