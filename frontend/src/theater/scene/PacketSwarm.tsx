import React, { useRef, useMemo, useEffect } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { SceneCommand } from '../director';
import { STYLE_CONFIGS } from '../styles';

interface PacketSwarmProps {
  activeWaves: SceneCommand[];
  reducedMotion?: boolean;
}

const MAX_INSTANCES = 120;
const DUMMY = new THREE.Object3D();

export const PacketSwarm: React.FC<PacketSwarmProps> = ({ activeWaves, reducedMotion }) => {
  const instancedMeshRef = useRef<THREE.InstancedMesh>(null);
  const noveltyMeshRef = useRef<THREE.InstancedMesh>(null);

  // Shared geometry & material for primary packets
  const sphereGeo = useMemo(() => new THREE.SphereGeometry(0.08, 12, 12), []);
  const baseMaterial = useMemo(
    () => new THREE.MeshBasicMaterial({ color: '#ffffff', transparent: true, opacity: 0.9 }),
    []
  );

  // Shared geometry & material for novelty shimmer particles
  const tetraGeo = useMemo(() => new THREE.TetrahedronGeometry(0.06), []);
  const noveltyMaterial = useMemo(
    () => new THREE.MeshBasicMaterial({ color: '#b026ff', wireframe: true, transparent: true, opacity: 0.85 }),
    []
  );

  // Clean up geometries and materials on unmount
  useEffect(() => {
    return () => {
      sphereGeo.dispose();
      baseMaterial.dispose();
      tetraGeo.dispose();
      noveltyMaterial.dispose();
    };
  }, [sphereGeo, baseMaterial, tetraGeo, noveltyMaterial]);

  useFrame(({ clock }) => {
    const mesh = instancedMeshRef.current;
    const novMesh = noveltyMeshRef.current;
    if (!mesh) return;

    const t = clock.getElapsedTime();
    let instanceIdx = 0;
    let novIdx = 0;

    // Resolve protocol color hints if provided
    const getProtocolColor = (proto: string | number | undefined, defaultColor: string) => {
      if (proto === 1 || proto === 'icmp' || proto === 'ICMP') return '#ff9e00'; // ICMP
      if (proto === 6 || proto === 'tcp' || proto === 'TCP') return '#ff0055'; // TCP SYN
      if (proto === 17 || proto === 'udp' || proto === 'UDP') return '#ff5400'; // UDP
      return defaultColor;
    };

    activeWaves.forEach((wave) => {
      const config = STYLE_CONFIGS[wave.family] || STYLE_CONFIGS.unrecognized;
      const count = Math.min(24, 6 * wave.intensity);
      const isReverse = wave.family === 'stealth'; // Leak return stream

      // Compute wave color
      const resolvedColorHex = wave.family === 'flood'
        ? getProtocolColor(wave.protocol, config.primaryColor)
        : wave.isStub
        ? '#6c757d'
        : config.primaryColor;

      const color = new THREE.Color(resolvedColorHex);

      for (let i = 0; i < count; i++) {
        if (instanceIdx >= MAX_INSTANCES) break;

        // Progress along channel from -4.5 (attacker) to +4.5 (victim)
        const speed = reducedMotion ? 0.3 : (wave.family === 'slow-connection' ? 0.5 : 2.2);
        const cycle = ((t * speed + i / count) % 1.0);
        const x = isReverse && i % 2 === 1
          ? 4.5 - cycle * 9.0 // Return leak stream
          : -4.5 + cycle * 9.0;

        // Arc height and spread
        const yArc = Math.sin(cycle * Math.PI) * (wave.family === 'scan' ? 0.3 : 1.2);
        const y = 0.4 + yArc + Math.sin(t * 8 + i) * 0.15;
        const z = Math.cos(t * 6 + i) * (wave.family === 'flood' ? 0.8 : 0.25);

        const scale = wave.family === 'flood' ? 1.4 : wave.family === 'scan' ? 0.7 : 1.0;

        DUMMY.position.set(x, y, z);
        DUMMY.scale.set(scale, scale, scale);
        DUMMY.updateMatrix();

        mesh.setMatrixAt(instanceIdx, DUMMY.matrix);
        mesh.setColorAt(instanceIdx, color);
        instanceIdx++;

        // Novelty shimmer overlay (violet sparks along stream)
        if (wave.hasNoveltyOverlay && novMesh && novIdx < 40) {
          DUMMY.position.set(x + (Math.random() - 0.5) * 0.2, y + 0.25, z + (Math.random() - 0.5) * 0.2);
          DUMMY.rotation.set(t * 4, t * 4, 0);
          DUMMY.scale.set(1.2, 1.2, 1.2);
          DUMMY.updateMatrix();

          novMesh.setMatrixAt(novIdx, DUMMY.matrix);
          novIdx++;
        }
      }
    });

    // Hide remaining unused instances
    for (let i = instanceIdx; i < MAX_INSTANCES; i++) {
      DUMMY.position.set(0, -999, 0);
      DUMMY.updateMatrix();
      mesh.setMatrixAt(i, DUMMY.matrix);
    }

    if (novMesh) {
      for (let i = novIdx; i < 40; i++) {
        DUMMY.position.set(0, -999, 0);
        DUMMY.updateMatrix();
        novMesh.setMatrixAt(i, DUMMY.matrix);
      }
      novMesh.instanceMatrix.needsUpdate = true;
    }

    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) {
      mesh.instanceColor.needsUpdate = true;
    }
  });

  return (
    <group>
      {/* Primary Instanced Packets */}
      <instancedMesh
        ref={instancedMeshRef}
        args={[sphereGeo, baseMaterial, MAX_INSTANCES]}
      />

      {/* Novelty Violet Shimmer Overlay Particles */}
      <instancedMesh
        ref={noveltyMeshRef}
        args={[tetraGeo, noveltyMaterial, 40]}
      />
    </group>
  );
};
