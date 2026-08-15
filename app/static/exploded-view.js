import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const showcase = document.querySelector("#technology-showcase");
const canvas = document.querySelector("#exploded-canvas");
const status = document.querySelector("#exploded-status");
const fallback = document.querySelector("#exploded-fallback");
const progressBar = document.querySelector("#technology-progress-bar");
const stageLabel = document.querySelector("#technology-stage-label");
const stageDots = Array.from(document.querySelectorAll("[data-stage-dot]"));
const technologyCopy = document.querySelector(".technology-copy");

if (!showcase || !canvas) {
  throw new Error("The technology showcase canvas is not available.");
}

const modelUrl = "/static/models/Glasses%203D%20model.glb";
const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
let reducedMotion = reducedMotionQuery.matches;
let renderer;
let camera;
let scene;
let modelGroup;
let model;
let frameRequest;
let scrollRequest;
let scrollTriggerInstance;
let isReady = false;
let currentProgress = 0;
let baseCameraPosition = new THREE.Vector3(0, 0.15, 7.7);
let baseGroupPosition = new THREE.Vector3();
let baseGroupRotation = new THREE.Euler();
let cameraTarget = new THREE.Vector3();
let edgeLight;
let rimLight;
let roleMeshes = [];
let displayTexture;
let displayScreenResources = [];

const clock = new THREE.Clock();

const stageRanges = [
  { start: 0, end: 0.08, label: "Complete glasses" },
  { start: 0.08, end: 0.22, label: "Side view" },
  { start: 0.22, end: 0.62, label: "Printed shell" },
  { start: 0.62, end: 0.74, label: "ESP32 CAM" },
  { start: 0.74, end: 0.86, label: "TFT display" },
  { start: 0.86, end: 1, label: "Exploded system" },
];

// The six entries line up with the six mesh roles in the supplied GLB.
// Each one has its own time window, three axis offset and local rotation.
const roleTimeline = {
  frame: {
    start: 0.8,
    end: 0.86,
    offset: new THREE.Vector3(0, -0.02, 0.04),
    rotation: new THREE.Euler(-0.025, 0.035, 0.02),
  },
  bridgeUpper: {
    start: 0.22,
    end: 0.34,
    offset: new THREE.Vector3(-0.35, 0.06, 0.1),
    rotation: new THREE.Euler(-0.06, 0.14, 0.08),
  },
  bridgeCore: {
    start: 0.36,
    end: 0.48,
    offset: new THREE.Vector3(-0.24, 0.09, 0.14),
    rotation: new THREE.Euler(0.065, -0.1, -0.05),
  },
  bridgeLower: {
    start: 0.5,
    end: 0.62,
    offset: new THREE.Vector3(-0.12, 0.13, 0.18),
    rotation: new THREE.Euler(-0.08, 0.08, 0.1),
  },
  electronics: {
    start: 0.62,
    end: 0.74,
    offset: new THREE.Vector3(0, 0.18, 0.22),
    rotation: new THREE.Euler(0.1, 0.14, 0.16),
  },
  display: {
    start: 0.74,
    end: 0.86,
    rotationStart: 0.79,
    rotationEnd: 0.86,
    offset: new THREE.Vector3(0.14, 0.15, 0.28),
    rotation: new THREE.Euler(0, 0, 0),
  },
};

function smoothstep(value) {
  const amount = THREE.MathUtils.clamp(value, 0, 1);
  return amount * amount * (3 - 2 * amount);
}

function remap(value, start, end) {
  if (end <= start) {
    return value >= end ? 1 : 0;
  }
  return THREE.MathUtils.clamp((value - start) / (end - start), 0, 1);
}

function setStatus(message) {
  if (status) {
    status.textContent = message;
    status.hidden = false;
  }
  if (fallback) {
    fallback.hidden = true;
  }
}

function showFallback(message) {
  if (status) {
    status.hidden = true;
  }
  if (fallback) {
    fallback.textContent = message;
    fallback.hidden = false;
  }
}

