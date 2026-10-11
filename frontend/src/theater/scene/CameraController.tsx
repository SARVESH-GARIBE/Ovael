import React, { useRef } from 'react';
import * as THREE from 'three';
import { useFrame, useThree } from '@react-three/fiber';

interface CameraControllerProps {
  enableDrift?: boolean;
  reducedMotion?: boolean;
}

export const CameraController: React.FC<CameraControllerProps> = ({
  enableDrift = true,
  reducedMotion = false,
}) => {
  const { camera, pointer } = useThree();
  const basePosition = useRef(new THREE.Vector3(0, 3.2, 10.5));
  const lookTarget = useRef(new THREE.Vector3(0, 1.2, 0));

  useFrame(({ clock }) => {
    if (reducedMotion) {
      camera.position.copy(basePosition.current);
      camera.lookAt(lookTarget.current);
      return;
    }

    const t = clock.getElapsedTime();

    // Subtle pointer parallax
    const parallaxX = pointer.x * 0.8;
    const parallaxY = pointer.y * 0.4;

    // Slow camera drift
    const driftX = enableDrift ? Math.sin(t * 0.3) * 0.6 : 0;
    const driftY = enableDrift ? Math.cos(t * 0.2) * 0.2 : 0;

    const targetPos = new THREE.Vector3(
      basePosition.current.x + parallaxX + driftX,
      basePosition.current.y + parallaxY + driftY,
      basePosition.current.z
    );

    camera.position.lerp(targetPos, 0.05);
    camera.lookAt(lookTarget.current);
  });

  return null;
};
