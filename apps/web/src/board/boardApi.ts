import type { Api } from "@lichess-org/chessground/api";

/** The live chessground instance, shared with the position editor's spare-piece palette. */
export const boardApi: { current: Api | null } = { current: null };

function squaresPath(): string {
  let d = "";
  for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) if ((x + y) % 2 === 1) d += `M${x} ${y}h1v1h-1z`;
  return d;
}
const PATH = squaresPath();

/** Checkerboard as an SVG data URL (a1 is dark, as on every real board). */
export function boardImage(light: string, dark: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8" shape-rendering="crispEdges"><rect width="8" height="8" fill="${light}"/><path fill="${dark}" d="${PATH}"/></svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
}