function classifyMesh(mesh, index) {
  const meshName = mesh.name || "";
  const parentName = mesh.parent && mesh.parent.name ? mesh.parent.name : "";
  const name = `${meshName} ${parentName}`.toLowerCase();

  if (name.includes("tft") || name.includes("monitor") || name.includes("lcd")) {
    return "display";
  }
  if (name.includes("bridge")) {
    if (name.includes(".001")) {
      return "bridgeUpper";
    }
    if (name.includes(".002")) {
      return "bridgeLower";
    }
    return "bridgeCore";
  }
  if (name.includes("board") || name.includes("esp32") || name.includes("camera")) {
    return "electronics";
  }
  if (name.includes("head") || name.includes("frame")) {
    return "frame";
  }

  const fallbackRoles = ["frame", "electronics", "display", "bridgeCore", "bridgeUpper", "bridgeLower"];
  return fallbackRoles[index % fallbackRoles.length];
}

function configureMaterial(mesh, role) {
  const palette = {
    frame: { color: 0x484b55, metalness: 0.52, roughness: 0.3 },
    electronics: { color: 0x44564f, metalness: 0.46, roughness: 0.38 },
    display: { color: 0x343c49, metalness: 0.48, roughness: 0.28 },
    bridgeCore: { color: 0x3f4652, metalness: 0.76, roughness: 0.25 },
    bridgeUpper: { color: 0x727985, metalness: 0.82, roughness: 0.22 },
    bridgeLower: { color: 0x2f343d, metalness: 0.62, roughness: 0.32 },
  };
  const appearance = palette[role] || palette.frame;
  const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];

  mesh.material = materials.map((material) => {
    const nextMaterial = material && material.clone
      ? material.clone()
      : new THREE.MeshStandardMaterial();
    nextMaterial.color.setHex(appearance.color);
    nextMaterial.metalness = appearance.metalness;
    nextMaterial.roughness = appearance.roughness;
    nextMaterial.envMapIntensity = 1.2;
    if (role === "display" && nextMaterial.emissive) {
      nextMaterial.emissive.setHex(0x071522);
      nextMaterial.emissiveIntensity = 0.32;
    }
    return nextMaterial;
  });

  if (mesh.material.length === 1) {
    mesh.material = mesh.material[0];
  }
  mesh.castShadow = true;
  mesh.receiveShadow = true;
}

function createDisplayTexture() {
  if (displayTexture) {
    return displayTexture;
  }

  const screenCanvas = document.createElement("canvas");
  screenCanvas.width = 960;
  screenCanvas.height = 640;
  const context = screenCanvas.getContext("2d");
  if (!context) {
    return undefined;
  }

  const background = context.createLinearGradient(0, 0, 0, screenCanvas.height);
  background.addColorStop(0, "#071927");
  background.addColorStop(0.52, "#020a12");
  background.addColorStop(1, "#010307");
  context.fillStyle = background;
  context.fillRect(0, 0, screenCanvas.width, screenCanvas.height);

  context.strokeStyle = "rgba(94, 217, 239, 0.72)";
  context.lineWidth = 12;
  context.strokeRect(18, 18, screenCanvas.width - 36, screenCanvas.height - 36);

  context.save();
  context.globalAlpha = 0.12;
  context.fillStyle = "#8eeeff";
  for (let y = 36; y < screenCanvas.height - 24; y += 16) {
    context.fillRect(30, y, screenCanvas.width - 60, 2);
  }
  context.restore();

  context.textAlign = "center";
  context.textBaseline = "middle";
  context.font = "700 84px Arial, sans-serif";
  context.fillStyle = "#e7fdff";
  context.shadowColor = "rgba(91, 225, 255, 0.95)";
  context.shadowBlur = 24;
  context.fillText("HELLO WORLD", screenCanvas.width / 2, screenCanvas.height / 2);
  context.shadowBlur = 0;

  displayTexture = new THREE.CanvasTexture(screenCanvas);
  displayTexture.colorSpace = THREE.SRGBColorSpace;
  displayTexture.flipY = true;
  displayTexture.needsUpdate = true;
  return displayTexture;
}

