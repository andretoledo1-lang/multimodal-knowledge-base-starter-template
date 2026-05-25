import { useState } from "react";
import { FileType } from "lucide-react";
import { cn, MODALITY, type Modality } from "@/lib/utils";

interface PreviewThumbProps {
  url: string | null | undefined;
  modality: string;
  alt: string;
  className?: string;
}

export function PreviewThumb({
  url,
  modality,
  alt,
  className,
}: PreviewThumbProps) {
  const [errored, setErrored] = useState(false);
  const key = (modality in MODALITY ? modality : "unknown") as
    | Modality
    | "unknown";
  const Icon = MODALITY[key].icon ?? FileType;

  if (!url || errored) {
    return (
      <div
        className={cn(
          "flex items-center justify-center bg-muted text-muted-foreground",
          className,
        )}
      >
        <Icon className="h-8 w-8" />
      </div>
    );
  }
  return (
    <img
      src={url}
      alt={alt}
      loading="lazy"
      onError={() => setErrored(true)}
      className={cn("h-full w-full object-cover", className)}
    />
  );
}
