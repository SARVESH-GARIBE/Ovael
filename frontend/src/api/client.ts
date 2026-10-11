import createClient, { type Middleware } from 'openapi-fetch';
import type { components, paths } from './schema';

/**
 * Typed REST client generated from the backend's OpenAPI document (`npm run gen:api`).
 * Paths are relative: the Vite dev proxy (and nginx in production) forward /api and /ws.
 */

type S = components['schemas'];
export type Detection = S['DetectionOut'];
export type DetectionDetail = S['DetectionDetail'];
/** Payload of a new_detection WebSocket event. */
export type LiveDetection = S['DetectionOut'] & { blocked: boolean; incident_count: number };
export type Incident = S['IncidentOut'];
export type Scan = S['ScanOut'];
export type ScanDetail = S['ScanDetail'];
export type DefenseAction = S['ActionOut'];
export type ReviewItem = S['ReviewItemOut'];
export type ModelVersion = S['ModelVersionOut'];
export type TopFeature = S['TopFeature'];
export type Module = 'network' | 'website';
export type RiskLevel = 'low' | 'suspicious' | 'medium' | 'high';

export interface AttackFamily {
  id: string;
  module: Module;
  name: string;
  severity_weight: number;
  summary: string;
  how_it_works: string[];
  indicators: string[];
  mitigations: string[];
  labels: string[];
  mitre: string[];
  kill_chain: string;
  impact: string;
  auto_defense: boolean;
  is_benign: boolean;
}

export interface Taxonomy {
  families: AttackFamily[];
  risk_bands: Record<RiskLevel, [number, number]>;
}

export interface StatsSummary {
  window_minutes: number;
  by_risk_level: Partial<Record<RiskLevel, number>>;
  by_family: Record<string, number>;
  timeline: Array<{ t: string } & Record<RiskLevel, number>>;
  open_incidents: number;
  pending_reviews: number;
  active_blocks: number;
  total: number;
}

export interface SimulatorStatus {
  running: boolean;
  scenario?: string;
  phase?: string | null;
  scenarios: string[];
}

const TOKEN_KEY = 'ovael_admin_token';

export function getAdminToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? '';
  } catch {
    return '';
  }
}

export function setAdminToken(token: string): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: token lives for this page only */
  }
}

const auth: Middleware = {
  onRequest({ request }) {
    const token = getAdminToken();
    if (token) request.headers.set('Authorization', `Bearer ${token}`);
    return request;
  },
};

export const api = createClient<paths>({ baseUrl: '' });
api.use(auth);

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number
  ) {
    super(message);
  }
}

/** Unwraps an openapi-fetch result: returns data or throws a readable ApiError. */
export async function unwrap<T>(
  p: Promise<{ data?: T; error?: unknown; response: Response }>
): Promise<T> {
  const { data, error, response } = await p;
  if (error !== undefined || !response.ok) {
    const detail = (error as { detail?: unknown } | undefined)?.detail;
    const msg =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg).join(', ')
          : `${response.status} ${response.statusText}`;
    throw new ApiError(msg, response.status);
  }
  return data as T;
}

/** For endpoints whose response the OpenAPI document leaves untyped. */
export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, {
    headers: getAdminToken() ? { Authorization: `Bearer ${getAdminToken()}` } : {},
  });
  if (!res.ok) throw new ApiError(`${res.status} ${res.statusText}`, res.status);
  return res.json() as Promise<T>;
}
