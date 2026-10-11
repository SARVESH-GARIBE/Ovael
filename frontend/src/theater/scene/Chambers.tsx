import React, { useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';

interface ChambersProps {
  reducedMotion?: boolean;
}

export const Chambers: React.FC<ChambersProps> = ({ reducedMotion }) => {
  const attackerRimRef = useRef<THREE.Mesh>(null);
  const victimRimRef = useRef<THREE.Mesh>(null);

  useFrame(({ clock }) => {
    if (reducedMotion) return;
    const t = clock.getElapsedTime();
    if (attackerRimRef.current) {
      const mat = attackerRimRef.current.material as THREE.MeshBasicMaterial;
      mat.opacity = 0.6 + Math.sin(t * 1.5) * 0.2;
    }
    if (victimRimRef.current) {
      const mat = victimRimRef.current.material as THREE.MeshBasicMaterial;
      mat.opacity = 0.6 + Math.cos(t * 1.5) * 0.2;
    }
  });

  return (
    <group>
      {/* ATTACKER CHAMBER (Left: x = -5) */}
      <group position={[-5, 0, 0]}>
        {/* Base Platform */}
        <mesh position={[0, -0.1, 0]}>
          <cylinderGeometry args={[2.2, 2.4, 0.2, 32]} />
          <meshStandardMaterial color="#0b1021" roughness={0.3} metalness={0.8} />
        </mesh>
        {/* Outer Ring Glow */}
        <mesh position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[2.1, 2.2, 32]} />
          <meshBasicMaterial color="#ff0055" transparent opacity={0.7} />
        </mesh>
        {/* Glass Enclosure */}
        <mesh position={[0, 1.8, 0]}>
          <cylinderGeometry args={[2.0, 2.0, 3.6, 32, 1, true]} />
          <meshPhysicalMaterial
            color="#141b2f"
            transparent
            opacity={0.25}
            roughness={0.1}
            metalness={0.1}
            transmission={0.8}
            ior={1.4}
            side={THREE.DoubleSide}
          />
        </mesh>
        {/* Emissive Rim Light Top Ring */}
        <mesh ref={attackerRimRef} position={[0, 3.6, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[1.95, 2.05, 32]} />
          <meshBasicMaterial color="#ff0055" transparent opacity={0.8} />
        </mesh>
      </group>

      {/* VICTIM CHAMBER (Right: x = 5) */}
      <group position={[5, 0, 0]}>
        {/* Base Platform */}
        <mesh position={[0, -0.1, 0]}>
          <cylinderGeometry args={[2.2, 2.4, 0.2, 32]} />
          <meshStandardMaterial color="#0b1021" roughness={0.3} metalness={0.8} />
        </mesh>
        {/* Outer Ring Glow */}
        <mesh position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[2.1, 2.2, 32]} />
          <meshBasicMaterial color="#00f2fe" transparent opacity={0.7} />
        </mesh>
        {/* Glass Enclosure */}
        <mesh position={[0, 1.8, 0]}>
          <cylinderGeometry args={[2.0, 2.0, 3.6, 32, 1, true]} />
          <meshPhysicalMaterial
            color="#0f1423"
            transparent
            opacity={0.25}
            roughness={0.1}
            metalness={0.1}
            transmission={0.8}
            ior={1.4}
            side={THREE.DoubleSide}
          />
        </mesh>
        {/* Emissive Rim Light Top Ring */}
        <mesh ref={victimRimRef} position={[0, 3.6, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[1.95, 2.05, 32]} />
          <meshBasicMaterial color="#00f2fe" transparent opacity={0.8} />
        </mesh>
      </group>
    </group>
  );
};
