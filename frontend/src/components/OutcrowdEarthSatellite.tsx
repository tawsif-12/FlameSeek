import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { HERO_ORBITS, orbitPosition } from "./heroOrbits";

interface OutcrowdEarthSatelliteProps {
  activeSatellite?: "terra" | "aqua" | "snpp" | "noaa20";
  onSatelliteSelect?: (sat: "terra" | "aqua" | "snpp" | "noaa20") => void;
  targetHotspots?: { lat: number; lon: number; frp?: number | null }[];
}

// Convert Lat/Lon to 3D Cartesian coordinates on sphere of given radius
function latLonToVector3(lat: number, lon: number, radius: number): THREE.Vector3 {
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lon + 180) * (Math.PI / 180);
  const x = -(radius * Math.sin(phi) * Math.cos(theta));
  const z = radius * Math.sin(phi) * Math.sin(theta);
  const y = radius * Math.cos(phi);
  return new THREE.Vector3(x, y, z);
}

// Procedural 3D Satellite Model
function createSatelliteModel(): THREE.Group {
  const satGroup = new THREE.Group();

  // 1. Satellite Bus (Main Body) - gold MLI thermal blanket
  const busGeo = new THREE.BoxGeometry(0.32, 0.46, 0.32);
  const busMat = new THREE.MeshStandardMaterial({
    color: 0xe6b800,
    metalness: 0.88,
    roughness: 0.22,
    envMapIntensity: 1.5,
  });
  const bus = new THREE.Mesh(busGeo, busMat);
  satGroup.add(bus);

  // Equipment bays and radiator panels (silver/dark panels)
  const radiatorGeo = new THREE.BoxGeometry(0.325, 0.38, 0.08);
  const radiatorMat = new THREE.MeshStandardMaterial({
    color: 0x222a38,
    metalness: 0.6,
    roughness: 0.4,
  });
  const radiator = new THREE.Mesh(radiatorGeo, radiatorMat);
  satGroup.add(radiator);

  // 2. Solar Array Wings (Left & Right)
  const wingGroup = new THREE.Group();
  const solarPanelGeo = new THREE.BoxGeometry(0.85, 0.36, 0.015);
  const solarPanelMat = new THREE.MeshStandardMaterial({
    color: 0x0a2246,
    roughness: 0.15,
    metalness: 0.85,
    emissive: 0x051326,
  });

  const boomGeo = new THREE.CylinderGeometry(0.012, 0.012, 0.25, 8);
  const boomMat = new THREE.MeshStandardMaterial({ color: 0x8892a0, metalness: 0.9, roughness: 0.2 });

  // Left wing
  const leftWing = new THREE.Mesh(solarPanelGeo, solarPanelMat);
  leftWing.position.x = -0.72;
  const leftBoom = new THREE.Mesh(boomGeo, boomMat);
  leftBoom.rotation.z = Math.PI / 2;
  leftBoom.position.x = -0.22;
  wingGroup.add(leftWing, leftBoom);

  // Right wing
  const rightWing = new THREE.Mesh(solarPanelGeo, solarPanelMat);
  rightWing.position.x = 0.72;
  const rightBoom = new THREE.Mesh(boomGeo, boomMat);
  rightBoom.rotation.z = Math.PI / 2;
  rightBoom.position.x = 0.22;
  wingGroup.add(rightWing, rightBoom);

  // Solar cell grid busbars overlay
  const cellLinesGeo = new THREE.BoxGeometry(0.852, 0.004, 0.018);
  const cellLineMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8 });
  const leftLine = new THREE.Mesh(cellLinesGeo, cellLineMat);
  leftLine.position.x = -0.72;
  const rightLine = new THREE.Mesh(cellLinesGeo, cellLineMat);
  rightLine.position.x = 0.72;
  wingGroup.add(leftLine, rightLine);

  satGroup.add(wingGroup);

  // 3. Parabolic High-Gain Antenna Dish
  const dishGeo = new THREE.SphereGeometry(0.14, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2);
  const dishMat = new THREE.MeshStandardMaterial({
    color: 0xf1f5f9,
    metalness: 0.7,
    roughness: 0.3,
    side: THREE.DoubleSide,
  });
  const dish = new THREE.Mesh(dishGeo, dishMat);
  dish.rotation.x = -Math.PI / 2;
  dish.position.set(0, 0, 0.22);
  satGroup.add(dish);

  // Antenna Feed Horn
  const feedGeo = new THREE.CylinderGeometry(0.008, 0.012, 0.1, 8);
  const feedMat = new THREE.MeshStandardMaterial({ color: 0xffd700, metalness: 0.9, roughness: 0.1 });
  const feed = new THREE.Mesh(feedGeo, feedMat);
  feed.rotation.x = Math.PI / 2;
  feed.position.set(0, 0, 0.28);
  satGroup.add(feed);

  // 4. Optical & Thermal IR Sensor Payload (MODIS/VIIRS nadir scanner)
  const sensorGeo = new THREE.CylinderGeometry(0.065, 0.075, 0.12, 16);
  const sensorMat = new THREE.MeshStandardMaterial({
    color: 0x111827,
    metalness: 0.9,
    roughness: 0.2,
  });
  const sensor = new THREE.Mesh(sensorGeo, sensorMat);
  sensor.position.set(0, -0.28, 0);
  satGroup.add(sensor);

  // Glowing optical lens aperture
  const lensGeo = new THREE.CircleGeometry(0.055, 16);
  const lensMat = new THREE.MeshBasicMaterial({ color: 0x00f2fe });
  const lens = new THREE.Mesh(lensGeo, lensMat);
  lens.rotation.x = Math.PI / 2;
  lens.position.set(0, -0.342, 0);
  satGroup.add(lens);

  // Thrusters / RCS Nozzles
  const nozzleGeo = new THREE.ConeGeometry(0.02, 0.04, 8);
  const nozzleMat = new THREE.MeshStandardMaterial({ color: 0x475569, metalness: 0.8 });
  const nozzle1 = new THREE.Mesh(nozzleGeo, nozzleMat);
  nozzle1.position.set(0.12, 0.24, 0.12);
  const nozzle2 = new THREE.Mesh(nozzleGeo, nozzleMat);
  nozzle2.position.set(-0.12, 0.24, -0.12);
  satGroup.add(nozzle1, nozzle2);

  satGroup.scale.set(0.85, 0.85, 0.85);
  return satGroup;
}

