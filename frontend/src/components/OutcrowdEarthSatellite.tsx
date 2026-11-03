import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { HERO_ORBITS, orbitPosition } from "./heroOrbits";

interface OutcrowdEarthSatelliteProps {
  activeSatellite?: "terra" | "aqua" | "snpp" | "noaa20";
  onSatelliteSelect?: (sat: "terra" | "aqua" | "snpp" | "noaa20") => void;
  targetHotspot?: { lat: number; lon: number; frp?: number | null };
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

export default function OutcrowdEarthSatellite({
  targetHotspot,
}: OutcrowdEarthSatelliteProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [isReady, setIsReady] = useState(false);
  const targetPinRef = useRef<THREE.Group | null>(null);
  const initialTargetRef = useRef(targetHotspot);

  useEffect(() => {
    targetPinRef.current?.position.copy(latLonToVector3(targetHotspot?.lat ?? 23.81, targetHotspot?.lon ?? 90.41, 2.065));
  }, [targetHotspot?.lat, targetHotspot?.lon]);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    let animationId: number;
    let isDisposed = false;
    let needsRender = true;
    let isInView = true;
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
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.25;
    container.appendChild(renderer.domElement);

    // 2. Lighting (Outcrowd dramatic space lighting)
    // Primary sunlight coming from the left/top-left
    const sunLight = new THREE.DirectionalLight(0xffffff, 2.8);
    sunLight.position.set(-6, 3.5, 4.5);
    scene.add(sunLight);

    // Soft celestial ambient light (deep space blue)
    const ambientLight = new THREE.AmbientLight(0x0a1628, 0.35);
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
    const dayTexture = textureLoader.load("/textures/earth_day_fast.webp", onTextureReady);
    dayTexture.colorSpace = THREE.SRGBColorSpace;

    // Normal & Specular textures
    const specularTexture = textureLoader.load("/textures/earth_specular_fast.webp", onTextureReady);
    const nightTexture = textureLoader.load("/textures/earth_night_fast.webp", onTextureReady);
    nightTexture.colorSpace = THREE.SRGBColorSpace;

    // 4. Earth Globe Group
    const earthGroup = new THREE.Group();
    earthGroup.position.set(0, 0, 0);
    scene.add(earthGroup);

    // Custom Shader Material for Earth: Blends Day, Night City Lights, and Normal/Specular
    const earthCustomShader = new THREE.ShaderMaterial({
      uniforms: {
        dayTexture: { value: dayTexture },
        nightTexture: { value: nightTexture },
        specularMap: { value: specularTexture },
        sunDirection: { value: new THREE.Vector3(-0.7, 0.4, 0.6).normalize() },
      },
      vertexShader: `
        varying vec2 vUv;
        varying vec3 vNormal;
        varying vec3 vWorldPosition;
        void main() {
          vUv = uv;
          vNormal = normalize(normalMatrix * normal);
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

          // Night illumination: golden city lights boost
          vec3 illuminatedNight = nightColor * vec3(1.3, 1.1, 0.8) * 1.5;

          // Final color composition
          vec3 finalColor = mix(illuminatedNight, dayColor, dayMix) + vec3(specular) + atmosphereTint;

          gl_FragColor = vec4(finalColor, 1.0);
        }
      `,
    });

    const earthGeometry = new THREE.SphereGeometry(earthRadius, 64, 64);
    const earthMesh = new THREE.Mesh(earthGeometry, earthCustomShader);
    earthGroup.add(earthMesh);

    // 5. Atmospheric Clouds Layer
    const cloudsTexture = textureLoader.load("/textures/earth_clouds_fast.webp", onTextureReady);
    const cloudsGeometry = new THREE.SphereGeometry(earthRadius + 0.028, 64, 64);
    const cloudsMaterial = new THREE.MeshStandardMaterial({
      map: cloudsTexture,
      transparent: true,
      opacity: 0.65,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const cloudsMesh = new THREE.Mesh(cloudsGeometry, cloudsMaterial);
    earthGroup.add(cloudsMesh);

    // 6. Outer Atmosphere Rayleigh Glow
    const atmosphereGeometry = new THREE.SphereGeometry(earthRadius + 0.16, 64, 64);
    const atmosphereShader = new THREE.ShaderMaterial({
      side: THREE.BackSide,
      blending: THREE.AdditiveBlending,
      transparent: true,
      vertexShader: `
        varying vec3 vNormal;
        void main() {
          vNormal = normalize(normalMatrix * normal);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        varying vec3 vNormal;
        void main() {
          float intensity = pow(0.68 - dot(vNormal, vec3(0.0, 0.0, 1.0)), 2.8);
          // Electric cyan to deep azure gradient
          vec3 glowColor = mix(vec3(0.0, 0.95, 1.0), vec3(0.15, 0.45, 1.0), intensity * 0.6);
          gl_FragColor = vec4(glowColor, intensity * 0.88);
        }
      `,
    });
    const atmosphereMesh = new THREE.Mesh(atmosphereGeometry, atmosphereShader);
    earthGroup.add(atmosphereMesh);

    // 7. Active Target Hotspot Pin
    const targetPinGroup = new THREE.Group();
    targetPinRef.current = targetPinGroup;
    const pinLat = initialTargetRef.current?.lat ?? 23.81;
    const pinLon = initialTargetRef.current?.lon ?? 90.41;
    const pinPos = latLonToVector3(pinLat, pinLon, earthRadius + 0.015);
    targetPinGroup.position.copy(pinPos);

    // Pin core dot
    const pinDotGeo = new THREE.SphereGeometry(0.035, 16, 16);
    const pinDotMat = new THREE.MeshBasicMaterial({ color: 0xff4d26 });
    const pinDot = new THREE.Mesh(pinDotGeo, pinDotMat);
    targetPinGroup.add(pinDot);

    // Pulsing target beacon ring
    const ringGeo = new THREE.RingGeometry(0.045, 0.075, 32);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0xff3b14,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.85,
    });
    const pinRing = new THREE.Mesh(ringGeo, ringMat);
    pinRing.lookAt(pinPos.clone().multiplyScalar(2));
    targetPinGroup.add(pinRing);

    earthMesh.add(targetPinGroup);

    // Five independent decorative orbits; Earth depth-testing naturally hides far-side models.
    const satelliteTemplate = createSatelliteModel();
    satelliteTemplate.scale.setScalar(0.23);
    const trailSamples = 28;
    const fleet = HERO_ORBITS.map((orbit) => {
      const model = satelliteTemplate.clone(true); // Share geometry/materials across the five models.
      model.name = `${orbit.name} ? ${orbit.sensor}`;
      scene.add(model);
      const marker = new THREE.Mesh(
        new THREE.SphereGeometry(0.028, 8, 8),
        new THREE.MeshBasicMaterial({ color: orbit.color }),
      );
      const label = createSatelliteLabel(orbit.name, orbit.sensor);
      scene.add(marker, label);
      const pathPoints = Array.from({ length: 129 }, (_, i) => orbitPosition(orbit, i / 128 * Math.PI * 2));
      const path = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pathPoints),
        new THREE.LineBasicMaterial({ color: orbit.color, transparent: true, opacity: 0.16, depthWrite: false }));
      scene.add(path);
      const trailGeometry = new THREE.BufferGeometry();
      const trailPositions = new Float32Array(trailSamples * 3);
      const trailColors = new Float32Array(trailSamples * 3);
      const color = new THREE.Color(orbit.color);
      for (let i = 0; i < trailSamples; i++) color.clone().multiplyScalar(0.15 + 0.85 * i / (trailSamples - 1)).toArray(trailColors, i * 3);
      const positions = new THREE.BufferAttribute(trailPositions, 3).setUsage(THREE.DynamicDrawUsage);
      trailGeometry.setAttribute("position", positions);
      trailGeometry.setAttribute("color", new THREE.BufferAttribute(trailColors, 3));
      const trail = new THREE.Line(trailGeometry,
        new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.5, depthWrite: false }));
      scene.add(trail);
      return { orbit, model, marker, label, trail, positions };
    });
    const orbitPoint = new THREE.Vector3();

    // 10. Starfield Background
    const starCount = 1400;
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
    let earthRotVelocityY = 0.0018;

    const handlePointerDown = (e: MouseEvent | TouchEvent) => {
      isDragging = true;
      const clientX = "touches" in e ? e.touches[0].clientX : e.clientX;
      const clientY = "touches" in e ? e.touches[0].clientY : e.clientY;
      prevPointerX = clientX;
      prevPointerY = clientY;
    };

    const handlePointerMove = (e: MouseEvent | TouchEvent) => {
      const clientX = "touches" in e ? e.touches[0].clientX : e.clientX;
      const clientY = "touches" in e ? e.touches[0].clientY : e.clientY;

      if (isDragging) {
        const deltaX = clientX - prevPointerX;
        const deltaY = clientY - prevPointerY;
        earthGroup.rotation.y += deltaX * 0.006;
        earthGroup.rotation.x += deltaY * 0.004;
        needsRender = true;
        earthRotVelocityX = deltaY * 0.0008;
        earthRotVelocityY = deltaX * 0.0012;
        prevPointerX = clientX;
        prevPointerY = clientY;
      }
    };

    const handlePointerUp = () => {
      isDragging = false;
    };

    const dom = renderer.domElement;
    dom.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("mousemove", handlePointerMove);
    window.addEventListener("mouseup", handlePointerUp);
    dom.addEventListener("touchstart", handlePointerDown, { passive: true });
    window.addEventListener("touchmove", handlePointerMove, { passive: true });
    window.addEventListener("touchend", handlePointerUp);

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
      const globeDiameter = Math.min(newWidth * 0.68, newHeight * 0.66, 420) * 1.27;
      camera.position.z = Math.sqrt(earthRadius ** 2 + (earthRadius * newHeight / (globeDiameter * Math.tan(halfFov))) ** 2);
      // Fit every orbit, including miniature wings/labels, without crossing the canvas edge.
      for (const orbit of HERO_ORBITS) {
        for (let i = 0; i < 96; i++) {
          orbitPosition(orbit, i / 96 * Math.PI * 2, orbitPoint);
          camera.position.z = Math.max(camera.position.z,
            orbitPoint.z + (Math.abs(orbitPoint.x) + 0.30) / (Math.tan(halfFov) * camera.aspect * 0.97),
            orbitPoint.z + (Math.abs(orbitPoint.y) + 0.30) / (Math.tan(halfFov) * 0.97));
        }
      }
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
    let revealed = false;
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
        earthRotVelocityY = THREE.MathUtils.lerp(earthRotVelocityY, 0.0018, 1 - Math.pow(0.97, frameScale));
        earthRotVelocityX = THREE.MathUtils.lerp(earthRotVelocityX, 0, 1 - Math.pow(0.95, frameScale));
      }
      cloudsMesh.rotation.y += 0.0006 * frameScale;
      cloudsMesh.rotation.x += 0.0002 * frameScale;
      for (const { orbit, model, marker, label, positions } of fleet) {
        const angle = orbit.phase + time * orbit.speed;
        orbitPosition(orbit, angle, model.position);
        model.lookAt(earthGroup.position);
        marker.position.copy(model.position).multiplyScalar(1.045);
        label.position.copy(model.position);
        label.position.y += 0.18;
        for (let i = 0; i < trailSamples; i++) {
          orbitPosition(orbit, angle - 0.5 * (1 - i / (trailSamples - 1)), orbitPoint);
          positions.setXYZ(i, orbitPoint.x, orbitPoint.y, orbitPoint.z);
        }
        positions.needsUpdate = true;
      }

      // Target pin pulsing ring
      const ringScale = 1.0 + (Math.sin(time * 4) * 0.5 + 0.5) * 1.2;
      pinRing.scale.set(ringScale, ringScale, ringScale);
      if (ringMat) {
        ringMat.opacity = Math.max(0.1, 1.0 - (ringScale - 1.0) / 1.2);
      }

      // Keep the globe centered; pointer interaction rotates the Earth, not the camera.
      camera.lookAt(earthGroup.position);

      // Subtle starfield twinkling
      starField.rotation.y = time * 0.005;

      renderer.render(scene, camera);
      needsRender = false;
      // Keep the lightweight globe visible until the textured frame is painted.
      if (!revealed && dayTexture.image && nightTexture.image && specularTexture.image) {
        revealed = true;
        setIsReady(true);
      }
    };

    animate(performance.now());

    // 14. Cleanup
    return () => {
      isDisposed = true;
      cancelAnimationFrame(animationId);
      resizeObserver.disconnect();
      visibilityObserver.disconnect();
      motionPreference.removeEventListener("change", handleMotionChange);
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("mousemove", handlePointerMove);
      window.removeEventListener("mouseup", handlePointerUp);
      window.removeEventListener("touchmove", handlePointerMove);
      window.removeEventListener("touchend", handlePointerUp);
      dom.removeEventListener("mousedown", handlePointerDown);
      dom.removeEventListener("touchstart", handlePointerDown);

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
      targetPinRef.current = null;
    };
  }, []);

  return (
    <div className="outcrowd-3d-wrapper" style={{ position: "relative", width: "100%", height: "100%" }}>
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
        }}
        aria-label="Interactive Earth with illustrative orbits of Terra, Aqua, Suomi-NPP, NOAA-20, and NOAA-21; positions are not live telemetry"
      />

      <small className="hero-orbit-caption">Illustrative orbits ? not live positions</small>

      {/* Futuristic Orbit HUD Overlays */}
      <div className="outcrowd-hud-overlay" style={{ pointerEvents: "none", position: "absolute", inset: 0, zIndex: 2 }}>
        {/* Subtle Orbit Reticles */}
        <div className="hud-reticle hud-reticle-tl" />
        <div className="hud-reticle hud-reticle-br" />
      </div>
    </div>
  );
}
