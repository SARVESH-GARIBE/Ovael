import { useState, useCallback } from 'react';

export type QualityTier = 'high' | 'medium' | 'low';

const STORAGE_KEY = 'ovael_quality_tier';

/**
 * Hook for graphics quality tier: high | medium | low.
 * Allows manual override kept in sessionStorage.
 */
export function useQualityTier(initialDefault: QualityTier = 'high') {
  const [tier, setTierState] = useState<QualityTier>(() => {
    if (typeof window === 'undefined') return initialDefault;
    try {
      const stored = sessionStorage.getItem(STORAGE_KEY);
      if (stored === 'high' || stored === 'medium' || stored === 'low') {
        return stored;
      }
    } catch {
      // sessionStorage unavailable
    }
    return initialDefault;
  });

  const setTier = useCallback((newTier: QualityTier) => {
    setTierState(newTier);
    try {
      sessionStorage.setItem(STORAGE_KEY, newTier);
    } catch {
      // ignore
    }
  }, []);

  return [tier, setTier] as const;
}
