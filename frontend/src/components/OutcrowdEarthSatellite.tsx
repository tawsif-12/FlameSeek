import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";

interface OutcrowdEarthSatelliteProps {
  activeSatellite?: "terra" | "aqua" | "snpp" | "noaa20";
  onSatelliteSelect?: (sat: "terra" | "aqua" | "snpp" | "noaa20") => void;
  targetHotspot?: { lat: number; lon: number; frp?: number | null };
}

type SatelliteId = "terra" | "aqua" | "snpp" | "noaa20";

interface OrbitConfig {
  id: SatelliteId;
  radiusX: number;
  radiusY: number;
  tiltX: number;
  tiltZ: number;
  phase: number;
  speed: number;
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

// Glowing Orbital Ring Creator
function createOrbitRing(radiusX: number, radiusY: number, color: number, tiltX: number, tiltZ: number, dashed = false) {
  const points: THREE.Vector3[] = [];
  const segments = 128;
  for (let i = 0; i <= segments; i++) {
    const theta = (i / segments) * Math.PI * 2;
    const x = Math.cos(theta) * radiusX;
    const y = Math.sin(theta) * radiusY;
    points.push(new THREE.Vector3(x, y, 0));
  }

  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  let material: THREE.Material;

  if (dashed) {
    material = new THREE.LineDashedMaterial({
      color,
      dashSize: 0.12,
      gapSize: 0.06,
      transparent: true,
      opacity: 0.65,
    });
  } else {
    material = new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity: 0.75,
    });
  }

  const line = new THREE.Line(geometry, material);
  if (dashed && "computeLineDistances" in geometry) {
    (line as THREE.Line).computeLineDistances();
  }
  line.rotation.x = tiltX;
  line.rotation.z = tiltZ;
  return line;
}

function pointOnOrbit(config: OrbitConfig, angle: number, center: THREE.Vector3) {
  return new THREE.Vector3(
    Math.cos(angle) * config.radiusX,
    Math.sin(angle) * config.radiusY,
    0,
  )
    .applyEuler(new THREE.Euler(config.tiltX, 0, config.tiltZ, "XYZ"))
    .add(center);
}

