import { Matrix4, Vector3 } from "three";

// Four illustrative satellites share two close, crossing orbital planes.
// These are art-directed paths, not ephemerides or live positions.
export const HERO_ORBITS = [
  { name: "Terra", sensor: "MODIS", radius: 2.38, eccentricity: 0, inclination: 0.95, node: -0.65, periapsis: 0, speed: 0.18, phase: 0.25, spin: 0.16, image: "/satellites/hero-terra.png", imageAspect: 650 / 800, imageSize: 0.56, color: 0x38bdf8 },
  { name: "Aqua", sensor: "MODIS", radius: 2.38, eccentricity: 0, inclination: 0.95, node: 0.65, periapsis: 0, speed: -0.18, phase: 1.82, spin: -0.11, image: "/satellites/hero-aqua.png", imageAspect: 720 / 480, imageSize: 0.65, color: 0x00f2fe },
  { name: "Suomi-NPP", sensor: "VIIRS", radius: 2.38, eccentricity: 0, inclination: 0.95, node: -0.65, periapsis: 0, speed: 0.18, phase: 3.39159265, spin: 0.21, image: "/satellites/hero-aqua.png", imageAspect: 720 / 480, imageSize: 0.59, color: 0x7dd3fc },
  { name: "NOAA-20", sensor: "VIIRS", radius: 2.38, eccentricity: 0, inclination: 0.95, node: 0.65, periapsis: 0, speed: -0.18, phase: 4.96159265, spin: -0.18, image: "/satellites/hero-terra.png", imageAspect: 650 / 800, imageSize: 0.52, color: 0xf59e0b },
] as const;

export type HeroOrbit = typeof HERO_ORBITS[number];
const transforms = new Map<HeroOrbit, Matrix4>(HERO_ORBITS.map((orbit) => {
  // Each pair shares its plane and remains half an orbit apart.
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
