import React, { useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { StyleFamily } from '../styles';

interface VictimTowerProps {
  currentFamily: StyleFamily | null;
  intensity: number;
  reducedMotion?: boolean;
}

export const VictimTower: React.FC<VictimTowerProps> = ({
  currentFamily,
  intensity,
  reducedMotion,
}) => {
  const towerGroupRef = useRef<THREE.Group>(null);
  const shieldDomeRef = useRef<THREE.Mesh>(null);
  const loadRingRef = useRef<THREE.Mesh>(null);
  const portLightsGroupRef = useRef<THREE.Group>(null);
  const lockMeshRef = useRef<THREE.Mesh>(null);
  const webPanelRef = useRef<THREE.Mesh>(null);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();

    // 1. Tower impact shake on flood
    if (!reducedMotion && towerGroupRef.current) {
      if (currentFamily === 'flood') {
        towerGroupRef.current.position.x = 5 + (Math.random() - 0.5) * 0.05 * intensity;
        towerGroupRef.current.position.z = (Math.random() - 0.5) * 0.05 * intensity;
      } else {
        towerGroupRef.current.position.x = 5;
        towerGroupRef.current.position.z = 0;
      }
    }

    // 2. Hex Shield Dome ripple on impact
    if (shieldDomeRef.current) {
      const shieldMat = shieldDomeRef.current.material as THREE.MeshBasicMaterial;
      if (currentFamily === 'flood') {
        const ripple = 0.5 + 0.4 * Math.sin(t * 15);
        shieldMat.opacity = ripple;
        shieldMat.color.set('#ff0055');
      } else if (currentFamily === 'scan') {
        shieldMat.opacity = 0.35 + 0.2 * Math.sin(t * 8);
        shieldMat.color.set('#ffb703');
      } else if (currentFamily === 'stub') {
        shieldMat.opacity = 0.15;
        shieldMat.color.set('#6c757d');
      } else if (currentFamily) {
        shieldMat.opacity = 0.3 + 0.15 * Math.sin(t * 4);
        shieldMat.color.set('#00f2fe');
      } else {
        // Idle
        shieldMat.opacity = 0.1 + 0.05 * Math.sin(t * 2);
        shieldMat.color.set('#00f2fe');
      }
    }

    // 3. Load Ring Gauge (climbs on flood or slow-connection)
    if (loadRingRef.current) {
      const targetScale = currentFamily === 'flood' ? 1.0 + intensity * 0.15 : 1.0;
      loadRingRef.current.scale.lerp(new THREE.Vector3(targetScale, targetScale, targetScale), 0.1);
      loadRingRef.current.rotation.z = t * (currentFamily === 'flood' ? 5 : 1);
    }

    // 4. Port Lights sequential sweep on scan
    if (portLightsGroupRef.current) {
      portLightsGroupRef.current.children.forEach((child, idx) => {
        const mesh = child as THREE.Mesh;
        const mat = mesh.material as THREE.MeshBasicMaterial;
        if (currentFamily === 'scan') {
          const activeIndex = Math.floor((t * 6) % 5);
          if (idx === activeIndex) {
            mat.color.set('#ffb703');
          } else {
            mat.color.set('#3a2e0a');
          }
        } else {
          // Normal status LEDs
          mat.color.set(idx % 2 === 0 ? '#00f59b' : '#00f2fe');
        }
      });
    }

    // 5. Lock rattling feedback on credential attack
    if (lockMeshRef.current) {
      if (currentFamily === 'credential' && !reducedMotion) {
        lockMeshRef.current.rotation.z = Math.sin(t * 30) * 0.2;
      } else {
        lockMeshRef.current.rotation.z = 0;
      }
    }

    // 6. Web Panel shimmer on web attack
    if (webPanelRef.current) {
      const mat = webPanelRef.current.material as THREE.MeshBasicMaterial;
      if (currentFamily === 'web') {
        mat.color.set('#06d6a0');
        mat.opacity = 0.8 + 0.2 * Math.sin(t * 12);
      } else {
        mat.color.set('#1e2844');
        mat.opacity = 0.4;
      }
    }
  });

  return (
    <group ref={towerGroupRef} position={[5, 0, 0]}>
      {/* Central Server Rack / Tower (Box Primitive) */}
      <mesh position={[0, 1.4, 0]}>
        <boxGeometry args={[1.2, 2.6, 1.2]} />
        <meshStandardMaterial color="#0c1224" roughness={0.3} metalness={0.8} />
      </mesh>

      {/* Rack Edge Strips */}
      <mesh position={[0.61, 1.4, 0.61]}>
        <boxGeometry args={[0.04, 2.6, 0.04]} />
        <meshBasicMaterial color="#00f2fe" />
      </mesh>
      <mesh position={[-0.61, 1.4, 0.61]}>
        <boxGeometry args={[0.04, 2.6, 0.04]} />
        <meshBasicMaterial color="#00f2fe" />
      </mesh>

      {/* Column of 5 Port Lights */}
      <group ref={portLightsGroupRef} position={[-0.62, 1.8, 0.3]}>
        {[0, 1, 2, 3, 4].map((i) => (
          <mesh key={i} position={[0, -i * 0.2, 0]}>
            <sphereGeometry args={[0.04, 8, 8]} />
            <meshBasicMaterial color="#00f59b" />
          </mesh>
        ))}
      </group>

      {/* Row of Connection Slots (Slow-connection visualization) */}
      <group position={[0, 0.4, 0.62]}>
        {[-0.4, -0.2, 0, 0.2, 0.4].map((x, idx) => (
          <mesh key={idx} position={[x, 0, 0]}>
            <boxGeometry args={[0.12, 0.08, 0.02]} />
            <meshBasicMaterial
              color={
                currentFamily === 'slow-connection' && idx < intensity * 1.2
                  ? '#fb8500'
                  : '#141b2f'
              }
            />
          </mesh>
        ))}
      </group>

      {/* Credential Lock Plate on Victim */}
      <mesh ref={lockMeshRef} position={[0, 1.2, 0.62]}>
        <torusGeometry args={[0.12, 0.03, 8, 16]} />
        <meshStandardMaterial
          color={currentFamily === 'credential' ? '#e0aaff' : '#2d3b63'}
          metalness={0.9}
        />
      </mesh>

      {/* Web Attack Target Panel */}
      <mesh ref={webPanelRef} position={[0, 2.2, 0.62]}>
        <planeGeometry args={[0.8, 0.35]} />
        <meshBasicMaterial color="#1e2844" transparent opacity={0.4} />
      </mesh>

      {/* Load-Ring Gauge Floating Above Tower */}
      <mesh ref={loadRingRef} position={[0, 2.9, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.7, 0.78, 32]} />
        <meshBasicMaterial
          color={currentFamily === 'flood' ? '#ff0055' : '#00f2fe'}
          transparent
          opacity={0.8}
        />
      </mesh>

      {/* Hex Shield Dome (Procedural hemisphere) */}
      <mesh ref={shieldDomeRef} position={[0, 1.4, 0]}>
        <sphereGeometry args={[1.8, 16, 12, 0, Math.PI * 2, 0, Math.PI * 0.55]} />
        <meshBasicMaterial
          color="#00f2fe"
          wireframe
          transparent
          opacity={0.15}
          side={THREE.DoubleSide}
        />
      </mesh>
    </group>
  );
};
