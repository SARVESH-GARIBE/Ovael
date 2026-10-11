import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useReducedMotion } from '../hooks/useReducedMotion';
import { useQualityTier } from '../hooks/useQualityTier';
import { useWebGLSupport } from '../hooks/useWebGLSupport';

describe('useReducedMotion', () => {
  it('returns false by default in test environment', () => {
    const { result } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(false);
  });
});

describe('useQualityTier', () => {
  it('defaults to high and updates when set', () => {
    const { result } = renderHook(() => useQualityTier('high'));
    expect(result.current[0]).toBe('high');

    act(() => {
      result.current[1]('low');
    });

    expect(result.current[0]).toBe('low');
    expect(sessionStorage.getItem('ovael_quality_tier')).toBe('low');
  });

  it('restores stored quality tier from sessionStorage', () => {
    sessionStorage.setItem('ovael_quality_tier', 'medium');
    const { result } = renderHook(() => useQualityTier('high'));
    expect(result.current[0]).toBe('medium');
  });
});

describe('useWebGLSupport', () => {
  it('detects whether WebGL is supported or fallback is needed', () => {
    const { result } = renderHook(() => useWebGLSupport());
    expect(typeof result.current).toBe('boolean');
  });
});
