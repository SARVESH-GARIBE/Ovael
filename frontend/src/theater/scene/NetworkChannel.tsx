import React, { useRef, useMemo } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';

interface NetworkChannelProps {
  reducedMotion?: boolean;
}

export const NetworkChannel: React.FC<NetworkChannelProps> = ({ reducedMotion }) => {
  const channelLineRef = useRef<THREE.Mesh>(null);
  const particlesRef = useRef<THREE.Points>(null);

  // Generate 80 ambient dust particles procedurally
  const particleCount = 80;
  const particlePositions = useMemo(() => {
    const pos = new Float32Array(particleCount * 3);
    for (let i = 0; i < particleCount; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 16;
      pos[i * 3 + 1] = Math.random() * 3.5;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 8;
    }
    return pos;
  }, []);

  useFrame(({ clock }) => {
    if (reducedMotion) return;
    const t = clock.getElapsedTime();

    if (channelLineRef.current) {
      const mat = channelLineRef.current.material as THREE.MeshBasicMaterial;
      mat.opacity = 0.5 + 0.25 * Math.sin(t * 3);
    }

    if (particlesRef.current) {
      particlesRef.current.rotation.y = t * 0.02;
    }
  });

  return (
    <group>
      {/* Reflective Grid Floor */}
      <gridHelper
        args={[24, 24, '#1e2844', '#0d1324']}
        position={[0, -0.01, 0]}
      />

      {/* Main Glowing Network Cable/Channel (from x = -4.5 to +4.5) */}
      <mesh ref={channelLineRef} position={[0, 0.05, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.06, 0.06, 9.0, 16]} />
        <meshBasicMaterial color="#00f2fe" transparent opacity={0.6} />
      </mesh>

      {/* Dual Guard Rails */}
      <mesh position={[0, 0.02, 0.4]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.02, 0.02, 9.0, 8]} />
        <meshBasicMaterial color="#141b2f" />
      </mesh>
      <mesh position={[0, 0.02, -0.4]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.02, 0.02, 9.0, 8]} />
        <meshBasicMaterial color="#141b2f" />
      </mesh>

      {/* Ambient Floating Dust Particles */}
      <points ref={particlesRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[particlePositions, 3]}
          />
        </bufferGeometry>
        <pointsMaterial
          size={0.04}
          color="#42558b"
          transparent
          opacity={0.5}
        />
      </points>
    </group>
  );
};
