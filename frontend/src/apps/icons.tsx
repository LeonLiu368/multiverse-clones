// Real brand marks for the launcher tiles + Google file-type icons for the Workspace view.
// Hand-built SVGs (brand colors + core silhouettes) so the dashboard shows each product's actual
// logo instead of a letter/emoji placeholder.

export function BrandIcon({ id, size = 40 }: { id: string; size?: number }) {
  const wrap = { width: size, height: size, display: "block" } as const;
  switch (id) {
    case "slack":
      return (
        <svg viewBox="0 0 24 24" style={wrap} aria-label="Slack">
          {[
            { a: 0, c: "#36C5F0" },
            { a: 90, c: "#2EB67D" },
            { a: 180, c: "#ECB22E" },
            { a: 270, c: "#E01E5A" },
          ].map(({ a, c }) => (
            <g key={a} transform={`rotate(${a} 12 12)`}>
              <rect x="3.4" y="10.4" width="5.6" height="3.2" rx="1.6" fill={c} />
              <rect x="9" y="10.4" width="3.2" height="6" rx="1.6" fill={c} />
            </g>
          ))}
        </svg>
      );
    case "jira":
      return (
        <svg viewBox="0 0 24 24" style={wrap} aria-label="Jira">
          <path d="M11.6 2 L20.8 11.2 a1.1 1.1 0 0 1 0 1.6 L11.6 22 L7.7 18.1 l5.7-5.7 a0.4 0.4 0 0 0 0-0.6 L7.7 6.1 z" fill="#2684FF" />
          <path d="M11.6 8.2 a5.2 5.2 0 0 1-5.2-5.2 h-3.2 A8.4 8.4 0 0 0 11.6 11.4 z" fill="#2684FF" opacity="0.75" />
          <path d="M11.6 15.8 a5.2 5.2 0 0 1 5.2 5.2 h3.2 A8.4 8.4 0 0 0 11.6 12.6 z" fill="#2684FF" opacity="0.55" />
        </svg>
      );
    case "figma":
      return (
        <svg viewBox="0 0 24 24" style={wrap} aria-label="Figma">
          <rect x="7" y="2.4" width="5" height="6.4" rx="2.5" fill="#F24E1E" />
          <rect x="7" y="8.8" width="5" height="6.4" fill="#A259FF" />
          <rect x="7" y="15.2" width="5" height="6.4" rx="2.5" fill="#0ACF83" />
          <circle cx="14.6" cy="5.6" r="3.2" fill="#FF7262" />
          <circle cx="14.6" cy="12" r="3.4" fill="#1ABCFE" />
        </svg>
      );
    case "gauge": // Grafana
      return (
        <svg viewBox="0 0 24 24" style={wrap} aria-label="Grafana">
          <circle cx="12" cy="12" r="9.2" fill="#F46800" />
          <path d="M12 6.2 a5.8 5.8 0 1 0 5.8 5.8 h-3 a2.8 2.8 0 1 1-2.8-2.8 z" fill="#fff" />
          <rect x="10.6" y="2.2" width="2.8" height="4.4" rx="1.4" fill="#F9A600" />
        </svg>
      );
    case "sentry":
      return (
        <svg viewBox="0 0 24 24" style={wrap} aria-label="Sentry">
          <path
            d="M13.6 3.4 a1.9 1.9 0 0 0-3.2 0 L3 16.2 a1.7 1.7 0 0 0 1.5 2.6 h3.1 a7.2 7.2 0 0 0-3.4-6.1 l1.6-2.7 a10.3 10.3 0 0 1 4.9 8.8 h4.2 a14.5 14.5 0 0 0-6.2-11.9 l1.1-1.9 a16.7 16.7 0 0 1 7.5 13.8 h1.2 a1.7 1.7 0 0 0 1.5-2.6 z"
            fill="#362D59"
          />
        </svg>
      );
    case "github":
      return (
        <svg viewBox="0 0 16 16" style={wrap} aria-label="GitHub">
          <path
            fill="#181717"
            d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"
          />
        </svg>
      );
    case "logfire": // Pydantic Logfire — flame
      return (
        <svg viewBox="0 0 24 24" style={wrap} aria-label="Logfire">
          <path d="M12 2.4 c2.6 3 5.4 5.2 5.4 9.4 a5.4 5.4 0 0 1-10.8 0 c0-2 1-3.6 2.2-5 0 1.4.6 2.4 1.7 2.4 1 0 1.5-.8 1.5-1.9 0-1.9-1-3-1-4.9 0.1-.001.9 0 1 0z" fill="#E5202E" />
          <path d="M12 12 c1.1 1.3 2.2 2.2 2.2 3.9 a2.2 2.2 0 0 1-4.4 0 c0-1.2.8-2 1.4-2.9 0 .6.3 1 .8 1 .5 0 .7-.4.7-.9 0-.4-.4-.8-.7-1.2z" fill="#FF8A3D" />
        </svg>
      );
    case "gworkspace": // Google "G"
      return (
        <svg viewBox="0 0 24 24" style={wrap} aria-label="Google Workspace">
          <path d="M21.6 12.2 c0-.7-.06-1.36-.18-2H12v3.8h5.4a4.6 4.6 0 0 1-2 3v2.5h3.2c1.9-1.74 3-4.3 3-7.3z" fill="#4285F4" />
          <path d="M12 22 c2.7 0 4.96-.9 6.6-2.44l-3.2-2.5c-.9.6-2.05.95-3.4.95-2.6 0-4.8-1.76-5.6-4.13H3.1v2.6A10 10 0 0 0 12 22z" fill="#34A853" />
          <path d="M6.4 13.88 a6 6 0 0 1 0-3.76V7.52H3.1a10 10 0 0 0 0 8.96z" fill="#FBBC05" />
          <path d="M12 5.98 c1.47 0 2.79.5 3.83 1.5l2.84-2.84C16.96 2.99 14.7 2 12 2A10 10 0 0 0 3.1 7.52l3.3 2.6C7.2 7.74 9.4 5.98 12 5.98z" fill="#EA4335" />
        </svg>
      );
    default: // echo / fallback — a neutral chat bubble
      return (
        <svg viewBox="0 0 24 24" style={wrap} aria-label={id}>
          <path d="M4 4 h16 a2 2 0 0 1 2 2 v9 a2 2 0 0 1-2 2 H9 l-4 4 v-4 H4 a2 2 0 0 1-2-2 V6 a2 2 0 0 1 2-2z" fill="#616061" />
        </svg>
      );
  }
}

