import { Euler, Vector3 } from "three";

// Art-directed paths for the hero, not ephemerides or live satellite positions.
export const HERO_ORBITS = [
  { name: "Terra", sensor: "MODIS", radius: 2.40, inclination: 0.92, node: 0.25, speed: 0.23, phase: 0.35, color: 0x38bdf8 },
  { name: "Aqua", sensor: "MODIS", radius: 2.44, inclination: 1.12, node: 1.15, speed: 0.21, phase: 1.75, color: 0x00f2fe },
  { name: "Suomi-NPP", sensor: "VIIRS", radius: 2.48, inclination: 0.78, node: 2.25, speed: 0.25, phase: 3.10, color: 0x7dd3fc },
  { name: "NOAA-20", sensor: "VIIRS", radius: 2.46, inclination: 1.32, node: -0.65, speed: 0.20, phase: 4.45, color: 0xf59e0b },
  { name: "NOAA-21", sensor: "VIIRS", radius: 2.52, inclination: 1.02, node: -1.55, speed: 0.22, phase: 5.60, color: 0xffb066 },
] as const;

export type HeroOrbit = typeof HERO_ORBITS[number];
const rotations = new Map<HeroOrbit, Euler>(HERO_ORBITS.map((orbit) =>
  [orbit, new Euler(orbit.inclination, 0, orbit.node, "XYZ")],
));

/** The same transform drives satellite positions, full paths, and trailing arcs. */
export function orbitPosition(orbit: HeroOrbit, angle: number, target = new Vector3()) {
  return target.set(Math.cos(angle) * orbit.radius, Math.sin(angle) * orbit.radius, 0)
    .applyEuler(rotations.get(orbit)!);
}
