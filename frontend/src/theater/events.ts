import { z } from 'zod';

export const FlowMetadataSchema = z
  .object({
    source_ip: z.string().nullable().optional(),
    destination_ip: z.string().nullable().optional(),
    source_port: z.number().nullable().optional(),
    destination_port: z.number().nullable().optional(),
    protocol: z.union([z.number(), z.string()]).nullable().optional(),
    payload_size: z.number().nullable().optional(),
    timestamp: z.string().nullable().optional(),
  })
  .passthrough();

export type FlowMetadata = z.infer<typeof FlowMetadataSchema>;

export const TheaterEventSchema = z
  .object({
    id: z.string().default(() => Math.random().toString(36).substring(2, 9)),
    scan_id: z.string().optional(),
    domain: z.literal('network').default('network'),
    status: z.enum(['queued', 'running', 'completed', 'failed']).default('completed'),
    origin: z.enum(['live', 'stored', 'demo']).default('demo'),
    is_stub: z.boolean().default(false),
    predicted_class: z.string().default('benign'),
    confidence: z.number().min(0).max(1).default(1.0),
    is_novel: z.boolean().default(false),
    novelty_score: z.number().min(0).max(1).default(0.0),
    risk_score: z.number().default(0.0),
    severity: z.string().default('unknown-placeholder'),
    flow_metadata: FlowMetadataSchema.optional().default({}),
    timestamp: z.number().default(() => Date.now()),
  })
  .passthrough();

export type TheaterEvent = z.infer<typeof TheaterEventSchema>;

/**
 * Validates untrusted input. A bad event is dropped and counted, never thrown.
 */
let droppedEventsCount = 0;

export function parseTheaterEvent(raw: unknown): TheaterEvent | null {
  const result = TheaterEventSchema.safeParse(raw);
  if (!result.success) {
    droppedEventsCount++;
    return null;
  }
  return result.data;
}

export function getDroppedEventsCount(): number {
  return droppedEventsCount;
}

export function resetDroppedEventsCount(): void {
  droppedEventsCount = 0;
}