export default function OutcrowdEarthSatellite({
  activeSatellite = "terra",
  targetHotspot,
}: OutcrowdEarthSatelliteProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const activeSatelliteRef = useRef(activeSatellite);
  const [isReady, setIsReady] = useState(false);
  const targetLat = targetHotspot?.lat;
  const targetLon = targetHotspot?.lon;

  useEffect(() => {
    activeSatelliteRef.current = activeSatellite;
  }, [activeSatellite]);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    let animationId: number;
    let isDisposed = false;

    // Dimensions
    const width = container.clientWidth || window.innerWidth;
    const height = container.clientHeight || 750;

    // 1. Scene, Camera, Renderer
    const scene = new THREE.Scene();

    const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 1000);
    camera.position.set(0, 0.45, 6.4);

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
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
    const earthRadius = 2.05;

    // Day texture
    const dayTexture = textureLoader.load("/textures/earth_day_2048.jpg", () => {
      if (!isDisposed) setIsReady(true);
    });
    dayTexture.colorSpace = THREE.SRGBColorSpace;

    // Normal & Specular textures
    const normalTexture = textureLoader.load("/textures/earth_normal_2048.jpg");
    const specularTexture = textureLoader.load("/textures/earth_specular_2048.jpg");
    const nightTexture = textureLoader.load("/textures/earth_night_2048.jpg");
    nightTexture.colorSpace = THREE.SRGBColorSpace;

    // 4. Earth Globe Group
    const earthGroup = new THREE.Group();
    earthGroup.position.set(0.65, 0, 0); // Offset slightly to right for hero copy balance
    scene.add(earthGroup);

    // Custom Shader Material for Earth: Blends Day, Night City Lights, and Normal/Specular
    const earthCustomShader = new THREE.ShaderMaterial({
      uniforms: {
        dayTexture: { value: dayTexture },
        nightTexture: { value: nightTexture },
        specularMap: { value: specularTexture },
        normalMap: { value: normalTexture },
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
    const cloudsTexture = textureLoader.load("/textures/earth_clouds_1024.png");
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
    const pinLat = targetLat ?? 23.81;
    const pinLon = targetLon ?? 90.41;
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

    // 8. Satellite fleet and their matching sun-synchronous orbital paths.
    const orbitConfigs: OrbitConfig[] = [
      { id: "terra", radiusX: 3.2, radiusY: 2.9, tiltX: 0.45, tiltZ: 0.82, phase: 0.15, speed: 0.62 },
      { id: "aqua", radiusX: 3.28, radiusY: 2.98, tiltX: 0.5, tiltZ: 0.88, phase: Math.PI + 0.15, speed: 0.62 },
      { id: "snpp", radiusX: 3.42, radiusY: 3.08, tiltX: -0.65, tiltZ: -0.38, phase: 1.35, speed: 0.52 },
      { id: "noaa20", radiusX: 3.52, radiusY: 3.16, tiltX: -0.7, tiltZ: -0.44, phase: Math.PI + 1.35, speed: 0.52 },
    ];

    const orbitLines = orbitConfigs.map((config) => {
      const color = config.id === activeSatelliteRef.current ? 0x00f2fe : 0x246f94;
      const line = createOrbitRing(config.radiusX, config.radiusY, color, config.tiltX, config.tiltZ, true);
      line.position.copy(earthGroup.position);
      scene.add(line);
      return line;
    });
    const activeOrbitColor = new THREE.Color(0x00f2fe);
    const idleOrbitColor = new THREE.Color(0x246f94);

    const satelliteTexture = textureLoader.load("/satellite-realistic-v2.png");
    satelliteTexture.colorSpace = THREE.SRGBColorSpace;
    const satelliteSprites = orbitConfigs.map((config) => {
      const material = new THREE.SpriteMaterial({
        map: satelliteTexture,
        color: 0xffffff,
        transparent: true,
        depthWrite: false,
        toneMapped: false,
        opacity: config.id === activeSatelliteRef.current ? 1 : 0.82,
      });
      const sprite = new THREE.Sprite(material);
      const baseScale = config.id === activeSatelliteRef.current ? 1.28 : 0.96;
      sprite.scale.set(baseScale, baseScale * 0.67, 1);
      sprite.position.copy(pointOnOrbit(config, config.phase, earthGroup.position));
      sprite.renderOrder = 4;
      scene.add(sprite);
      return { config, sprite, material };
    });

    // Orbit pulse indicator node
    const pulseGeo = new THREE.SphereGeometry(0.065, 16, 16);
    const pulseMat = new THREE.MeshBasicMaterial({ color: 0x00f2fe });
    const pulseNode = new THREE.Mesh(pulseGeo, pulseMat);
    scene.add(pulseNode);

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
    let mouseX = 0;
    let mouseY = 0;
    let targetCameraX = 0;
    let targetCameraY = 0.45;
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

      // Parallax target
      mouseX = (clientX / window.innerWidth) * 2 - 1;
      mouseY = -(clientY / window.innerHeight) * 2 + 1;
      targetCameraX = mouseX * 0.45;
      targetCameraY = 0.45 + mouseY * 0.3;

      if (isDragging) {
        const deltaX = clientX - prevPointerX;
        const deltaY = clientY - prevPointerY;
        earthGroup.rotation.y += deltaX * 0.006;
        earthGroup.rotation.x += deltaY * 0.004;
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

      // Responsive adjustments for mobile vs desktop
      if (newWidth < 768) {
        earthGroup.position.set(0, 0.4, 0);
        camera.position.z = 7.4;
      } else if (newWidth < 1200) {
        earthGroup.position.set(0.35, 0, 0);
        camera.position.z = 6.6;
      } else {
        earthGroup.position.set(0.75, 0, 0);
        camera.position.z = 6.2;
      }
      orbitLines.forEach((line) => line.position.copy(earthGroup.position));
    };

    window.addEventListener("resize", handleResize);
    handleResize();

    // 13. Animation Loop
    const clock = new THREE.Clock();

    const animate = () => {
      if (isDisposed) return;
      animationId = requestAnimationFrame(animate);

      const time = clock.getElapsedTime();

      // Earth rotation
      if (!isDragging) {
        earthGroup.rotation.y += earthRotVelocityY;
        earthGroup.rotation.x += earthRotVelocityX;
        earthRotVelocityY = THREE.MathUtils.lerp(earthRotVelocityY, 0.0018, 0.03);
        earthRotVelocityX = THREE.MathUtils.lerp(earthRotVelocityX, 0, 0.05);
      }

      // Clouds rotate slightly faster than Earth
      cloudsMesh.rotation.y += 0.0006;
      cloudsMesh.rotation.x += 0.0002;

      // Every spacecraft is evaluated from the same ellipse and tilt used by
      // its visible ring, so it cannot drift away from its orbital path.
      satelliteSprites.forEach(({ config, sprite, material }, index) => {
        const angle = config.phase + time * config.speed;
        sprite.position.copy(pointOnOrbit(config, angle, earthGroup.position));
        const isActive = config.id === activeSatelliteRef.current;
        const baseScale = isActive ? 1.28 : 0.96;
        const depth = sprite.position.z - earthGroup.position.z;
        const depthScale = THREE.MathUtils.clamp(1 + depth * 0.1, 0.78, 1.24);
        sprite.scale.set(baseScale * depthScale, baseScale * depthScale * 0.67, 1);
        material.opacity = THREE.MathUtils.lerp(material.opacity, isActive ? 1 : 0.82, 0.08);
        const orbitMaterial = orbitLines[index].material as THREE.LineDashedMaterial;
        orbitMaterial.color.lerp(isActive ? activeOrbitColor : idleOrbitColor, 0.08);
      });

      // Pulse node travels along main orbit
      pulseNode.position.copy(pointOnOrbit(orbitConfigs[0], orbitConfigs[0].phase + time * orbitConfigs[0].speed + 0.35, earthGroup.position));
      const pulseScale = 1.0 + Math.sin(time * 6.0) * 0.35;
      pulseNode.scale.set(pulseScale, pulseScale, pulseScale);

      // Target pin pulsing ring
      const ringScale = 1.0 + (Math.sin(time * 4) * 0.5 + 0.5) * 1.2;
      pinRing.scale.set(ringScale, ringScale, ringScale);
      if (ringMat) {
        ringMat.opacity = Math.max(0.1, 1.0 - (ringScale - 1.0) / 1.2);
      }

      // Smooth camera parallax
      camera.position.x = THREE.MathUtils.lerp(camera.position.x, targetCameraX, 0.05);
      camera.position.y = THREE.MathUtils.lerp(camera.position.y, targetCameraY, 0.05);
      camera.lookAt(earthGroup.position.x * 0.35, 0, 0);

      // Subtle starfield twinkling
      starField.rotation.y = time * 0.005;

      renderer.render(scene, camera);
    };

    animate();

    // 14. Cleanup
    return () => {
      isDisposed = true;
      cancelAnimationFrame(animationId);
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

      // Dispose Three.js resources
      renderer.dispose();
      earthGeometry.dispose();
      earthCustomShader.dispose();
      cloudsGeometry.dispose();
      cloudsMaterial.dispose();
      atmosphereGeometry.dispose();
      atmosphereShader.dispose();
      orbitLines.forEach((line) => {
        line.geometry.dispose();
        (line.material as THREE.Material).dispose();
      });
      satelliteSprites.forEach(({ material }) => material.dispose());
      satelliteTexture.dispose();
      starGeo.dispose();
      starMat.dispose();
    };
  }, [targetLat, targetLon]);

  return (
    <div className="outcrowd-3d-wrapper" style={{ position: "relative", width: "100%", height: "100%", minHeight: "720px" }}>
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
        }}
        aria-label="Interactive 3D Earth and Satellite visualization"
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