function applyDisplayTexture(material, texture) {
  if (!material || !texture) {
    return;
  }

  material.map = texture;
  if ("emissiveMap" in material && material.emissive) {
    material.emissiveMap = texture;
    material.emissive.setHex(0xffffff);
    material.emissiveIntensity = 1.8;
  }
  material.roughness = 0.2;
  material.metalness = 0.12;
  material.needsUpdate = true;
}

function addDisplayScreenPlane(mesh, texture) {
  if (!mesh.geometry || !texture) {
    return;
  }

  mesh.geometry.computeBoundingBox();
  const bounds = mesh.geometry.boundingBox;
  if (!bounds) {
    return;
  }

  const size = bounds.getSize(new THREE.Vector3());
  const center = bounds.getCenter(new THREE.Vector3());
  const width = Math.max(0.1, size.z * 0.82);
  const height = Math.max(0.1, size.y * 0.76);
  const surfaceOffset = Math.max(0.008, size.x * 0.04);
  const planeMaterial = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    map: texture,
    emissive: 0xffffff,
    emissiveMap: texture,
    emissiveIntensity: 1.8,
    metalness: 0.12,
    roughness: 0.2,
    side: THREE.DoubleSide,
    toneMapped: false,
  });
  const plane = new THREE.Mesh(new THREE.PlaneGeometry(width, height), planeMaterial);
  plane.name = "TFTScreenHelloWorld";
  plane.position.set(bounds.max.x + surfaceOffset, center.y, center.z);
  plane.rotation.y = Math.PI / 2;
  plane.scale.x = -1;
  plane.renderOrder = 3;
  plane.castShadow = false;
  plane.receiveShadow = false;
  mesh.add(plane);
  displayScreenResources.push({ geometry: plane.geometry, material: planeMaterial });
}

function setDisplayScreen(mesh) {
  const texture = createDisplayTexture();
  if (!texture) {
    return;
  }

  const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
  const uv = mesh.geometry && mesh.geometry.attributes ? mesh.geometry.attributes.uv : undefined;
  if (uv && uv.count > 0) {
    materials.forEach((material) => applyDisplayTexture(material, texture));
    return;
  }

  addDisplayScreenPlane(mesh, texture);
}

function createDisplayFacingQuaternion(displayObject) {
  if (!displayObject || !displayObject.parent || !modelGroup) {
    return displayObject ? displayObject.quaternion.clone() : new THREE.Quaternion();
  }

  const savedGroupPosition = modelGroup.position.clone();
  const savedGroupRotation = modelGroup.rotation.clone();
  const finalExplodedGroupPosition = baseGroupPosition.clone();
  finalExplodedGroupPosition.x -= 0.22;
  modelGroup.position.copy(finalExplodedGroupPosition);
  modelGroup.rotation.set(
    baseGroupRotation.x - 0.06,
    baseGroupRotation.y + 0.46,
    baseGroupRotation.z + 0.055,
    baseGroupRotation.order,
  );
  modelGroup.updateMatrixWorld(true);
  displayObject.updateMatrixWorld(true);

  const displayWorldPosition = displayObject.getWorldPosition(new THREE.Vector3());
  const finalCameraPosition = new THREE.Vector3(
    baseCameraPosition.x + 0.03,
    baseCameraPosition.y,
    baseCameraPosition.z - 0.1,
  );
  const normalAxis = finalCameraPosition.sub(displayWorldPosition).normalize();
  const worldUp = new THREE.Vector3(0, 1, 0);
  const zAxis = new THREE.Vector3().crossVectors(normalAxis, worldUp).normalize();
  if (zAxis.lengthSq() < 0.001) {
    zAxis.set(0, 0, -1);
  }
  const yAxis = new THREE.Vector3().crossVectors(zAxis, normalAxis).normalize();
  const targetWorldMatrix = new THREE.Matrix4().makeBasis(normalAxis, yAxis, zAxis);
  const targetWorldQuaternion = new THREE.Quaternion().setFromRotationMatrix(targetWorldMatrix);
  const parentWorldQuaternion = displayObject.parent.getWorldQuaternion(new THREE.Quaternion());
  const targetQuaternion = parentWorldQuaternion.invert().multiply(targetWorldQuaternion);

  modelGroup.position.copy(savedGroupPosition);
  modelGroup.rotation.copy(savedGroupRotation);
  modelGroup.updateMatrixWorld(true);
  return targetQuaternion;
}