function createImageSatelliteModel(texture: THREE.Texture, aspect: number, size: number) {
  const group = new THREE.Group();
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    alphaTest: 0.025,
    depthTest: true,
    depthWrite: false,
    toneMapped: false,
  });
  const billboard = new THREE.Sprite(material);
  if (aspect >= 1) billboard.scale.set(size, size / aspect, 1);
  else billboard.scale.set(size * aspect, size, 1);
  group.add(billboard);
  return { group, billboard };
}

function createSatelliteLabel(name: string, sensor: string): THREE.Sprite {
  const canvas = document.createElement("canvas");
  canvas.width = 384;
  canvas.height = 64;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "rgba(3, 7, 18, 0.8)";
  ctx.fillRect(0, 0, 384, 64);
  ctx.font = "600 26px system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#e0f2fe";
  ctx.fillText(`${name} ? ${sensor}`, 192, 32);
  const map = new THREE.CanvasTexture(canvas);
  map.colorSpace = THREE.SRGBColorSpace;
  const label = new THREE.Sprite(new THREE.SpriteMaterial({ map, depthTest: true, depthWrite: false }));
  label.scale.set(0.56, 0.093, 1);
  return label;
}

// Decorative fallback locations for the homepage, explicitly labelled below.
const ILLUSTRATIVE_HOTSPOTS = [
  { lat: 23.8, lon: 90.4 }, { lat: 15, lon: 100 }, { lat: -2, lon: 112 },
  { lat: 29, lon: 78 }, { lat: 35, lon: 105 }, { lat: -18, lon: 135 },
  { lat: 5, lon: 22 }, { lat: -15, lon: 30 }, { lat: 40, lon: 24 },
  { lat: -9, lon: -55 }, { lat: 38, lon: -120 }, { lat: 10, lon: -72 },
];