// Google Drive file-type icons (Docs/Sheets/Slides/PDF/image/folder) for the Workspace file browser.
export function FileIcon({ mimeType, size = 18 }: { mimeType: string; size?: number }) {
  const s = { width: size, height: size, display: "block", flexShrink: 0 } as const;
  const folder = mimeType === "application/vnd.google-apps.folder";
  if (folder)
    return (
      <svg viewBox="0 0 24 24" style={s} aria-label="Folder">
        <path d="M3 6 a2 2 0 0 1 2-2 h5 l2 2 h7 a2 2 0 0 1 2 2 v8 a2 2 0 0 1-2 2 H5 a2 2 0 0 1-2-2z" fill="#5f6368" />
      </svg>
    );
  // a rounded "page" with a folded corner, tinted per type + a white glyph
  const type =
    mimeType === "application/vnd.google-apps.document"
      ? { c: "#4285F4", glyph: <g stroke="#fff" strokeWidth="1.3" strokeLinecap="round"><line x1="9" y1="12" x2="15" y2="12" /><line x1="9" y1="15" x2="15" y2="15" /><line x1="9" y1="18" x2="13" y2="18" /></g> }
      : mimeType === "application/vnd.google-apps.spreadsheet"
      ? { c: "#0F9D58", glyph: <g stroke="#fff" strokeWidth="1.2"><rect x="9" y="11.5" width="6" height="7" fill="none" /><line x1="9" y1="14.8" x2="15" y2="14.8" /><line x1="12" y1="11.5" x2="12" y2="18.5" /></g> }
      : mimeType === "application/vnd.google-apps.presentation"
      ? { c: "#F4B400", glyph: <rect x="9" y="12" width="6" height="4.5" rx="0.5" fill="none" stroke="#fff" strokeWidth="1.3" /> }
      : mimeType === "application/pdf"
      ? { c: "#EA4335", glyph: <text x="12" y="18" textAnchor="middle" fontSize="4.4" fontWeight="700" fill="#fff">PDF</text> }
      : mimeType?.startsWith("image/")
      ? { c: "#EA4335", glyph: <g><circle cx="10.5" cy="13" r="1" fill="#fff" /><path d="M9 18 l2-2.5 1.5 1.7 1.5-2.2 2 3z" fill="#fff" /></g> }
      : { c: "#5f6368", glyph: <g stroke="#fff" strokeWidth="1.3" strokeLinecap="round"><line x1="9" y1="13" x2="15" y2="13" /><line x1="9" y1="16" x2="15" y2="16" /></g> };
  return (
    <svg viewBox="0 0 24 24" style={s} aria-label={type.c}>
      <path d="M6 3 h8 l4 4 v12 a2 2 0 0 1-2 2 H6 a2 2 0 0 1-2-2 V5 a2 2 0 0 1 2-2z" fill={type.c} />
      <path d="M14 3 l4 4 h-4z" fill="#000" opacity="0.18" />
      {type.glyph}
    </svg>
  );
}
