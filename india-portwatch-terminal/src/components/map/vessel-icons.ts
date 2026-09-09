/**
 * Ship glyphs, drawn into the GL context as images.
 *
 * MapLibre rotates a symbol's icon per feature, which is the only way to render
 * hundreds of heading-oriented marks without a DOM node each. The alternative --
 * an SDF sprite tinted by expression -- loses the dark outline that keeps a
 * small glyph readable over a bright weather field, so each class gets its own
 * raster at device resolution.
 *
 * Two shapes carry navigation state, because colour is already spoken for by
 * vessel class:
 *
 *   hull   a ship outline, pointed at the course over ground. Under way.
 *   ring   a circle with a bar. Stopped: at anchor, waiting, or alongside.
 */

import { VESSEL_CLASS_LIST, type VesselClass } from "@/lib/maritime/traffic-types";

export type GlyphShape = "hull" | "ring";

export interface IconImage {
  id: string;
  data: ImageData;
  pixelRatio: number;
}

const OUTLINE = "#04121b";

function canvas(size: number): { ctx: CanvasRenderingContext2D; size: number } | null {
  if (typeof document === "undefined") return null;
  const element = document.createElement("canvas");
  element.width = size;
  element.height = size;
  const ctx = element.getContext("2d");
  return ctx ? { ctx, size } : null;
}

/**
 * A ship in plan view, bow up.
 *
 * Drawn as a real hull rather than a triangle: at eleven pixels the difference
 * between "an arrow" and "a vessel" is the flat transom and the shoulder, and
 * it is what makes the map read as marine traffic instead of a scatter plot.
 */
function drawHull(ctx: CanvasRenderingContext2D, size: number, color: string) {
  const c = size / 2;
  const halfLength = size * 0.44;
  const halfBeam = size * 0.2;

  ctx.beginPath();
  ctx.moveTo(c, c - halfLength);
  ctx.quadraticCurveTo(c + halfBeam, c - halfLength * 0.42, c + halfBeam, c + halfLength * 0.2);
  ctx.lineTo(c + halfBeam * 0.82, c + halfLength);
  ctx.lineTo(c - halfBeam * 0.82, c + halfLength);
  ctx.lineTo(c - halfBeam, c + halfLength * 0.2);
  ctx.quadraticCurveTo(c - halfBeam, c - halfLength * 0.42, c, c - halfLength);
  ctx.closePath();

  ctx.fillStyle = color;
  ctx.fill();
  ctx.lineWidth = Math.max(1, size * 0.07);
  ctx.strokeStyle = OUTLINE;
  ctx.stroke();
}

function drawRing(ctx: CanvasRenderingContext2D, size: number, color: string) {
  const c = size / 2;
  const radius = size * 0.3;
  ctx.beginPath();
  ctx.arc(c, c, radius, 0, Math.PI * 2);
  ctx.fillStyle = OUTLINE;
  ctx.fill();
  ctx.lineWidth = Math.max(1.4, size * 0.11);
  ctx.strokeStyle = color;
  ctx.stroke();

  // A short bar across the ring reads as "made fast" rather than "a dot".
  ctx.beginPath();
  ctx.moveTo(c - radius * 0.5, c);
  ctx.lineTo(c + radius * 0.5, c);
  ctx.lineWidth = Math.max(1, size * 0.08);
  ctx.strokeStyle = color;
  ctx.stroke();
}

/** The own-ship mark: the same hull, brighter, with a course lubber line. */
function drawOwn(ctx: CanvasRenderingContext2D, size: number) {
  const c = size / 2;
  ctx.beginPath();
  ctx.arc(c, c, size * 0.46, 0, Math.PI * 2);
  ctx.strokeStyle = "rgba(255,255,255,0.5)";
  ctx.lineWidth = Math.max(1, size * 0.05);
  ctx.stroke();
  drawHull(ctx, size, "#f2f7fb");
}

export function iconId(vesselClass: VesselClass, shape: GlyphShape): string {
  return `ship-${vesselClass}-${shape}`;
}

export const OWN_ICON = "ship-own";

/**
 * Every glyph the map can show. Built once per session; there are seventeen of
 * them and each is a few hundred bytes.
 */
export function buildVesselIcons(pixelRatio = 2): IconImage[] {
  const size = Math.round(22 * pixelRatio);
  const out: IconImage[] = [];

  for (const spec of VESSEL_CLASS_LIST) {
    for (const shape of ["hull", "ring"] as GlyphShape[]) {
      const surface = canvas(size);
      if (!surface) return out;
      if (shape === "hull") drawHull(surface.ctx, size, spec.color);
      else drawRing(surface.ctx, size, spec.color);
      out.push({
        id: iconId(spec.key, shape),
        data: surface.ctx.getImageData(0, 0, size, size),
        pixelRatio,
      });
    }
  }

  const ownSurface = canvas(Math.round(30 * pixelRatio));
  if (ownSurface) {
    drawOwn(ownSurface.ctx, ownSurface.size);
    out.push({
      id: OWN_ICON,
      data: ownSurface.ctx.getImageData(0, 0, ownSurface.size, ownSurface.size),
      pixelRatio,
    });
  }

  return out;
}
