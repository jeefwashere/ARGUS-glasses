import { Canvas, useFrame, useLoader } from "@react-three/fiber";
import { Environment, Float, Html } from "@react-three/drei";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Group } from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { MotionValue, motionValue, useReducedMotion, useSpring, useTransform } from "framer-motion";

type SceneConfig = {
  initialScale?: number;
  finalScale?: number;
  xMovement?: number;
  yMovement?: number;
  rotation?: number;
  cameraPosition?: [number, number, number];
};

type ArgusProductSceneProps = {
  progress?: MotionValue<number>;
  className?: string;
  config?: SceneConfig;
};

const MODEL_PATH = "/models/argus.glb";

function Model() {
  const gltf = useLoader(GLTFLoader, MODEL_PATH);
  return <primitive object={gltf.scene} />;
}

function PlaceholderHardware() {
  const group = useRef<Group>(null);

  useFrame(({ clock }) => {
    if (!group.current) return;
    group.current.rotation.y = Math.sin(clock.elapsedTime * 0.35) * 0.08;
    group.current.rotation.x = Math.sin(clock.elapsedTime * 0.2) * 0.025;
  });

  const dark = "#171715";
  const metal = "#bec3bd";
  const lens = "#dce7df";

  return (
    <Float speed={1.2} rotationIntensity={0.08} floatIntensity={0.22}>
      <group ref={group}>
        <mesh position={[-1.25, 0, 0]}>
          <torusGeometry args={[0.58, 0.035, 16, 84]} />
          <meshStandardMaterial color={dark} roughness={0.42} metalness={0.4} />
        </mesh>
        <mesh position={[1.25, 0, 0]}>
          <torusGeometry args={[0.58, 0.035, 16, 84]} />
          <meshStandardMaterial color={dark} roughness={0.42} metalness={0.4} />
        </mesh>
        <mesh position={[-1.25, 0, 0.01]}>
          <circleGeometry args={[0.51, 64]} />
          <meshPhysicalMaterial color={lens} transparent opacity={0.32} roughness={0.08} transmission={0.35} />
        </mesh>
        <mesh position={[1.25, 0, 0.01]}>
          <circleGeometry args={[0.51, 64]} />
          <meshPhysicalMaterial color={lens} transparent opacity={0.32} roughness={0.08} transmission={0.35} />
        </mesh>
        <mesh position={[0, 0.04, 0]}>
          <boxGeometry args={[1.28, 0.075, 0.075]} />
          <meshStandardMaterial color={dark} roughness={0.46} metalness={0.38} />
        </mesh>
        <mesh position={[2.08, 0.1, -0.05]} rotation={[0, 0.08, -0.12]}>
          <boxGeometry args={[0.72, 0.32, 0.42]} />
          <meshStandardMaterial color={metal} roughness={0.35} metalness={0.58} />
        </mesh>
        <mesh position={[2.09, 0.1, 0.18]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.105, 0.105, 0.045, 36]} />
          <meshStandardMaterial color={dark} roughness={0.3} metalness={0.7} />
        </mesh>
        <mesh position={[2.52, 0.11, -0.05]} rotation={[0, 0.1, -0.12]}>
          <boxGeometry args={[0.22, 0.22, 0.46]} />
          <meshStandardMaterial color={dark} roughness={0.42} metalness={0.5} />
        </mesh>
        <mesh position={[-1.95, 0.03, -0.42]} rotation={[0.04, 0.72, -0.03]}>
          <boxGeometry args={[1.65, 0.07, 0.08]} />
          <meshStandardMaterial color={dark} roughness={0.46} metalness={0.38} />
        </mesh>
        <mesh position={[2.6, 0.1, -0.48]} rotation={[0.02, -0.88, -0.03]}>
          <boxGeometry args={[1.55, 0.07, 0.08]} />
          <meshStandardMaterial color={dark} roughness={0.46} metalness={0.38} />
        </mesh>
      </group>
    </Float>
  );
}

function ProductRig({ progress, config = {} }: { progress?: MotionValue<number>; config?: SceneConfig }) {
  const [missing, setMissing] = useState(false);
  const group = useRef<Group>(null);
  const reducedMotion = useReducedMotion();
  const baseProgress = useMemo(() => progress ?? motionValue(0), [progress]);
  const smoothProgress = useSpring(baseProgress, { stiffness: 75, damping: 28, mass: 0.6 });
  const scale = useTransform(smoothProgress, [0, 1], [config.initialScale ?? 1.25, config.finalScale ?? 0.78]);
  const x = useTransform(smoothProgress, [0, 1], [0, config.xMovement ?? 1.3]);
  const y = useTransform(smoothProgress, [0, 1], [0, config.yMovement ?? -0.1]);
  const rotation = useTransform(smoothProgress, [0, 1], [0, config.rotation ?? 0.65]);
  const lights = useMemo(() => ({ key: "studio" }), []);

  useEffect(() => {
    let active = true;
    fetch(MODEL_PATH, { method: "HEAD" })
      .then((response) => {
        if (active) setMissing(!response.ok);
      })
      .catch(() => {
        if (active) setMissing(true);
      });
    return () => {
      active = false;
    };
  }, []);

  useFrame(({ clock }) => {
    if (!group.current) return;
    const idle = reducedMotion ? 0 : Math.sin(clock.elapsedTime * 0.28) * 0.035;
    group.current.scale.setScalar(scale.get());
    group.current.position.set(x.get(), y.get(), 0);
    group.current.rotation.set(0.04, rotation.get() + idle, -0.04);
  });

  return (
    <group ref={group} dispose={null}>
      <ambientLight intensity={1.15} />
      <directionalLight position={[3, 4, 5]} intensity={2.2} />
      <spotLight position={[-4, 3, 4]} angle={0.5} penumbra={0.8} intensity={1.6} />
      {missing ? (
        <PlaceholderHardware />
      ) : (
        <Suspense fallback={<PlaceholderHardware />}>
          <Model />
        </Suspense>
      )}
      <Environment preset="city" {...lights} />
      <Html position={[2.9, -0.85, 0]} className="pointer-events-none hidden md:block">
        <div className="w-56 border border-black/15 bg-argus-paper/80 p-3 font-mono text-[10px] uppercase text-argus-muted backdrop-blur">
          Product render / optical module
          <br />
          Camera · display · audio · intelligence
        </div>
      </Html>
    </group>
  );
}

export function ArgusProductScene({ progress, className, config }: ArgusProductSceneProps) {
  return (
    <div className={className}>
      <Canvas
        dpr={[1, 1.65]}
        camera={{ position: config?.cameraPosition ?? [0, 0.35, 5.4], fov: 35 }}
        gl={{ alpha: true, antialias: true, powerPreference: "high-performance" }}
      >
        <ProductRig progress={progress} config={config} />
      </Canvas>
    </div>
  );
}
