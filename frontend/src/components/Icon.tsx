import type { ReactNode } from "react";

/** Свой набор тонких иконок: 20×20, линия 1.6, без заливок (кроме play/pause/stop). */
const PATHS = {
  play: <path d="M6.5 4.5v11l9-5.5-9-5.5Z" fill="currentColor" stroke="none" />,
  pause: (
    <>
      <rect x="5" y="4.5" width="3.4" height="11" rx="1" fill="currentColor" stroke="none" />
      <rect x="11.6" y="4.5" width="3.4" height="11" rx="1" fill="currentColor" stroke="none" />
    </>
  ),
  stop: <rect x="5" y="5" width="10" height="10" rx="1.5" fill="currentColor" stroke="none" />,
  prev: <path d="M14 5l-6 5 6 5M6 5v10" />,
  next: <path d="M6 5l6 5-6 5M14 5v10" />,
  loop: <path d="M4 9V8a3 3 0 0 1 3-3h8l-2.5-2.5M16 11v1a3 3 0 0 1-3 3H5l2.5 2.5" />,
  metronome: <path d="M7.5 3h5l3 14h-11l3-14ZM10 13l4.5-7M5.6 13h8.8" />,
  countin: <path d="M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14ZM10 6.5V10l2.5 1.5" />,
  speaker: <path d="M3.5 7.5h3l4-3.5v12l-4-3.5h-3v-5ZM13.5 7.2a4 4 0 0 1 0 5.6M15.6 5a7 7 0 0 1 0 10" />,
  mute: <path d="M3.5 7.5h3l4-3.5v12l-4-3.5h-3v-5ZM13.5 8l4 4M17.5 8l-4 4" />,
  solo: <path d="M4 12v-1a6 6 0 0 1 12 0v1M4 12h2.5v4H4v-4ZM13.5 12H16v4h-2.5v-4Z" />,
  upload: <path d="M10 13V3.5M6 7.5l4-4 4 4M3.5 13v2.5a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1V13" />,
  link: <path d="M8.5 11.5a3 3 0 0 0 4.2 0l2.6-2.6a3 3 0 0 0-4.2-4.2l-.9.9M11.5 8.5a3 3 0 0 0-4.2 0l-2.6 2.6a3 3 0 0 0 4.2 4.2l.9-.9" />,
  plus: <path d="M10 4.5v11M4.5 10h11" />,
  minus: <path d="M4.5 10h11" />,
  close: <path d="M5 5l10 10M15 5L5 15" />,
  trash: <path d="M4 6h12M8 6V4.5h4V6M5.5 6l.8 9.5h7.4l.8-9.5" />,
  download: <path d="M10 3.5V13M6 9l4 4 4-4M3.5 16.5h13" />,
  retry: <path d="M15.5 10a5.5 5.5 0 1 1-1.6-3.9M15.5 3.5v3h-3" />,
  check: <path d="M4.5 10.5l3.5 3.5 7.5-8" />,
  chevron: <path d="M5.5 8l4.5 4.5L14.5 8" />,
  back: <path d="M12.5 4.5L7 10l5.5 5.5" />,
  library: (
    <>
      <rect x="3.5" y="6.5" width="10" height="10" rx="2" />
      <path d="M6.5 3.5h8a2 2 0 0 1 2 2v8" />
      <circle cx="8.5" cy="11.5" r="2" />
    </>
  ),
  theme: (
    <>
      <circle cx="10" cy="10" r="6.75" />
      <path d="M10 3.25a6.75 6.75 0 0 1 0 13.5Z" fill="currentColor" stroke="none" />
    </>
  ),
  guitar: <path d="M11.5 8.5l5-5M15 2.5l2.5 2.5M9.6 7.7a3.2 3.2 0 0 0-4.4.3c-.8.8-.7 1.9-1.6 2.6-1.4 1-1.5 3.3-.1 4.7s3.7 1.3 4.7-.1c.7-.9 1.8-.8 2.6-1.6a3.2 3.2 0 0 0 .3-4.4M8 12l.01.01" />,
  wave: <path d="M2.5 10h1.5M6 6.5v7M9 4v12M12 7v6M15 5.5v9M17.5 10H16" />,
  sliders: <path d="M5 3.5v13M10 3.5v13M15 3.5v13M3 13h4M8 7h4M13 11h4" />,
  print: <path d="M6 7.5V3.5h8v4M6 13.5H4.5a1 1 0 0 1-1-1v-4a1 1 0 0 1 1-1h11a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1H14M6 11h8v5.5H6V11Z" />,
  user: <path d="M10 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM4.5 16.5a5.5 5.5 0 0 1 11 0" />,
  spark: <path d="M10 3v3M10 14v3M3 10h3M14 10h3M5.2 5.2l2 2M12.8 12.8l2 2M14.8 5.2l-2 2M7.2 12.8l-2 2" />,
  mic: <path d="M10 12.5a2.5 2.5 0 0 0 2.5-2.5V5a2.5 2.5 0 0 0-5 0v5a2.5 2.5 0 0 0 2.5 2.5ZM5.5 9.5a4.5 4.5 0 0 0 9 0M10 14v3M7 17h6" />,
  lines: <path d="M3.5 5.5h13M3.5 9h9M3.5 12.5h13M3.5 16h7" />,
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 20, className = "" }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={`shrink-0 ${className}`}
    >
      {PATHS[name]}
    </svg>
  );
}
