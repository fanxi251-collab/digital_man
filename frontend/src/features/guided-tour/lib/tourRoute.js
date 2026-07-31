import { resolveRouteSummary } from "../../../lib/routeSummary.js";
import { buildRouteMetrics } from "./geo.js";

export function normalizeTourRoute(value) {
  const summary = resolveInputSummary(value);
  if (!summary) return null;
  const metrics = buildRouteMetrics(summary.polyline || []);
  if (metrics.points.length < 2 || metrics.totalDistance <= 0) return null;

  const origin = String(summary.origin || "路线起点").trim();
  const destination = String(summary.destination || "路线终点").trim();
  const mode = String(summary.mode || "walking").trim() || "walking";
  return {
    routeId: String(summary.route_id || `ai:${origin}:${destination}:${mode}`),
    name: String(summary.name || `${origin} → ${destination}`),
    origin,
    destination,
    mode,
    points: metrics.points,
    segments: metrics.segments,
    totalDistance: metrics.totalDistance,
    summary,
  };
}

function resolveInputSummary(value) {
  if (!value || typeof value !== "object") return null;
  if (value.metadata) return resolveRouteSummary(value);
  return value;
}
