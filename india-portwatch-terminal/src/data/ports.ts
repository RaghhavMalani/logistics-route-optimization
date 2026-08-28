import type { Chokepoint, ChokepointRoute, Port, PortRisk, RiskLevel } from "@/types/portwatch";

export const ports: Port[] = [
  { code: "INMUN", name: "Mundra", authority: "Adani Ports and SEZ", short: "MUN", location: { lat: 22.74, lon: 69.7 }, radar: { x: 0.28, y: 0.36 }, schematic: { x: 210, y: 340 }, coast: "west" },
  { code: "INIXY", name: "Deendayal / Kandla", authority: "Deendayal Port Authority", short: "KDL", location: { lat: 23.02, lon: 70.22 }, radar: { x: 0.31, y: 0.34 }, schematic: { x: 235, y: 320 }, coast: "west" },
  { code: "INBOM", name: "Mumbai", authority: "Mumbai Port Authority", short: "BOM", location: { lat: 18.95, lon: 72.83 }, radar: { x: 0.36, y: 0.51 }, schematic: { x: 295, y: 470 }, coast: "west" },
  { code: "INNSA", name: "JNPT / Nhava Sheva", authority: "Jawaharlal Nehru Port Authority", short: "JNP", location: { lat: 18.95, lon: 72.95 }, radar: { x: 0.365, y: 0.53 }, schematic: { x: 305, y: 482 }, coast: "west" },
  { code: "INMRM", name: "Mormugao", authority: "Mormugao Port Authority", short: "MRM", location: { lat: 15.41, lon: 73.8 }, radar: { x: 0.39, y: 0.59 }, schematic: { x: 335, y: 570 }, coast: "west" },
  { code: "ININM", name: "New Mangalore", authority: "New Mangalore Port Authority", short: "NML", location: { lat: 12.92, lon: 74.8 }, radar: { x: 0.41, y: 0.65 }, schematic: { x: 355, y: 635 }, coast: "west" },
  { code: "INCOK", name: "Cochin", authority: "Cochin Port Authority", short: "COK", location: { lat: 9.96, lon: 76.24 }, radar: { x: 0.44, y: 0.73 }, schematic: { x: 400, y: 720 }, coast: "west" },
  { code: "INTUT", name: "Tuticorin (V.O.C.)", authority: "V.O. Chidambaranar Port Authority", short: "TUT", location: { lat: 8.79, lon: 78.13 }, radar: { x: 0.485, y: 0.77 }, schematic: { x: 465, y: 762 }, coast: "east" },
  { code: "INMAA", name: "Chennai", authority: "Chennai Port Authority", short: "MAA", location: { lat: 13.08, lon: 80.29 }, radar: { x: 0.55, y: 0.63 }, schematic: { x: 545, y: 635 }, coast: "east" },
  { code: "INENR", name: "Kamarajar / Ennore", authority: "Kamarajar Port Limited", short: "ENR", location: { lat: 13.25, lon: 80.33 }, radar: { x: 0.552, y: 0.615 }, schematic: { x: 552, y: 628 }, coast: "east" },
  { code: "INVTZ", name: "Visakhapatnam", authority: "Visakhapatnam Port Authority", short: "VTZ", location: { lat: 17.68, lon: 83.21 }, radar: { x: 0.585, y: 0.53 }, schematic: { x: 610, y: 500 }, coast: "east" },
  { code: "INPRT", name: "Paradip", authority: "Paradip Port Authority", short: "PRT", location: { lat: 20.26, lon: 86.67 }, radar: { x: 0.615, y: 0.44 }, schematic: { x: 675, y: 425 }, coast: "east" },
  { code: "INHAL", name: "Haldia / Kolkata", authority: "Syama Prasad Mookerjee Port", short: "HAL", location: { lat: 22.03, lon: 88.06 }, radar: { x: 0.63, y: 0.375 }, schematic: { x: 720, y: 370 }, coast: "east" },
  { code: "INPBR", name: "Port Blair", authority: "Port Blair Authority", short: "PBL", location: { lat: 11.6234, lon: 92.7265 }, radar: { x: 0.75, y: 0.50 }, schematic: { x: 750, y: 500 }, coast: "east" },
  { code: "INDHM", name: "Dhamra", authority: "Dhamra Port Authority", short: "DHM", location: { lat: 20.7820, lon: 86.9850 }, radar: { x: 0.68, y: 0.29 }, schematic: { x: 680, y: 290 }, coast: "east" },
  { code: "INKPT", name: "Krishnapatnam", authority: "Krishnapatnam Port Authority", short: "KPT", location: { lat: 14.25, lon: 80.12 }, radar: { x: 0.59, y: 0.44 }, schematic: { x: 590, y: 440 }, coast: "east" },
  { code: "INHAZ", name: "Hazira", authority: "Hazira Port Authority", short: "HAZ", location: { lat: 21.1167, lon: 72.65 }, radar: { x: 0.50, y: 0.28 }, schematic: { x: 500, y: 280 }, coast: "west" },
];