function addLighting() {
  scene.add(new THREE.HemisphereLight(0xdce6ff, 0x08090d, 1.35));

  const keyLight = new THREE.DirectionalLight(0xffffff, 3.4);
  keyLight.position.set(-3.8, 4.4, 5.5);
  keyLight.castShadow = true;
  scene.add(keyLight);

  rimLight = new THREE.DirectionalLight(0x758dff, 3.1);
  rimLight.position.set(4.5, 1.5, -4.5);
  scene.add(rimLight);

  edgeLight = new THREE.PointLight(0x54dfce, 1.5, 8, 2);
  edgeLight.position.set(-3.5, -0.6, -2.8);
  scene.add(edgeLight);
}

function resize() {
  if (!renderer || !camera) {
    return;
  }

  const bounds = canvas.getBoundingClientRect();
  const width = Math.max(1, Math.round(bounds.width));
  const height = Math.max(1, Math.round(bounds.height));
  const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);

  renderer.setPixelRatio(pixelRatio);
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();

  if (scrollTriggerInstance && window.ScrollTrigger) {
    window.ScrollTrigger.refresh();
  }
}

function getScrollProgress() {
  const bounds = showcase.getBoundingClientRect();
  const scrollRange = Math.max(1, showcase.offsetHeight - window.innerHeight);
  return THREE.MathUtils.clamp(-bounds.top / scrollRange, 0, 1);
}

function updateStageIndicator(progress) {
  const stageIndex = stageRanges.findIndex((range, index) => (
    progress < range.end || index === stageRanges.length - 1
  ));
  const currentStage = stageRanges[Math.max(0, stageIndex)];

  if (stageLabel && currentStage) {
    stageLabel.textContent = currentStage.label;
  }
  stageDots.forEach((dot, index) => {
    dot.classList.toggle("is-active", index === stageIndex);
    dot.classList.toggle("is-complete", index < stageIndex);
    dot.setAttribute("aria-current", index === stageIndex ? "step" : "false");
  });
}

function applyRoleProgress(progress) {
  roleMeshes.forEach(({ object, basePosition, baseQuaternion, targetPosition, targetQuaternion, timeline }) => {
    const positionProgress = remap(progress, timeline.start, timeline.end);
    const rotationProgress = remap(
      progress,
      timeline.rotationStart === undefined ? timeline.start : timeline.rotationStart,
      timeline.rotationEnd === undefined ? timeline.end : timeline.rotationEnd,
    );
    const positionEased = smoothstep(positionProgress);
    const rotationEased = smoothstep(rotationProgress);
    object.position.copy(basePosition).lerp(targetPosition, positionEased);
    object.quaternion.copy(baseQuaternion).slerp(targetQuaternion, rotationEased);
  });
}

function applyScrollProgress(progress = getScrollProgress()) {
  currentProgress = THREE.MathUtils.clamp(progress, 0, 1);
  updateStageIndicator(currentProgress);

  const copyProgress = reducedMotion ? 0 : smoothstep(remap(currentProgress, 0.22, 0.42));
  if (technologyCopy) {
    technologyCopy.style.opacity = `${1 - copyProgress}`;
    technologyCopy.style.transform = `translate3d(-50%, ${copyProgress * -72}px, 0)`;
    technologyCopy.style.visibility = copyProgress > 0.995 ? "hidden" : "visible";
  }

  if (progressBar) {
    progressBar.style.transform = `scaleX(${currentProgress})`;
  }

  if (!isReady || !model) {
    return;
  }

  const motionProgress = reducedMotion ? 0 : currentProgress;
  const sideProgress = smoothstep(remap(motionProgress, 0.08, 0.24));
  const explodedProgress = smoothstep(remap(motionProgress, 0.24, 1));
  const sideAngle = THREE.MathUtils.lerp(baseGroupRotation.y, baseGroupRotation.y + 0.46, sideProgress);
  modelGroup.rotation.y = sideAngle;
  modelGroup.rotation.x = baseGroupRotation.x - sideProgress * 0.06;
  modelGroup.rotation.z = baseGroupRotation.z + sideProgress * 0.035 + explodedProgress * 0.02;
  modelGroup.position.x = baseGroupPosition.x - explodedProgress * 0.22;

  camera.position.x = baseCameraPosition.x + sideProgress * 0.03;
  camera.position.y = baseCameraPosition.y;
  camera.position.z = baseCameraPosition.z - sideProgress * 0.28 + explodedProgress * 0.18;
  camera.lookAt(cameraTarget);

  applyRoleProgress(motionProgress);
}

