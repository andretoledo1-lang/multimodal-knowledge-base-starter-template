import { MODALITY, type Modality } from "@/lib/utils";

const KEYS: Modality[] = ["image", "pdf", "video", "text"];

interface ModalityFilterProps {
  value: string[];
  onChange: (next: string[]) => void;
  className?: string;
}

export function ModalityFilter({
  value,
  onChange,
  className,
}: ModalityFilterProps) {
  const toggle = (m: string) => {
    if (value.includes(m)) onChange(value.filter((v) => v !== m));
    else onChange([...value, m]);
  };

  return (
    <div className={className}>
      <div className="flex flex-wrap items-center gap-1.5">
        {KEYS.map((m) => {
          const active = value.includes(m);
          const Icon = MODALITY[m].icon;
          return (
            <button
              key={m}
              type="button"
              onClick={() => toggle(m)}
              aria-pressed={active}
              className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
                active
                  ? MODALITY[m].color
                  : "border-input bg-background text-muted-foreground hover:bg-accent"
              }`}
            >
              <Icon className="h-3 w-3" />
              {MODALITY[m].label}
            </button>
          );
        })}
        {value.length > 0 && (
          <button
            type="button"
            onClick={() => onChange([])}
            className="ml-1 text-xs text-muted-foreground underline-offset-2 hover:underline"
          >
            Clear
          </button>
        )}
      </div>
    </div>
  );
}
