// Official brand SVGs (fetched into ./logos) for the launcher tiles + Google file-type icons for the
// Workspace view. Vite imports each .svg as a URL; we render it in an <img> so the real multicolor
// artwork shows exactly as shipped.
import slack from "./logos/slack.svg";
import jira from "./logos/jira.svg";
import figma from "./logos/figma.svg";
import gauge from "./logos/gauge.svg";
import sentry from "./logos/sentry.svg";
import github from "./logos/github.svg";
import gworkspace from "./logos/gworkspace.svg";
import logfire from "./logos/logfire.svg";
import notion from "./logos/notion.svg";
import aws from "./logos/aws.svg";
import discord from "./logos/discord.svg";
import gdoc from "./logos/gdoc.svg";
import gsheet from "./logos/gsheet.svg";
import gslides from "./logos/gslides.svg";

export const LOGO: Record<string, string> = {
  slack, jira, figma, gauge, sentry, github, gworkspace, logfire, notion, aws, discord,
};

export function BrandIcon({ id, size = 40 }: { id: string; size?: number }) {
  const src = LOGO[id];
  if (!src)
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} style={{ display: "block" }} aria-label={id}>
        <path
          d="M4 4 h16 a2 2 0 0 1 2 2 v9 a2 2 0 0 1-2 2 H9 l-4 4 v-4 H4 a2 2 0 0 1-2-2 V6 a2 2 0 0 1 2-2z"
          fill="#616061"
        />
      </svg>
    );
  return (
    <img
      src={src}
      width={size}
      height={size}
      alt={id}
      style={{ display: "block", width: size, height: size, objectFit: "contain" }}
    />
  );
}

const DOC_LOGO: Record<string, string> = {
  "application/vnd.google-apps.document": gdoc,
  "application/vnd.google-apps.spreadsheet": gsheet,
  "application/vnd.google-apps.presentation": gslides,
};

// Google Drive file-type icons: the real Docs/Sheets/Slides marks; a simple page/folder for the rest.
export function FileIcon({ mimeType, size = 18 }: { mimeType: string; size?: number }) {
  const s = { width: size, height: size, display: "block", flexShrink: 0 } as const;
  if (mimeType === "application/vnd.google-apps.folder")
    return (
      <svg viewBox="0 0 24 24" style={s} aria-label="Folder">
        <path d="M3 6 a2 2 0 0 1 2-2 h5 l2 2 h7 a2 2 0 0 1 2 2 v8 a2 2 0 0 1-2 2 H5 a2 2 0 0 1-2-2z" fill="#5f6368" />
      </svg>
    );
  const brand = DOC_LOGO[mimeType];
  if (brand) return <img src={brand} width={size} height={size} alt={mimeType} style={s} />;

  const isPdf = mimeType === "application/pdf";
  const isImg = mimeType?.startsWith("image/");
  const c = isPdf ? "#EA4335" : isImg ? "#EA4335" : "#5f6368";
  return (
    <svg viewBox="0 0 24 24" style={s} aria-label={mimeType}>
      <path d="M6 3 h8 l4 4 v12 a2 2 0 0 1-2 2 H6 a2 2 0 0 1-2-2 V5 a2 2 0 0 1 2-2z" fill={c} />
      <path d="M14 3 l4 4 h-4z" fill="#000" opacity="0.18" />
      {isPdf ? (
        <text x="12" y="18" textAnchor="middle" fontSize="4.4" fontWeight="700" fill="#fff">PDF</text>
      ) : isImg ? (
        <g>
          <circle cx="10.5" cy="13" r="1" fill="#fff" />
          <path d="M9 18 l2-2.5 1.5 1.7 1.5-2.2 2 3z" fill="#fff" />
        </g>
      ) : (
        <g stroke="#fff" strokeWidth="1.3" strokeLinecap="round">
          <line x1="9" y1="13" x2="15" y2="13" />
          <line x1="9" y1="16" x2="15" y2="16" />
        </g>
      )}
    </svg>
  );
}
