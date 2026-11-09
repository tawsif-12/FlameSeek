import { Matrix4, Vector3 } from "three";

// Art-directed paths for the hero, not ephemerides or live satellite positions.
export const HERO_ORBITS = [
  { name: "Terra", sensor: "MODIS", radius: 2.43, eccentricity: 0.025, inclination: 0.38, node: -1.12, periapsis: 0.35, speed: 0.205, phase: 0.25, spin: 0.16, image: "/satellites/hero-terra.png", imageAspect: 650 / 800, imageSize: 0.56, color: 0x38bdf8 },
  { name: "Aqua", sensor: "MODIS", radius: 2.51, eccentricity: 0.018, inclination: 1.04, node: 0.28, periapsis: 1.45, speed: -0.157, phase: 2.15, spin: -0.11, image: "/satellites/hero-aqua.png", imageAspect: 720 / 480, imageSize: 0.65, color: 0x00f2fe },
  { name: "Suomi-NPP", sensor: "VIIRS", radius: 2.58, eccentricity: 0.032, inclination: 1.68, node: 1.62, periapsis: -0.65, speed: 0.246, phase: 4.10, spin: 0.21, image: "/satellites/hero-aqua.png", imageAspect: 720 / 480, imageSize: 0.59, color: 0x7dd3fc },
  { name: "NOAA-20", sensor: "VIIRS", radius: 2.47, eccentricity: 0.022, inclination: 2.12, node: 2.58, periapsis: 0.90, speed: -0.188, phase: 5.35, spin: -0.18, image: "/satellites/hero-terra.png", imageAspect: 650 / 800, imageSize: 0.52, color: 0xf59e0b },
  { name: "NOAA-21", sensor: "VIIRS", radius: 2.63, eccentricity: 0.028, inclination: 2.62, node: -2.28, periapsis: -1.25, speed: 0.129, phase: 1.20, spin: 0.095, image: "/satellites/hero-aqua.png", imageAspect: 720 / 480, imageSize: 0.57, color: 0xffb066 },
] as const;

export type HeroOrbit = typeof HERO_ORBITS[number];
const transforms = new Map<HeroOrbit, Matrix4>(HERO_ORBITS.map((orbit) => {
  // Classical orbital-element order: argument of periapsis, inclination,
  // then longitude of ascending node. This produces genuinely distinct planes.
  const transform = new Matrix4()
    .makeRotationZ(orbit.node)
    .multiply(new Matrix4().makeRotationX(orbit.inclination))
    .multiply(new Matrix4().makeRotationZ(orbit.periapsis));
  return [orbit, transform];
}));

/** The same transform drives satellite positions, full paths, and trailing arcs. */
export function orbitPosition(orbit: HeroOrbit, angle: number, target = new Vector3()) {
  const semiMinor = orbit.radius * Math.sqrt(1 - orbit.eccentricity ** 2);
  return target.set(
    orbit.radius * (Math.cos(angle) - orbit.eccentricity),
    semiMinor * Math.sin(angle),
    0,
  ).applyMatrix4(transforms.get(orbit)!);
}
