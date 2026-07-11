import { z } from "zod";

/**
 * Zod schemas for the Prometheus HTTP API. Validating at the boundary means a
 * datasource that returns something unexpected fails here, with a clear error,
 * instead of producing `undefined`s deep inside a component.
 *
 * See https://prometheus.io/docs/prometheus/latest/querying/api/
 */

/** A single [unixSeconds, "stringValue"] sample. */
export const SampleSchema = z.tuple([z.number(), z.string()]);
export type Sample = z.infer<typeof SampleSchema>;

/** Label set attached to a series, e.g. { email: "a@b.com", seat_type: "premium" }. */
export const MetricLabelsSchema = z.record(z.string());
export type MetricLabels = z.infer<typeof MetricLabelsSchema>;

const MatrixResultSchema = z.object({
  metric: MetricLabelsSchema,
  values: z.array(SampleSchema),
});

const VectorResultSchema = z.object({
  metric: MetricLabelsSchema,
  value: SampleSchema,
});

export const PromResponseSchema = z.discriminatedUnion("resultType", [
  z.object({
    resultType: z.literal("matrix"),
    result: z.array(MatrixResultSchema),
  }),
  z.object({
    resultType: z.literal("vector"),
    result: z.array(VectorResultSchema),
  }),
]);

export const PromEnvelopeSchema = z.object({
  status: z.literal("success"),
  data: PromResponseSchema,
});

/** A series after parsing: labels plus its time-ordered samples. */
export interface Series {
  labels: MetricLabels;
  samples: Array<{ t: number; v: number }>;
}