export const portRisks: PortRisk[] = [
  { portCode: "INMUN", risk: "congested", congestion: 0.62, delayHours: 14, throughput: 178, vessels: 82, confidence: 0.88, regime: "CONGESTED_MED", updatedAt: "08:41Z" },
  { portCode: "INIXY", risk: "congested", congestion: 0.58, delayHours: 12, throughput: 141, vessels: 61, confidence: 0.84, regime: "CONGESTED_MED", updatedAt: "08:38Z" },
  { portCode: "INBOM", risk: "severe", congestion: 0.83, delayHours: 22, throughput: 96, vessels: 54, confidence: 0.91, regime: "CONGESTED_HIGH", updatedAt: "08:31Z" },
  { portCode: "INNSA", risk: "severe", congestion: 0.79, delayHours: 19, throughput: 208, vessels: 71, confidence: 0.93, regime: "CONGESTED_HIGH", updatedAt: "08:30Z" },
  { portCode: "INMRM", risk: "normal", congestion: 0.34, delayHours: 6, throughput: 44, vessels: 22, confidence: 0.82, regime: "NORMAL", updatedAt: "08:22Z" },
  { portCode: "ININM", risk: "normal", congestion: 0.28, delayHours: 5, throughput: 41, vessels: 19, confidence: 0.79, regime: "NORMAL", updatedAt: "08:22Z" },
  { portCode: "INCOK", risk: "congested", congestion: 0.55, delayHours: 11, throughput: 63, vessels: 34, confidence: 0.85, regime: "CONGESTED_MED", updatedAt: "08:27Z" },
  { portCode: "INTUT", risk: "normal", congestion: 0.31, delayHours: 6, throughput: 38, vessels: 18, confidence: 0.8, regime: "NORMAL", updatedAt: "08:16Z" },
  { portCode: "INMAA", risk: "severe", congestion: 0.86, delayHours: 24, throughput: 152, vessels: 68, confidence: 0.94, regime: "CONGESTED_HIGH", updatedAt: "08:44Z" },
  { portCode: "INENR", risk: "congested", congestion: 0.61, delayHours: 13, throughput: 88, vessels: 41, confidence: 0.87, regime: "CONGESTED_MED", updatedAt: "08:38Z" },
  { portCode: "INVTZ", risk: "congested", congestion: 0.57, delayHours: 12, throughput: 121, vessels: 49, confidence: 0.86, regime: "CONGESTED_MED", updatedAt: "08:36Z" },
  { portCode: "INPRT", risk: "lowconf", congestion: 0.48, delayHours: 9, throughput: 104, vessels: 37, confidence: 0.52, regime: "WATCH_LOW_CONF", updatedAt: "07:52Z" },
  { portCode: "INHAL", risk: "congested", congestion: 0.6, delayHours: 13, throughput: 87, vessels: 40, confidence: 0.83, regime: "CONGESTED_MED", updatedAt: "08:10Z" },
];

export const chokepoints: Chokepoint[] = [
  { code: "HRMZ", name: "HORMUZ STRAIT", radar: { x: 0.18, y: 0.28 }, location: { lat: 26.57, lon: 56.25 }, status: "elevated" },
  { code: "BAB", name: "BAB-EL-MANDEB", radar: { x: 0.14, y: 0.66 }, location: { lat: 12.58, lon: 43.33 }, status: "watch" },
  { code: "SUEZ", name: "SUEZ CANAL", radar: { x: 0.06, y: 0.1 }, location: { lat: 30, lon: 32.55 }, status: "normal" },
  { code: "MLC", name: "MALACCA STRAIT", radar: { x: 0.94, y: 0.82 }, location: { lat: 2.5, lon: 101.5 }, status: "severe" },
];

export const chokepointRoutes: ChokepointRoute[] = [
  { fromPortCode: "INNSA", toChokepointCode: "HRMZ", label: "IN -> Hormuz", risk: "elevated" },
  { fromPortCode: "INMUN", toChokepointCode: "SUEZ", label: "IN -> Suez", risk: "watch" },
  { fromPortCode: "INCOK", toChokepointCode: "BAB", label: "IN -> Bab-el-Mandeb", risk: "watch" },
  { fromPortCode: "INMAA", toChokepointCode: "MLC", label: "IN -> Malacca", risk: "severe" },
  { fromPortCode: "INVTZ", toChokepointCode: "MLC", label: "VTZ -> Malacca", risk: "severe" },
];

export const riskColor: Record<RiskLevel, string> = {
  normal: "var(--color-mint)",
  congested: "var(--color-amber)",
  severe: "var(--color-red)",
  lowconf: "var(--color-purple)",
};

export const riskColorHex: Record<RiskLevel, string> = {
  normal: "#7ef0b4",
  congested: "#ffb347",
  severe: "#ff5566",
  lowconf: "#c58cff",
};

export const riskLabel: Record<RiskLevel, string> = {
  normal: "NORMAL",
  congested: "CONGESTED",
  severe: "SEVERE",
  lowconf: "LOW CONF",
};