function requestScrollUpdate() {
  if (scrollRequest === undefined) {
    scrollRequest = window.requestAnimationFrame(() => {
      scrollRequest = undefined;
      applyScrollProgress();
    });
  }
}

function setupScrollDriver() {
  const gsap = window.gsap;
  const ScrollTrigger = window.ScrollTrigger;

  // Keep a native scroll driver active even when ScrollTrigger is available.
  // This makes the demo work when the plugin initializes but does not emit
  // updates (for example in some local/static-server browser configurations).
  window.addEventListener("scroll", requestScrollUpdate, { passive: true });

  if (gsap && ScrollTrigger && typeof ScrollTrigger.create === "function") {
    try {
      gsap.registerPlugin(ScrollTrigger);
      scrollTriggerInstance = ScrollTrigger.create({
        trigger: showcase,
        start: "top top",
        end: "bottom bottom",
        invalidateOnRefresh: true,
        onUpdate: requestScrollUpdate,
        onRefresh: requestScrollUpdate,
      });
    } catch (error) {
      scrollTriggerInstance = undefined;
    }
  }

  requestScrollUpdate();
}

function render() {
  frameRequest = window.requestAnimationFrame(render);
  if (!renderer || !scene || !camera) {
    return;
  }

  const elapsed = clock.getElapsedTime();
  const sideWeight = reducedMotion ? 0 : smoothstep(remap(currentProgress, 0.08, 0.22));
  const settleWeight = reducedMotion ? 1 : smoothstep(remap(currentProgress, 0.18, 0.42));
  const finalWeight = reducedMotion ? 0 : smoothstep(remap(currentProgress, 0.86, 1));

  if (modelGroup) {
    const hover = Math.sin(elapsed * 1.15) * 0.016 * finalWeight;
    modelGroup.position.y = baseGroupPosition.y - (1 - settleWeight) * 0.3 + hover;
  }
  if (edgeLight && rimLight) {
    const breath = Math.sin(elapsed * 1.55) * 0.13 * sideWeight;
    edgeLight.intensity = 1.5 + breath;
    rimLight.intensity = 3.1 + breath * 0.45;
  }

  renderer.render(scene, camera);
}

