import { COLORS } from "@/components/miniature/palette";
import {
  VESSEL_CLASS_LIST,
  type VesselClass,
} from "@/lib/maritime/traffic-types";

interface VesselShape {
  outline: string;
  detail?: string;
}

/** Plan views share the same geometry in the chart and its filter legend. */
export const VESSEL_SHAPES: Record<VesselClass, VesselShape> = {
  container: {
    outline: "M12 3 17.5 8 17.5 24 6.5 24 6.5 8Z",
    detail: "M8.5 10H15.5M8.5 14H15.5M8.5 18H15.5M8.5 22H15.5M12 9V22",
  },
  tanker: {
    outline:
      "M12 3C16 4 18 8 18 12C18 18 15 22 13.5 24H10.5C9 22 6 18 6 12C6 8 8 4 12 3Z",
    detail: "M12 8V20M9.5 12H14.5M9.5 16H14.5",
  },
  bulk: {
    outline: "M12 2.8 18 16 17 24H7L6 16Z",
    detail: "M12 9 14 13H10ZM9 16H15V19H9ZM9 21H15",
  },
  lng: {
    outline:
      "M12 3C15.7 5 17.5 8 17.5 11V22Q17.5 24 15 24H9Q6.5 24 6.5 22V11C6.5 8 8.3 5 12 3Z",
    detail:
      "M14 10a2 2 0 1 1-4 0 2 2 0 1 1 4 0ZM14 15.5a2 2 0 1 1-4 0 2 2 0 1 1 4 0ZM14 21a2 2 0 1 1-4 0 2 2 0 1 1 4 0Z",
  },
  roro: {
    outline: "M8 5 12 3 16 5 18 11V24H6V11Z",
    detail: "M9 9H15V20H9ZM12 21V24",
  },
  cargo: {
    outline: "M12 3 17 11 16 23 12 25 8 23 7 11Z",
    detail: "M10 10H14V15H10ZM10 17H14V22H10Z",
  },
  passenger: {
    outline: "M12 2.5Q17.5 7 17.5 14L15.5 23 12 25 8.5 23 6.5 14Q6.5 7 12 2.5Z",
    detail: "M10 9V21M14 9V21M10 14H14",
  },
  service: {
    outline: "M12 5.5Q18 8 18 13L16.5 21H7.5L6 13Q6 8 12 5.5Z",
    detail: "M9 11H15V15H9ZM9.5 18H14.5",
  },
};

const HULL: VesselShape = {
  outline: "M12 3Q17.5 8 17.5 14L16.5 24H7.5L6.5 14Q6.5 8 12 3Z",
};
const RING: VesselShape = {
  outline: "M18 14a6 6 0 1 1-12 0 6 6 0 1 1 12 0Z",
  detail: "M9 14H15",
};
const STOPPED = "M10 25.5H14";
const WAKE = "M9.5 24.5 7.5 28.5M14.5 24.5 16.5 28.5";

type Ink = VesselClass | "neutral" | "follow";

export function vesselIconId(
  vesselClass: VesselClass,
  ink: Ink,
  detailed: boolean,
  stopped: boolean,
): string {
  const shape = detailed ? vesselClass : stopped ? "ring" : "hull";
  return `ship-${ink}-${shape}-${stopped ? "still" : "moving"}`;
}

export interface IconImage {
  id: string;
  data: ImageData;
  pixelRatio: number;
}

function drawSprite(
  ctx: CanvasRenderingContext2D,
  shape: VesselShape,
  color: string,
  detailed: boolean,
  stopped: boolean,
  followed: boolean,
) {
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  if (followed && !stopped) {
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.15;
    ctx.globalAlpha = 0.58;
    ctx.stroke(new Path2D(WAKE));
    ctx.globalAlpha = 1;
  }
  const outline = new Path2D(shape.outline);
  const ring = shape === RING;
  ctx.fillStyle = ring ? COLORS.panel : color;
  ctx.fill(outline);
  ctx.strokeStyle = ring ? color : COLORS.panel;
  ctx.lineWidth = ring ? 1.65 : 1.2;
  ctx.stroke(outline);
  if (shape.detail) {
    ctx.lineWidth = 1.15;
    ctx.stroke(new Path2D(shape.detail));
  }
  if (detailed && stopped) {
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.45;
    ctx.stroke(new Path2D(STOPPED));
  }
}

/** Rasterize once per chart. MapLibre rotates the images without a DOM node per ship. */
export function buildVesselIcons(pixelRatio = 2): IconImage[] {
  if (typeof document === "undefined") return [];
  const canvas = document.createElement("canvas");
  canvas.width = 24 * pixelRatio;
  canvas.height = 30 * pixelRatio;
  const ctx = canvas.getContext("2d");
  if (!ctx) return [];
  ctx.scale(pixelRatio, pixelRatio);
  const images = new Map<string, IconImage>();

  for (const spec of VESSEL_CLASS_LIST) {
    for (const [ink, color] of [
      [spec.key, spec.color],
      ["neutral", COLORS.modelInk],
      ["follow", COLORS.action],
    ] as const) {
      for (const detailed of [false, true]) {
        for (const stopped of [false, true]) {
          const id = vesselIconId(spec.key, ink, detailed, stopped);
          if (images.has(id)) continue;
          ctx.clearRect(0, 0, 24, 30);
          const shape = detailed
            ? VESSEL_SHAPES[spec.key]
            : stopped
              ? RING
              : HULL;
          drawSprite(ctx, shape, color, detailed, stopped, ink === "follow");
          images.set(id, {
            id,
            data: ctx.getImageData(0, 0, canvas.width, canvas.height),
            pixelRatio,
          });
        }
      }
    }
  }
  return [...images.values()];
}
