type AppIconName =
  | "arrow-left"
  | "arrow-right"
  | "bell"
  | "calendar"
  | "chart"
  | "chevron-down"
  | "clipboard"
  | "clock"
  | "doc"
  | "doctor"
  | "flag"
  | "globe"
  | "grid"
  | "hospital"
  | "layers"
  | "lightbulb"
  | "list"
  | "play"
  | "refresh"
  | "rocket"
  | "search"
  | "send"
  | "settings"
  | "shield"
  | "spark"
  | "star"
  | "tag"
  | "target"
  | "trend"
  | "log-out"
  | "user"
  | "info"
  | "alert";

type AppIconProps = {
  className?: string;
  name: AppIconName;
};

export function AppIcon({ className, name }: AppIconProps) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      xmlns="http://www.w3.org/2000/svg"
    >
      {name === "arrow-left" ? (
        <path d="M14.5 5.5 8 12l6.5 6.5M9 12h9" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.9" />
      ) : null}
      {name === "arrow-right" ? (
        <path d="M9.5 5.5 16 12l-6.5 6.5M15 12H6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.9" />
      ) : null}
      {name === "bell" ? (
        <>
          <path d="M8.5 17h7l-1.1-1.3a2 2 0 0 1-.5-1.3V11a4 4 0 1 0-8 0v3.4c0 .5-.2 1-.5 1.3L4.5 17h4Z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.9" />
          <path d="M10 18.5a2 2 0 0 0 4 0" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "calendar" ? (
        <>
          <rect height="14" rx="2.5" stroke="currentColor" strokeWidth="1.9" width="16" x="4" y="6" />
          <path d="M4 10.5h16M8 4v4M16 4v4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "chart" ? (
        <>
          <path d="M5 19V9M12 19V5M19 19v-7" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
          <path d="M4 19h16" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "chevron-down" ? (
        <path d="m7 10 5 5 5-5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.9" />
      ) : null}
      {name === "clipboard" ? (
        <>
          <rect height="15" rx="2.5" stroke="currentColor" strokeWidth="1.9" width="12" x="6" y="6" />
          <rect height="4" rx="1.5" stroke="currentColor" strokeWidth="1.9" width="6" x="9" y="3" />
          <path d="M9 11h6M9 15h4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "clock" ? (
        <>
          <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.9" />
          <path d="M12 8v4l3 2" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "doc" ? (
        <>
          <path d="M8 3.5h6l4 4V20a1 1 0 0 1-1 1H8a2 2 0 0 1-2-2V5.5a2 2 0 0 1 2-2Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.9" />
          <path d="M14 3.5V8h4" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.9" />
          <path d="M9 12h6M9 16h5" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "doctor" ? (
        <>
          <circle cx="12" cy="7.5" r="3" stroke="currentColor" strokeWidth="1.9" />
          <path d="M8 20v-4a4 4 0 0 1 8 0v4M10 12.5l2 2 2-2" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "flag" ? (
        <>
          <path d="M6 20V5" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
          <path d="M7 5h10l-2.3 3L17 11H7" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "globe" ? (
        <>
          <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.9" />
          <path d="M12 3a15.3 15.3 0 0 1 4 9 15.3 15.3 0 0 1-4 9 15.3 15.3 0 0 1-4-9 15.3 15.3 0 0 1 4-9z" stroke="currentColor" strokeWidth="1.9" />
          <path d="M3 12h18" stroke="currentColor" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "grid" ? (
        <>
          <rect height="5" rx="1" stroke="currentColor" strokeWidth="1.9" width="5" x="4.5" y="4.5" />
          <rect height="5" rx="1" stroke="currentColor" strokeWidth="1.9" width="5" x="14.5" y="4.5" />
          <rect height="5" rx="1" stroke="currentColor" strokeWidth="1.9" width="5" x="4.5" y="14.5" />
          <rect height="5" rx="1" stroke="currentColor" strokeWidth="1.9" width="5" x="14.5" y="14.5" />
        </>
      ) : null}
      {name === "hospital" ? (
        <>
          <path d="M7 20V8h10v12M10 4h4v4h-4z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.9" />
          <path d="M12 10v6M9 13h6" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "layers" ? (
        <>
          <path d="m12 4 8 4-8 4-8-4 8-4ZM4 12l8 4 8-4M4 16l8 4 8-4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "lightbulb" ? (
        <>
          <path d="M9 17h6M10 20h4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
          <path d="M8.5 14.5c-1.2-.9-2-2.4-2-4A5.5 5.5 0 0 1 12 5a5.5 5.5 0 0 1 5.5 5.5c0 1.6-.8 3.1-2 4l-.8 1H9.3l-.8-1Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "list" ? (
        <>
          <path d="M10 7h9M10 12h9M10 17h9M5 7h.01M5 12h.01M5 17h.01" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "play" ? (
        <path d="m9 7 8 5-8 5V7Z" fill="currentColor" />
      ) : null}
      {name === "refresh" ? (
        <path d="M4.5 12A7.5 7.5 0 0 0 17 17.5M19.5 12A7.5 7.5 0 0 0 7 6.5M19.5 6v4h-4M4.5 18v-4h4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.9" />
      ) : null}
      {name === "rocket" ? (
        <>
          <path d="m13 5 6 6-3.5 7.5L8 16l-2.5-7.5L13 5Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.9" />
          <path d="m7 17-2 2M10 19l-1 2M14 9.5h.01" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "search" ? (
        <>
          <circle cx="11" cy="11" r="6" stroke="currentColor" strokeWidth="1.9" />
          <path d="m16 16 3 3" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "send" ? (
        <path d="m4 12 15-7-3 14-4.5-4L4 12Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.9" />
      ) : null}
      {name === "shield" ? (
        <>
          <path d="M12 4 6 6.5v5c0 4 2.5 6.4 6 8 3.5-1.6 6-4 6-8v-5L12 4Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.9" />
          <path d="m9.5 12.5 1.8 1.8 3.4-3.6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "settings" ? (
        <>
          <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.9" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "user" ? (
        <>
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.9" />
          <circle cx="12" cy="7" r="4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "log-out" ? (
        <>
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.9" />
          <polyline points="16 17 21 12 16 7" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.9" fill="none" />
          <line x1="21" y1="12" x2="9" y2="12" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "spark" ? (
        <path d="M12 3.5 13.8 8l4.7.6-3.5 3 1 4.6L12 13.8l-4 2.4 1-4.6-3.5-3 4.7-.6L12 3.5Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.9" />
      ) : null}
      {name === "star" ? (
        <path d="m12 4 2.4 4.9 5.4.8-3.9 3.8.9 5.4-4.8-2.5-4.8 2.5.9-5.4-3.9-3.8 5.4-.8L12 4Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.9" />
      ) : null}
      {name === "tag" ? (
        <>
          <path d="M6 10.5V5.8A1.8 1.8 0 0 1 7.8 4h4.7l6.5 6.5-6 6-6.5-6Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.9" />
          <circle cx="10" cy="8" r="1" fill="currentColor" />
        </>
      ) : null}
      {name === "target" ? (
        <>
          <circle cx="12" cy="12" r="7.5" stroke="currentColor" strokeWidth="1.9" />
          <circle cx="12" cy="12" r="3.5" stroke="currentColor" strokeWidth="1.9" />
          <path d="M12 4.5V2.5M19.5 12h2M12 21.5v-2M2.5 12h2" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "trend" ? (
        <>
          <path d="M4 19h16" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
          <path d="m5 15 4-4 3 2 6-6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "user" ? (
        <>
          <circle cx="12" cy="8" r="3.2" fill="currentColor" opacity=".9" />
          <path d="M6.5 19a5.5 5.5 0 0 1 11 0" fill="currentColor" opacity=".9" />
        </>
      ) : null}
      {name === "info" ? (
        <>
          <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.9" />
          <path d="M12 8v4M12 16h.01" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
        </>
      ) : null}
      {name === "alert" ? (
        <>
          <path d="m12 5 8 14H4L12 5Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.9" />
          <path d="M12 9v4M12 17h.01" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
        </>
      ) : null}
    </svg>
  );
}

export function BrandMark({ className }: { className?: string }) {
  const isSmall = className?.includes('h-5') || className?.includes('w-5') || className?.includes('h-4') || className?.includes('w-4');
  
  let size = '1.5rem'; // default for h-6/w-6
  if (className?.includes('h-5') || className?.includes('w-5')) {
    size = '1.25rem'; // 20px for h-5/w-5
  } else if (className?.includes('h-4') || className?.includes('w-4')) {
    size = '1rem'; // 16px for h-4/w-4
  }
  
  const style = isSmall || className?.includes('h-6') || className?.includes('w-6') ? { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: size, height: size } : { display: 'inline-flex', alignItems: 'center', justifyContent: 'center' };
  
  return (
    <span aria-hidden="true" className={className} style={style}>
      <svg fill="none" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg" style={{ width: '100%', height: '100%' }}>
        <path
          d="M16 2.5 28.5 9v14L16 29.5 3.5 23V9L16 2.5Z"
          fill="url(#brandFill)"
          stroke="#1D4ED8"
          strokeWidth="1.4"
        />
        <path d="M15.9 8v15.8M8 15.9h15.8" stroke="#fff" strokeLinecap="round" strokeWidth="3" />
        <defs>
          <linearGradient id="brandFill" x1="16" x2="16" y1="2.5" y2="29.5">
            <stop stopColor="#56C2FF" />
            <stop offset="1" stopColor="#2563EB" />
          </linearGradient>
        </defs>
      </svg>
    </span>
  );
}

export function UserAvatar({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span aria-hidden="true" className={className}>
      <svg fill="none" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="avatarBg" x1="32" x2="32" y1="0" y2="64">
            <stop stopColor="#D9ECFF" />
            <stop offset="1" stopColor="#B7D4FF" />
          </linearGradient>
        </defs>
        <circle cx="32" cy="32" fill="url(#avatarBg)" r="31" stroke="#D6E4FF" strokeWidth="2" />
        <circle cx="32" cy="20" fill="#F3C9A8" r="8.5" />
        <path d="M22 50a10 10 0 0 1 20 0v1H22v-1Z" fill={compact ? "#1E40AF" : "#2563EB"} />
        <path d="M25 52h14l-2-10H27l-2 10Z" fill="#203A78" />
        <path d="m32 42 3 5-3 5-3-5 3-5Z" fill="#fff" />
        <path d="M24.5 16.5c1.4-5.1 5.2-8 10.3-8 4 0 7.2 2.1 8.7 5.7-1.6-.5-3.4-.7-5.4-.7-5 0-9.6 1.5-13.6 3Z" fill="#1E3A8A" opacity=".9" />
      </svg>
    </span>
  );
}

export type IllustrationVariant =
  | "meeting"
  | "presentation"
  | "analysis"
  | "conversation"
  | "growth"
  | "report";

type ThumbnailArtworkProps = {
  className?: string;
  variant: IllustrationVariant;
};

export function ThumbnailArtwork({ className, variant }: ThumbnailArtworkProps) {
  const palette =
    variant === "presentation"
      ? { bg: "#DCEBFF", panel: "#8BB8FF", accent: "#2E6CFF", soft: "#BEDBFF" }
      : variant === "analysis"
        ? { bg: "#D7F2FF", panel: "#8AC5F6", accent: "#1780E8", soft: "#C3E6FF" }
        : variant === "conversation"
          ? { bg: "#E7F0FF", panel: "#9AC0FF", accent: "#356AF6", soft: "#CFE0FF" }
          : variant === "growth"
            ? { bg: "#EAF4FF", panel: "#9DD2FF", accent: "#1D65F2", soft: "#D1EAFF" }
            : variant === "report"
              ? { bg: "#E8F2FF", panel: "#93C5FD", accent: "#2563EB", soft: "#D7E9FF" }
              : { bg: "#E5F1FF", panel: "#8FBEFF", accent: "#2563EB", soft: "#CBE1FF" };

  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      viewBox="0 0 320 180"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect fill={palette.bg} height="180" rx="20" width="320" />
      <rect fill="#fff" height="115" opacity=".58" rx="12" width="110" x="190" y="26" />
      <rect fill={palette.panel} height="60" opacity=".95" rx="10" width="112" x="170" y="36" />
      <rect fill={palette.soft} height="12" rx="6" width="68" x="184" y="108" />
      <rect fill={palette.soft} height="12" rx="6" width="96" x="184" y="128" />
      <circle cx="90" cy="86" fill="#F4C8A4" r="22" />
      <path d="M58 152c2-25 17-42 38-42 23 0 38 16 41 42H58Z" fill={palette.accent} />
      <circle cx="62" cy="93" fill="#F2C9A7" r="20" />
      <path d="M33 152c2-21 14-36 32-36 19 0 31 14 34 36H33Z" fill="#274B7F" />
      <rect fill="#fff" height="28" opacity=".7" rx="14" width="80" x="18" y="24" />
      <path
        d="M218 56h18v26h-18zM244 48h22v34h-22zM274 42h16v40h-16z"
        fill="#fff"
        opacity=".72"
      />
      {variant === "presentation" ? (
        <>
          <rect fill="#fff" height="8" opacity=".8" rx="4" width="54" x="184" y="50" />
          <rect fill="#fff" height="8" opacity=".7" rx="4" width="78" x="184" y="68" />
        </>
      ) : null}
      {variant === "analysis" ? (
        <path d="m182 90 18-18 18 8 22-24 20 10" stroke="#fff" strokeLinecap="round" strokeLinejoin="round" strokeWidth="6" />
      ) : null}
      {variant === "conversation" ? (
        <>
          <rect fill="#fff" height="20" opacity=".82" rx="10" width="54" x="184" y="48" />
          <rect fill="#fff" height="20" opacity=".7" rx="10" width="70" x="210" y="74" />
        </>
      ) : null}
      {variant === "growth" ? (
        <>
          <path d="m184 112 26-22 22 12 34-34" stroke="#fff" strokeLinecap="round" strokeLinejoin="round" strokeWidth="6" />
          <circle cx="276" cy="68" fill="#fff" r="8" />
        </>
      ) : null}
      {variant === "report" ? (
        <>
          <rect fill="#fff" height="64" opacity=".82" rx="10" width="46" x="200" y="44" />
          <path d="M210 60h24M210 74h24M210 88h16" stroke={palette.accent} strokeLinecap="round" strokeWidth="5" />
        </>
      ) : null}
    </svg>
  );
}
