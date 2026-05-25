import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import {
  type LucideIcon,
  Image as ImageIcon,
  FileText,
  Video,
  FileType,
  HelpCircle,
} from "lucide-react";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export type Modality = "image" | "pdf" | "video" | "text";

export const MODALITY: Record<
  Modality | "unknown",
  { color: string; icon: LucideIcon; label: string }
> = {
  image: {
    color:
      "bg-violet-500/15 text-violet-700 dark:text-violet-300 border-violet-500/30",
    icon: ImageIcon,
    label: "Image",
  },
  pdf: {
    color: "bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/30",
    icon: FileText,
    label: "PDF",
  },
  video: {
    color: "bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-500/30",
    icon: Video,
    label: "Video",
  },
  text: {
    color:
      "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30",
    icon: FileType,
    label: "Text",
  },
  unknown: {
    color: "bg-zinc-500/15 text-zinc-700 dark:text-zinc-300 border-zinc-500/30",
    icon: HelpCircle,
    label: "Unknown",
  },
};

export function formatRelativeTime(iso: string | undefined): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (isNaN(then)) return iso;
  const diff = Date.now() - then;
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}d ago`;
  return new Date(iso).toLocaleDateString();
}
