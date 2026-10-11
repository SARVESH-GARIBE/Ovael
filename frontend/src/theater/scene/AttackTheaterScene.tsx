import React from 'react';
import { Canvas } from '@react-three/fiber';
import { EffectComposer, Bloom, Vignette } from '@react-three/postprocessing';
import { Chambers } from './Chambers';
import { AttackerFigure } from './AttackerFigure';
import { VictimTower } from './VictimTower';
import { NetworkChannel } from './NetworkChannel';
import { PacketSwarm } from './PacketSwarm';
import { CameraController } from './CameraController';
import { SceneCommand } from '../director';
import { QualityTier } from '../../hooks/useQualityTier';

interface AttackTheaterSceneProps {
  activeWaves: SceneCommand[];
  qualityTier: QualityTier;
  reducedMotion: boolean;
  enableCameraDrift: boolean;
}

export const AttackTheaterScene: React.FC<AttackTheaterSceneProps> = ({
  activeWaves,
  qualityTier,
  reducedMotion,
  enableCameraDrift,
}) => {
  const isAttacking = activeWaves.length > 0;
  const currentFamily = activeWaves.length > 0 ? activeWaves[0].family : null;
  const maxIntensity = activeWaves.reduce((acc, w) => Math.max(acc, w.intensity), 1);

  const dpr = qualityTier === 'high' ? [1, 1.5] : [1, 1];

  return (
    <Canvas
      dpr={dpr as [number, number]}
      camera={{ position: [0, 3.2, 10.5], fov: 45 }}
      gl={{ antialias: qualityTier !== 'low', powerPreference: 'high-performance' }}
      className="w-full h-full"
    >
      <color attach="background" args={['#06080e']} />
      <ambientLight intensity={0.4} />

      {/* Main stage point lights */}
      <pointLight position={[-5, 4, 2]} intensity={1.5} color="#ff0055" distance={10} />
      <pointLight position={[5, 4, 2]} intensity={1.5} color="#00f2fe" distance={10} />
      <directionalLight position={[0, 8, 4]} intensity={0.6} />

      {/* Procedural Chambers and Stage */}
      <Chambers reducedMotion={reducedMotion} />
      <AttackerFigure
        isAttacking={isAttacking}
        intensity={maxIntensity}
        reducedMotion={reducedMotion}
      />
      <VictimTower
        currentFamily={currentFamily}
        intensity={maxIntensity}
        reducedMotion={reducedMotion}
      />
      <NetworkChannel reducedMotion={reducedMotion} />
      <PacketSwarm activeWaves={activeWaves} reducedMotion={reducedMotion} />

      {/* Camera Controller */}
      <CameraController
        enableDrift={enableCameraDrift}
        reducedMotion={reducedMotion}
      />

      {/* Post Processing on High Tier Only */}
      {qualityTier === 'high' && !reducedMotion && (
        <EffectComposer multisampling={0}>
          <Bloom
            luminanceThreshold={0.4}
            luminanceSmoothing={0.8}
            intensity={0.6}
          />
          <Vignette eskil={false} offset={0.2} darkness={0.8} />
        </EffectComposer>
      )}
    </Canvas>
  );
};

export default AttackTheaterScene;