export default function OutcrowdEarthSatellite({
  targetHotspots = [],
}: OutcrowdEarthSatelliteProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [isReady, setIsReady] = useState(false);
  const targetPinsRef = useRef<THREE.Group[]>([]);
  const displayedHotspots = targetHotspots.length ? targetHotspots : ILLUSTRATIVE_HOTSPOTS;
  const initialTargetsRef = useRef(displayedHotspots);

  useEffect(() => {
    targetPinsRef.current.forEach((pin, index) => {
      const point = displayedHotspots[index];
      pin.visible = !!point;
      if (point) {
        pin.position.copy(latLonToVector3(point.lat, point.lon, 2.11));
        pin.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), pin.position.clone().normalize());
      }
    });
  }, [displayedHotspots]);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    let animationId: number;
    let isDisposed = false;
    let needsRender = true;
    let isInView = true;
    let revealed = false;
    let detailRequested = false;
    let detailTexture: THREE.Texture | undefined;
    let detailTimer: ReturnType<typeof setTimeout> | undefined;
    const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
    let reducedMotion = motionPreference.matches;

    // Dimensions
    const width = container.clientWidth || window.innerWidth;
    const height = container.clientHeight || 750;

    // 1. Scene, Camera, Renderer
    const scene = new THREE.Scene();

    const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 1000);
    camera.position.set(0, 0, 6.4);

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
    renderer.setSize(width, height);
    // A modest pixel-ratio cap keeps pointer interaction fluid on dense/retina displays.
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.3));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.25;
    container.appendChild(renderer.domElement);

    // 2. Lighting (Outcrowd dramatic space lighting)
    // Primary sunlight coming from the left/top-left
    const sunLight = new THREE.DirectionalLight(0xffffff, 2.8);
    sunLight.position.set(-6, 3.5, 4.5);
    scene.add(sunLight);

    // Soft celestial ambient light (deep space blue)
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
    scene.add(ambientLight);

    // Rim backlight for horizon specular glow
    const rimLight = new THREE.DirectionalLight(0x00e5ff, 0.7);
    rimLight.position.set(5, -2, -3);
    scene.add(rimLight);

    // 3. Texture Loading
    const textureLoader = new THREE.TextureLoader();
    const onTextureReady = () => { if (!isDisposed) needsRender = true; };
    const earthRadius = 2.05;

    // Day texture
    // Match the small preloaded texture: the first frame must not wait for full detail.
    const dayTexture = textureLoader.load("/textures/earth_day_fast.webp", onTextureReady);
    dayTexture.colorSpace = THREE.SRGBColorSpace;

    // Normal & Specular textures
    const specularTexture = textureLoader.load("/textures/earth_specular_fast.webp", onTextureReady);
    const nightTexture = textureLoader.load("/textures/earth_night_fast.webp", onTextureReady);
    nightTexture.colorSpace = THREE.SRGBColorSpace;

    // 4. Earth Globe Group
    const earthGroup = new THREE.Group();
    earthGroup.position.set(0, 0, 0);
    earthGroup.rotation.set(-0.12, -0.34, -0.12);
    scene.add(earthGroup);

    // Custom Shader Material for Earth: Blends Day, Night City Lights, and Normal/Specular
    const earthCustomShader = new THREE.ShaderMaterial({
      uniforms: {
        dayTexture: { value: dayTexture },
        nightTexture: { value: nightTexture },
        specularMap: { value: specularTexture },
        sunDirection: { value: new THREE.Vector3(-0.3, 0.4, 1.0).normalize() },
      },
      vertexShader: `
        varying vec2 vUv;
        varying vec3 vNormal;
        varying vec3 vWorldPosition;
        void main() {
          vUv = uv;
          vNormal = normalize(mat3(modelMatrix) * normal);
          vec4 worldPos = modelMatrix * vec4(position, 1.0);
          vWorldPosition = worldPos.xyz;
          gl_Position = projectionMatrix * viewMatrix * worldPos;
        }
      `,
      fragmentShader: `
        uniform sampler2D dayTexture;
        uniform sampler2D nightTexture;
        uniform sampler2D specularMap;
        uniform vec3 sunDirection;

        varying vec2 vUv;
        varying vec3 vNormal;
        varying vec3 vWorldPosition;

        void main() {
          vec3 dayColor = texture2D(dayTexture, vUv).rgb;
          vec3 nightColor = texture2D(nightTexture, vUv).rgb;
          float spec = texture2D(specularMap, vUv).r;

          // Compute sunlight cosine
          vec3 normal = normalize(vNormal);
          float NdotL = dot(normal, normalize(sunDirection));

          // Soft terminator transition (-0.1 to 0.2)
          float dayMix = smoothstep(-0.15, 0.25, NdotL);

          // Specular water highlight on sun side
          vec3 viewDir = normalize(cameraPosition - vWorldPosition);
          vec3 halfVec = normalize(normalize(sunDirection) + viewDir);
          float specAngle = max(dot(normal, halfVec), 0.0);
          float specular = pow(specAngle, 32.0) * spec * 0.85 * dayMix;

          // Atmospheric scattering tint on day side
          vec3 atmosphereTint = vec3(0.08, 0.35, 0.65) * pow(1.0 - max(dot(normal, viewDir), 0.0), 3.0) * dayMix;

          // Presentation lighting keeps the natural-color surface readable on the shaded side.
          // This illustrative globe does not represent the current solar terminator.
          float surfaceLight = 0.65 + 0.35 * max(NdotL, 0.0);
          vec3 finalColor = dayColor * surfaceLight
            + nightColor * (1.0 - dayMix) * 0.12
            + vec3(specular * 0.25) + atmosphereTint * 0.3;

          gl_FragColor = vec4(finalColor, 1.0);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }
      `,
    });

    const earthGeometry = new THREE.SphereGeometry(earthRadius, 56, 48);
    const earthMesh = new THREE.Mesh(earthGeometry, earthCustomShader);
    earthGroup.add(earthMesh);

    // 5. Atmospheric Clouds Layer
    const cloudsTexture = textureLoader.load("/textures/earth_clouds_fast.webp", onTextureReady);
    const cloudsGeometry = new THREE.SphereGeometry(earthRadius + 0.028, 48, 40);
    const cloudsMaterial = new THREE.MeshStandardMaterial({
      map: cloudsTexture,
      transparent: true,
      opacity: 0.65,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const cloudsMesh = new THREE.Mesh(cloudsGeometry, cloudsMaterial);
    earthGroup.add(cloudsMesh);

    // A wide atmosphere fades to transparent before its outer edge, so the
    // Earth blends into either theme instead of ending in a bright cyan ring.
    const atmosphereGeometry = new THREE.SphereGeometry(earthRadius * 1.3, 48, 40);
    const atmosphereShader = new THREE.ShaderMaterial({
      side: THREE.BackSide,
      transparent: true,
      depthWrite: false,
      vertexShader: `
        varying vec3 vViewNormal;
        varying vec3 vViewPosition;
        void main() {
          vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
          vViewNormal = normalize(normalMatrix * normal);
          vViewPosition = viewPosition.xyz;
          gl_Position = projectionMatrix * viewPosition;
        }
      `,
      fragmentShader: `
        varying vec3 vViewNormal;
        varying vec3 vViewPosition;
        void main() {
          float facing = abs(dot(normalize(vViewNormal), normalize(-vViewPosition)));
          float radius = sqrt(max(0.0, 1.0 - facing * facing));
          float falloff = exp(-max(radius - 0.72, 0.0) * 12.0);
          float edgeFade = 1.0 - smoothstep(0.88, 1.0, radius);
          vec3 glowColor = mix(vec3(0.12, 0.62, 0.86), vec3(0.38, 0.76, 0.94), radius);
          gl_FragColor = vec4(glowColor, falloff * edgeFade * 0.5);
        }
      `,
    });
    const atmosphereMesh = new THREE.Mesh(atmosphereGeometry, atmosphereShader);
    earthGroup.add(atmosphereMesh);

    // A bounded pool shares geometry and updates without rebuilding the globe.
    const pinDotGeo = new THREE.SphereGeometry(0.035, 8, 8);
    const pinDotMat = new THREE.MeshBasicMaterial({ color: 0xff6b2c });
    const ringGeo = new THREE.RingGeometry(0.05, 0.085, 24);
    const beacons = Array.from({ length: 24 }, (_, index) => {
      const pin = new THREE.Group();
      const point = initialTargetsRef.current[index];
      pin.visible = !!point;
      if (point) {
        pin.position.copy(latLonToVector3(point.lat, point.lon, earthRadius + 0.06));
        pin.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), pin.position.clone().normalize());
      }
      pin.add(new THREE.Mesh(pinDotGeo, pinDotMat));
      const material = new THREE.MeshBasicMaterial({
        color: 0xff4d26, side: THREE.DoubleSide, transparent: true,
        opacity: 0.85, depthWrite: false,
      });
      const ring = new THREE.Mesh(ringGeo, material);
      pin.add(ring);
      earthMesh.add(pin);
      return { pin, ring, material };
    });
    targetPinsRef.current = beacons.map(({ pin }) => pin);

    // The supplied transparent spacecraft artwork is shared as two GPU textures,
    // while every satellite owns its material, rotation, speed, and orbital plane.
    const spacecraftTextures = new Map<string, THREE.Texture>();
    for (const orbit of HERO_ORBITS) {
      if (spacecraftTextures.has(orbit.image)) continue;
      const texture = textureLoader.load(orbit.image, onTextureReady);
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 4);
      spacecraftTextures.set(orbit.image, texture);
    }
    const trailSamples = 28;
    const drawnOrbitPlanes = new Set<string>();
    const fleet = HERO_ORBITS.map((orbit) => {
      const { group: model, billboard } = createImageSatelliteModel(
        spacecraftTextures.get(orbit.image)!, orbit.imageAspect, orbit.imageSize,
      );
      model.name = `${orbit.name} · ${orbit.sensor}`;
      scene.add(model);
      const marker = new THREE.Mesh(
        new THREE.SphereGeometry(0.028, 8, 8),
        new THREE.MeshBasicMaterial({ color: orbit.color }),
      );
      const label = createSatelliteLabel(orbit.name, orbit.sensor);
      scene.add(marker, label);
      const pathPoints = Array.from({ length: 97 }, (_, i) => orbitPosition(orbit, i / 96 * Math.PI * 2));
      const path = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pathPoints),
        new THREE.LineBasicMaterial({ color: orbit.color, transparent: true, opacity: 0.34, depthWrite: false }));
      const planeKey = `${orbit.radius}:${orbit.inclination}:${orbit.node}`;
      if (!drawnOrbitPlanes.has(planeKey)) {
        scene.add(path);
        drawnOrbitPlanes.add(planeKey);
      } else {
        path.geometry.dispose();
        path.material.dispose();
      }
      const trailGeometry = new THREE.BufferGeometry();
      const trailPositions = new Float32Array(trailSamples * 3);
      const trailColors = new Float32Array(trailSamples * 3);
      const color = new THREE.Color(orbit.color);
      for (let i = 0; i < trailSamples; i++) color.clone().multiplyScalar(0.15 + 0.85 * i / (trailSamples - 1)).toArray(trailColors, i * 3);
      const positions = new THREE.BufferAttribute(trailPositions, 3).setUsage(THREE.DynamicDrawUsage);
      trailGeometry.setAttribute("position", positions);
      trailGeometry.setAttribute("color", new THREE.BufferAttribute(trailColors, 3));
      const trail = new THREE.Line(trailGeometry,
        new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.72, depthWrite: false }));
      scene.add(trail);
      return { orbit, model, billboard, marker, label, trail, positions };
    });
    const orbitPoint = new THREE.Vector3();

    // 10. Starfield Background
    const starCount = 1000;
    const starGeo = new THREE.BufferGeometry();
    const starPositions = new Float32Array(starCount * 3);
    const starColors = new Float32Array(starCount * 3);

    for (let i = 0; i < starCount; i++) {
      const idx = i * 3;
      const r = 25 + Math.random() * 45;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(Math.random() * 2 - 1);

      starPositions[idx] = r * Math.sin(phi) * Math.cos(theta);
      starPositions[idx + 1] = r * Math.sin(phi) * Math.sin(theta);
      starPositions[idx + 2] = r * Math.cos(phi);

      // Star hues: icy white, cyan, pale amber
      const hueChoice = Math.random();
      if (hueChoice > 0.7) {
        starColors[idx] = 0.6;
        starColors[idx + 1] = 0.9;
        starColors[idx + 2] = 1.0;
      } else if (hueChoice > 0.4) {
        starColors[idx] = 1.0;
        starColors[idx + 1] = 0.95;
        starColors[idx + 2] = 0.85;
      } else {
        starColors[idx] = 0.95;
        starColors[idx + 1] = 0.98;
        starColors[idx + 2] = 1.0;
      }
    }

    starGeo.setAttribute("position", new THREE.BufferAttribute(starPositions, 3));
    starGeo.setAttribute("color", new THREE.BufferAttribute(starColors, 3));

    const starMat = new THREE.PointsMaterial({
      size: 0.12,
      vertexColors: true,
      transparent: true,
      opacity: 0.88,
    });
    const starField = new THREE.Points(starGeo, starMat);
    scene.add(starField);

    // 11. Mouse & Parallax Interaction
    let isDragging = false;
    let prevPointerX = 0;
    let prevPointerY = 0;
    let earthRotVelocityX = 0;
    let earthRotVelocityY = 0.0027;
    let activePointerId: number | null = null;

    const handlePointerDown = (e: PointerEvent) => {
      isDragging = true;
      activePointerId = e.pointerId;
      prevPointerX = e.clientX;
      prevPointerY = e.clientY;
      dom.setPointerCapture(e.pointerId);
      dom.style.cursor = "grabbing";
      e.preventDefault();
    };

    const handlePointerMove = (e: PointerEvent) => {
      if (isDragging && e.pointerId === activePointerId) {
        const deltaX = e.clientX - prevPointerX;
        const deltaY = e.clientY - prevPointerY;
        earthGroup.rotation.y += deltaX * 0.008;
        earthGroup.rotation.x = THREE.MathUtils.clamp(earthGroup.rotation.x + deltaY * 0.0055, -0.8, 0.8);
        needsRender = true;
        earthRotVelocityX = THREE.MathUtils.clamp(deltaY * 0.00075, -0.024, 0.024);
        earthRotVelocityY = THREE.MathUtils.clamp(deltaX * 0.00105, -0.036, 0.036);
        prevPointerX = e.clientX;
        prevPointerY = e.clientY;
      }
    };

    const handlePointerUp = (e: PointerEvent) => {
      if (activePointerId !== null && e.pointerId !== activePointerId) return;
      isDragging = false;
      if (dom.hasPointerCapture(e.pointerId)) dom.releasePointerCapture(e.pointerId);
      activePointerId = null;
      dom.style.cursor = "grab";
    };

    const dom = renderer.domElement;
    dom.style.touchAction = "none";
    dom.addEventListener("pointerdown", handlePointerDown);
    dom.addEventListener("pointermove", handlePointerMove);
    dom.addEventListener("pointerup", handlePointerUp);
    dom.addEventListener("pointercancel", handlePointerUp);

    // 12. Resize Listener
    const handleResize = () => {
      if (!container || isDisposed) return;
      const newWidth = container.clientWidth || window.innerWidth;
      const newHeight = container.clientHeight || 750;
      camera.aspect = newWidth / newHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(newWidth, newHeight);

      // Fit a consistent circular globe inside the actual canvas, independent of aspect ratio.
      earthGroup.position.set(0, 0, 0);
      const halfFov = THREE.MathUtils.degToRad(camera.fov / 2);
      const globeDiameter = Math.min(newWidth * 0.72, newHeight * 0.70, 450) * 1.27;
      camera.position.z = Math.sqrt(earthRadius ** 2 + (earthRadius * newHeight / (globeDiameter * Math.tan(halfFov))) ** 2);
      // Fit every orbit, including miniature wings/labels, without crossing the canvas edge.
      for (const orbit of HERO_ORBITS) {
        for (let i = 0; i < 48; i++) {
          orbitPosition(orbit, i / 48 * Math.PI * 2, orbitPoint);
          camera.position.z = Math.max(camera.position.z,
            orbitPoint.z + (Math.abs(orbitPoint.x) + 0.30) / (Math.tan(halfFov) * camera.aspect * 0.97),
            orbitPoint.z + (Math.abs(orbitPoint.y) + 0.30) / (Math.tan(halfFov) * 0.97));
        }
      }
      // Bring the complete scene a little closer while retaining the orbit framing.
      camera.position.z = Math.max(earthRadius + 0.7, camera.position.z * 0.92);
      const actualDiameter = earthRadius * newHeight / (Math.tan(halfFov) * Math.sqrt(camera.position.z ** 2 - earthRadius ** 2));
      container.parentElement?.style.setProperty("--earth-preview-size", `${actualDiameter}px`);
      needsRender = true;
    };

    window.addEventListener("resize", handleResize);
    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(container);
    handleResize();

    // Offscreen and reduced-motion views retain a stable frame, without continuous GPU work.
    const visibilityObserver = new IntersectionObserver(([entry]) => {
      isInView = entry.isIntersecting;
      needsRender = true;
    });
    visibilityObserver.observe(container);
    const handleMotionChange = () => { reducedMotion = motionPreference.matches; needsRender = true; };
    motionPreference.addEventListener("change", handleMotionChange);
    let lastFrame = performance.now();
    let time = 0;
    const animate = (now: number) => {
      if (isDisposed) return;
      animationId = requestAnimationFrame(animate);
      const delta = Math.min((now - lastFrame) / 1000, 0.05);
      lastFrame = now;
      if (document.hidden || !isInView || (reducedMotion && !needsRender)) return;
      if (!reducedMotion) time += delta;
      const frameScale = reducedMotion ? 0 : delta * 60;
      if (!isDragging) {
        earthGroup.rotation.y += earthRotVelocityY * frameScale;
        earthGroup.rotation.x += earthRotVelocityX * frameScale;
        earthRotVelocityY = THREE.MathUtils.lerp(earthRotVelocityY, 0.0027, 1 - Math.pow(0.955, frameScale));
        earthRotVelocityX = THREE.MathUtils.lerp(earthRotVelocityX, 0, 1 - Math.pow(0.925, frameScale));
      }
      earthGroup.rotation.z = -0.12 + Math.sin(time * 0.22) * 0.012;
      cloudsMesh.rotation.y += 0.00095 * frameScale;
      cloudsMesh.rotation.x += 0.00014 * frameScale;
      for (const { orbit, model, billboard, marker, label, positions } of fleet) {
        const angle = orbit.phase + time * orbit.speed;
        orbitPosition(orbit, angle, model.position);
        billboard.material.rotation = orbit.phase * 0.17 + time * orbit.spin;
        marker.position.copy(model.position).multiplyScalar(1.045);
        label.position.copy(model.position);
        label.position.y += 0.18;
        for (let i = 0; i < trailSamples; i++) {
          const trailAngle = angle - Math.sign(orbit.speed) * 0.62 * (1 - i / (trailSamples - 1));
          orbitPosition(orbit, trailAngle, orbitPoint);
          positions.setXYZ(i, orbitPoint.x, orbitPoint.y, orbitPoint.z);
        }
        positions.needsUpdate = true;
      }

      // Stagger the pulses so multiple observations remain individually visible.
      beacons.forEach(({ pin, ring, material }, index) => {
        if (!pin.visible) return;
        const pulse = (Math.sin(time * 3 + index * 1.7) + 1) * 0.5;
        ring.scale.setScalar(1 + pulse * 1.4);
        material.opacity = 0.85 - pulse * 0.65;
      });

      // Keep the globe centered; pointer interaction rotates the Earth, not the camera.
      camera.lookAt(earthGroup.position);

      // Subtle starfield twinkling
      starField.rotation.y = time * 0.008;
      starField.rotation.x = Math.sin(time * 0.06) * 0.018;

      renderer.render(scene, camera);
      needsRender = false;
      // Keep the lightweight globe visible until the textured frame is painted.
      if (!revealed && dayTexture.image) {
        revealed = true;
        setIsReady(true);
      }
      if (revealed && !detailRequested) {
        detailRequested = true;
        // Let the browser paint the lightweight globe before downloading the detailed map.
        detailTimer = setTimeout(() => {
          if (isDisposed) return;
          detailTexture = textureLoader.load("/textures/earth_day_2048.jpg", (texture) => {
            if (isDisposed) { texture.dispose(); return; }
            texture.colorSpace = THREE.SRGBColorSpace;
            earthCustomShader.uniforms.dayTexture.value = texture;
            needsRender = true;
          });
        }, 250);
      }
    };

    animate(performance.now());

    // 14. Cleanup
    return () => {
      isDisposed = true;
      cancelAnimationFrame(animationId);
      if (detailTimer !== undefined) clearTimeout(detailTimer);
      detailTexture?.dispose();
      resizeObserver.disconnect();
      visibilityObserver.disconnect();
      motionPreference.removeEventListener("change", handleMotionChange);
      window.removeEventListener("resize", handleResize);
      dom.removeEventListener("pointerdown", handlePointerDown);
      dom.removeEventListener("pointermove", handlePointerMove);
      dom.removeEventListener("pointerup", handlePointerUp);
      dom.removeEventListener("pointercancel", handlePointerUp);

      if (container.contains(dom)) {
        container.removeChild(dom);
      }

      // Cloned satellites share GPU resources: release each one exactly once.
      const geometries = new Set<THREE.BufferGeometry>();
      const materials = new Set<THREE.Material>();
      const textures = new Set<THREE.Texture>([dayTexture, nightTexture, specularTexture, cloudsTexture]);
      scene.traverse((object) => {
        const drawable = object as THREE.Mesh;
        if (drawable.geometry) geometries.add(drawable.geometry);
        if (drawable.material) {
          for (const material of Array.isArray(drawable.material) ? drawable.material : [drawable.material]) materials.add(material);
        }
      });
      for (const material of materials) {
        const map = (material as THREE.MeshBasicMaterial).map;
        if (map) textures.add(map);
        material.dispose();
      }
      geometries.forEach((geometry) => geometry.dispose());
      textures.forEach((texture) => texture.dispose());
      renderer.dispose();
      targetPinsRef.current = [];
    };
  }, []);

  return (
    <div className="outcrowd-3d-wrapper" style={{ position: "relative", width: "100%", height: "100%" }}>
      {!targetHotspots.length && <small style={{ position: "absolute", bottom: 8, left: "50%", transform: "translateX(-50%)", color: "#9eb6c9", fontSize: 11, zIndex: 3 }}>Example heat markers</small>}
      {!isReady && <div className="earth-instant-preview" aria-hidden="true"><div /></div>}
      {/* 3D Canvas Mount Point */}
      <div
        ref={mountRef}
        style={{
          width: "100%",
          height: "100%",
          position: "absolute",
          top: 0,
          left: 0,
          zIndex: 1,
          cursor: "grab",
          opacity: isReady ? 1 : 0,
          transition: "opacity 100ms ease-out",
          touchAction: "none",
        }}
        aria-label="Interactive Earth with illustrative orbits of four satellites (Terra, Aqua, Suomi-NPP, and NOAA-20) on two crossing paths; satellite positions are illustrative"
      />


      {/* Futuristic Orbit HUD Overlays */}
      <div className="outcrowd-hud-overlay" style={{ pointerEvents: "none", position: "absolute", inset: 0, zIndex: 2 }}>
        {/* Subtle Orbit Reticles */}
        <div className="hud-reticle hud-reticle-tl" />
        <div className="hud-reticle hud-reticle-br" />
      </div>
    </div>
  );
}
