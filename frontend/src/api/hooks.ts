import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  api,
  getJson,
  unwrap,
  type DefenseAction,
  type Incident,
  type Module,
  type ModelVersion,
  type ReviewItem,
  type Scan,
  type ScanDetail,
  type SimulatorStatus,
  type StatsSummary,
  type Taxonomy,
} from './client';

export function useTaxonomy() {
  return useQuery({
    queryKey: ['taxonomy'],
    queryFn: () => getJson<Taxonomy>('/api/taxonomy'),
    staleTime: Infinity,
  });
}

export function useFamily(module: Module, id: string | undefined) {
  const { data } = useTaxonomy();
  return data?.families.find((f) => f.module === module && f.id === id);
}

export function useIncidents(module: Module) {
  return useQuery({
    queryKey: ['incidents', module],
    queryFn: () =>
      unwrap<Incident[]>(api.GET('/api/incidents', { params: { query: { module, limit: 30 } } })),
  });
}

export function useActions() {
  return useQuery({
    queryKey: ['actions'],
    queryFn: () =>
      unwrap<DefenseAction[]>(api.GET('/api/actions', { params: { query: { limit: 20 } } })),
  });
}

export function useDetection(id: string | undefined) {
  return useQuery({
    queryKey: ['detection', id],
    enabled: Boolean(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/detections/{detection_id}', { params: { path: { detection_id: id! } } })
      ),
    staleTime: 60_000,
  });
}

export function useStats(module?: Module, windowMinutes = 30) {
  return useQuery({
    queryKey: ['stats', module, windowMinutes],
    queryFn: () =>
      getJson<StatsSummary>(
        `/api/stats/summary?window_minutes=${windowMinutes}${module ? `&module=${module}` : ''}`
      ),
    refetchInterval: 10_000,
  });
}

export function useUndoAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap<DefenseAction>(
        api.POST('/api/actions/{action_id}/undo', { params: { path: { action_id: id } } })
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['actions'] }),
  });
}

export function useSimulator() {
  return useQuery({
    queryKey: ['simulator'],
    queryFn: () => getJson<SimulatorStatus>('/api/simulate'),
    refetchInterval: (q) => (q.state.data?.running ? 1000 : false),
    retry: false,
  });
}

export function useStartSimulation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { scenario: string; duration_s: number }) =>
      unwrap(api.POST('/api/simulate', { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['simulator'] }),
  });
}

export function useStopSimulation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.DELETE('/api/simulate')),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['simulator'] }),
  });
}

export function useScans() {
  return useQuery({
    queryKey: ['scans'],
    queryFn: () => unwrap<Scan[]>(api.GET('/api/scans', { params: { query: { limit: 12 } } })),
  });
}

export function useScan(id: string | undefined) {
  return useQuery({
    queryKey: ['scans', id],
    enabled: Boolean(id),
    queryFn: () =>
      unwrap<ScanDetail>(api.GET('/api/scans/{scan_id}', { params: { path: { scan_id: id! } } })),
    // Live scan_complete events refresh this; polling is the fallback if the socket is down.
    refetchInterval: (q) =>
      q.state.data && ['queued', 'running'].includes(q.state.data.status) ? 3000 : false,
  });
}

export function useSubmitScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (url: string) => unwrap<Scan>(api.POST('/api/scans', { body: { url } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scans'] }),
  });
}

export function useReviewQueue(module?: Module) {
  return useQuery({
    queryKey: ['review-queue', module],
    queryFn: () =>
      unwrap<ReviewItem[]>(
        api.GET('/api/review-queue', {
          params: { query: { module, status: 'pending', limit: 50 } },
        })
      ),
  });
}

export function useReviewDecision() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, label, reject }: { id: string; label?: string; reject?: boolean }) =>
      reject
        ? unwrap(
            api.POST('/api/review-queue/{item_id}/reject', {
              params: { path: { item_id: id } },
              body: {},
            })
          )
        : unwrap(
            api.POST('/api/review-queue/{item_id}/confirm', {
              params: { path: { item_id: id } },
              body: { label: label! },
            })
          ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['review-queue'] }),
  });
}

export function useModels() {
  return useQuery({
    queryKey: ['models'],
    queryFn: () => unwrap<ModelVersion[]>(api.GET('/api/models')),
  });
}

export function useRetrain() {
  return useMutation({
    mutationFn: (module: Module) =>
      unwrap(api.POST('/api/models/{module}/retrain', { params: { path: { module } } })),
  });
}

export function usePromote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ module, version }: { module: Module; version: string }) =>
      unwrap(
        api.POST('/api/models/{module}/{version}/promote', {
          params: { path: { module, version } },
        })
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['models'] }),
  });
}

export interface ModelSchema {
  module: Module;
  version: string;
  threshold: number;
  classes: string[];
  features: Array<{ name: string; description: string; baseline: number | null }>;
}

export function useModelSchema(module: Module) {
  return useQuery({
    queryKey: ['models', module, 'schema'],
    queryFn: () => getJson<ModelSchema>(`/api/models/${module}/schema`),
    staleTime: 60_000,
  });
}
