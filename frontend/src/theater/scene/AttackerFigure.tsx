import React, { useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';

interface AttackerFigureProps {
  isAttacking: boolean;
  intensity: number;
  reducedMotion?: boolean;
}

export const AttackerFigure: React.FC<AttackerFigureProps> = ({
  isAttacking,
  intensity,
  reducedMotion,
}) => {
  const figureGroupRef = useRef<THREE.Group>(null);
  const leftHandRef = useRef<THREE.Mesh>(null);
  const rightHandRef = useRef<THREE.Mesh>(null);
  const terminalScreenRef = useRef<THREE.Mesh>(null);
  const terminalFlashRef = useRef<THREE.PointLight>(null);
  const glyphsGroupRef = useRef<THREE.Group>(null);

  useFrame(({ clock }) => {
    if (reducedMotion) return;
    const t = clock.getElapsedTime();

    // Subtle breathing motion
    if (figureGroupRef.current) {
      figureGroupRef.current.position.y = 0.05 * Math.sin(t * 1.8);
    }

    // Typing hands motion
    const typingSpeed = isAttacking ? 16 + intensity * 4 : 4;
    if (leftHandRef.current) {
      leftHandRef.current.position.y = 1.05 + 0.04 * Math.sin(t * typingSpeed);
    }
    if (rightHandRef.current) {
      rightHandRef.current.position.y = 1.05 + 0.04 * Math.cos(t * typingSpeed + 1);
    }

    // Terminal screen glow & flash
    if (terminalScreenRef.current && terminalFlashRef.current) {
      const mat = terminalScreenRef.current.material as THREE.MeshBasicMaterial;
      if (isAttacking) {
        const pulse = 0.7 + 0.3 * Math.sin(t * 20);
        mat.color.set('#ff0055');
        terminalFlashRef.current.intensity = 2.0 * intensity * pulse;
        terminalFlashRef.current.color.set('#ff0055');
      } else {
        mat.color.set('#00f2fe');
        terminalFlashRef.current.intensity = 0.4 + 0.2 * Math.sin(t * 2);
        terminalFlashRef.current.color.set('#00f2fe');
      }
    }

    // Floating glyphs rotation
    if (glyphsGroupRef.current) {
      glyphsGroupRef.current.rotation.y = t * 0.5;
    }
  });

  return (
    <group position={[-5, 0, 0]}>
      {/* Hooded Figure */}
      <group ref={figureGroupRef} position={[0, 0, -0.2]}>
        {/* Torso / Cloak (Cone Primitive) */}
        <mesh position={[0, 1.0, 0]}>
          <coneGeometry args={[0.55, 1.4, 6]} />
          <meshStandardMaterial color="#0a0e1c" roughness={0.7} metalness={0.2} />
        </mesh>

        {/* Hood (Sphere Primitive) */}
        <mesh position={[0, 1.75, 0]}>
          <sphereGeometry args={[0.32, 12, 12]} />
          <meshStandardMaterial color="#0e1428" roughness={0.6} metalness={0.3} />
        </mesh>

        {/* Emissive Visor Strip */}
        <mesh position={[0.18, 1.72, 0.22]} rotation={[0, Math.PI / 4, 0]}>
          <boxGeometry args={[0.26, 0.05, 0.02]} />
          <meshBasicMaterial color="#ff0055" />
        </mesh>

        {/* Hands on Terminal */}
        <mesh ref={leftHandRef} position={[0.25, 1.05, 0.45]}>
          <boxGeometry args={[0.08, 0.04, 0.12]} />
          <meshStandardMaterial color="#1a2238" roughness={0.5} />
        </mesh>
        <mesh ref={rightHandRef} position={[0.45, 1.05, 0.35]}>
          <boxGeometry args={[0.08, 0.04, 0.12]} />
          <meshStandardMaterial color="#1a2238" roughness={0.5} />
        </mesh>
      </group>

      {/* Holographic Terminal Desk */}
      <group position={[0.3, 0.6, 0.4]} rotation={[0, -Math.PI / 6, 0]}>
        {/* Terminal Stand */}
        <mesh position={[0, -0.1, 0]}>
          <cylinderGeometry args={[0.08, 0.12, 0.8, 8]} />
          <meshStandardMaterial color="#141b2f" metalness={0.7} roughness={0.3} />
        </mesh>

        {/* Angled Hologram Console */}
        <mesh ref={terminalScreenRef} position={[0, 0.45, 0]} rotation={[-Math.PI / 6, 0, 0]}>
          <boxGeometry args={[0.7, 0.02, 0.45]} />
          <meshBasicMaterial color="#00f2fe" transparent opacity={0.85} />
        </mesh>

        {/* Light Emitter */}
        <pointLight ref={terminalFlashRef} position={[0, 0.7, 0]} distance={4} />

        {/* Floating Holographic Glyphs */}
        <group ref={glyphsGroupRef} position={[0, 0.65, 0]}>
          <mesh position={[0.15, 0.08, 0]}>
            <octahedronGeometry args={[0.04]} />
            <meshBasicMaterial color="#00f2fe" wireframe />
          </mesh>
          <mesh position={[-0.15, 0.12, 0.05]}>
            <tetrahedronGeometry args={[0.035]} />
            <meshBasicMaterial color="#ff0055" wireframe />
          </mesh>
          <mesh position={[0.02, 0.18, -0.08]}>
            <boxGeometry args={[0.04, 0.04, 0.04]} />
            <meshBasicMaterial color="#b026ff" wireframe />
          </mesh>
        </group>
      </group>
    </group>
  );
};