async function loadModel() {
  setStatus("Loading 3D model");

  const loader = new GLTFLoader();
  const gltf = await loader.loadAsync(modelUrl, (event) => {
    if (event.total) {
      const percent = Math.round((event.loaded / event.total) * 100);
      setStatus(`Loading 3D model ${percent}%`);
    }
  });

  model = gltf.scene;
  modelGroup.add(model);

  // Centre the asset in model local space so the staged group placement is
  // preserved instead of being cancelled by the world-space bounding box.
  const stagedGroupPosition = modelGroup.position.clone();
  const stagedGroupQuaternion = modelGroup.quaternion.clone();
  modelGroup.position.set(0, 0, 0);
  modelGroup.quaternion.identity();
  modelGroup.updateMatrixWorld(true);

  const bounds = new THREE.Box3().setFromObject(model);
  const size = bounds.getSize(new THREE.Vector3());
  const maxDimension = Math.max(size.x, size.y, size.z, 0.001);
  const fitScale = 3.05 / maxDimension;

  model.scale.setScalar(fitScale);
  model.updateMatrixWorld(true);

  const fittedCenter = new THREE.Box3()
    .setFromObject(model)
    .getCenter(new THREE.Vector3());
  model.position.sub(fittedCenter);
  model.updateMatrixWorld(true);

  modelGroup.position.copy(stagedGroupPosition);
  modelGroup.quaternion.copy(stagedGroupQuaternion);
  modelGroup.updateMatrixWorld(true);

  roleMeshes = [];
  let meshIndex = 0;
  model.traverse((object) => {
    if (!object.isMesh) {
      return;
    }

    const role = classifyMesh(object, meshIndex);
    const timeline = roleTimeline[role] || roleTimeline.frame;
    const basePosition = object.position.clone();
    const baseQuaternion = object.quaternion.clone();
    const localRotation = new THREE.Quaternion().setFromEuler(timeline.rotation);
    const targetPosition = basePosition
      .clone()
      .addScaledVector(timeline.offset, maxDimension);
    const targetQuaternion = role === "display"
      ? createDisplayFacingQuaternion(object)
      : baseQuaternion.clone().multiply(localRotation);

    object.userData.explodeRole = role;
    object.userData.explodeBasePosition = basePosition.clone();
    object.userData.explodeBaseQuaternion = baseQuaternion.clone();
    object.userData.explodeTargetPosition = targetPosition.clone();
    object.userData.explodeTargetQuaternion = targetQuaternion.clone();
    object.userData.explodeTimeline = timeline;
    configureMaterial(object, role);
    if (role === "display") {
      setDisplayScreen(object);
    }

    roleMeshes.push({
      object,
      role,
      timeline,
      basePosition,
      baseQuaternion,
      targetPosition,
      targetQuaternion,
    });
    meshIndex += 1;
  });

  isReady = true;
  if (status) {
    status.hidden = true;
  }
  applyScrollProgress(currentProgress);
}

function initialize() {
  try {
    renderer = new THREE.WebGLRenderer({
      canvas,
      alpha: true,
      antialias: true,
      powerPreference: "high-performance",
    });
  } catch (error) {
    showFallback("Your browser could not start the 3D viewer. You can continue to use the ARGUS voice controls below.");
    return;
  }

  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.18;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(27, 1, 0.01, 100);
  camera.position.copy(baseCameraPosition);
  cameraTarget.set(0, 0, 0);
  camera.lookAt(cameraTarget);

  modelGroup = new THREE.Group();
  modelGroup.position.y = -0.75;
  modelGroup.rotation.x = -0.08;
  modelGroup.rotation.y = 0.12;
  baseGroupPosition.copy(modelGroup.position);
  baseGroupRotation.copy(modelGroup.rotation);
  scene.add(modelGroup);
  addLighting();
  resize();

  window.addEventListener("resize", resize, { passive: true });
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(resize).observe(canvas);
  }

  const updateReducedMotion = (event) => {
    reducedMotion = event.matches;
    applyScrollProgress(currentProgress);
  };
  if (typeof reducedMotionQuery.addEventListener === "function") {
    reducedMotionQuery.addEventListener("change", updateReducedMotion);
  } else if (typeof reducedMotionQuery.addListener === "function") {
    reducedMotionQuery.addListener(updateReducedMotion);
  }

  setupScrollDriver();
  render();
  loadModel().catch(() => {
    showFallback("The 3D model could not be loaded. You can continue to use the ARGUS voice controls below.");
  });
}

initialize();

window.addEventListener("pagehide", () => {
  if (frameRequest) {
    window.cancelAnimationFrame(frameRequest);
  }
  if (scrollRequest) {
    window.cancelAnimationFrame(scrollRequest);
  }
  if (scrollTriggerInstance) {
    scrollTriggerInstance.kill();
  }
  if (renderer) {
    renderer.dispose();
  }
  displayScreenResources.forEach(({ geometry, material }) => {
    geometry.dispose();
    material.dispose();
  });
  displayScreenResources = [];
  if (displayTexture) {
    displayTexture.dispose();
    displayTexture = undefined;
  }
});
