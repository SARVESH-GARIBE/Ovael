import { useState, useEffect } from 'react';

/**
 * Hook to check if WebGL is supported in the current environment.
 */
export function useWebGLSupport(): boolean {
  const [supported, setSupported] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    try {
      const canvas = document.createElement('canvas');
      const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
      return Boolean(gl && gl instanceof WebGLRenderingContext);
    } catch {
      return false;
    }
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      const canvas = document.createElement('canvas');
      const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
      setSupported(Boolean(gl && gl instanceof WebGLRenderingContext));
    } catch {
      setSupported(false);
    }
  }, []);

  return supported;
}
