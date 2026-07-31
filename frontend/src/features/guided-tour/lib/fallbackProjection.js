import { parseTourPoint } from "./geo.js";

export function buildProjectionBounds(values, paddingRatio = 0.08) {
  const points = (values || []).map(parseTourPoint).filter(Boolean);
  if (!points.length) {
    return { minLongitude: 0, maxLongitude: 1, minLatitude: 0, maxLatitude: 1 };
  }
  let minLongitude = Math.min(...points.map((point) => point.longitude));
  let maxLongitude = Math.max(...points.map((point) => point.longitude));
  let minLatitude = Math.min(...points.map((point) => point.latitude));
  let maxLatitude = Math.max(...points.map((point) => point.latitude));
  const longitudeSpan = maxLongitude - minLongitude;
  const latitudeSpan = maxLatitude - minLatitude;
  if (!longitudeSpan && !latitudeSpan) {
    const epsilon = 0.001;
    return {
      minLongitude: minLongitude - epsilon,
      maxLongitude: maxLongitude + epsilon,
      minLatitude: minLatitude - epsilon,
      maxLatitude: maxLatitude + epsilon,
    };
  }
  const padding = Math.max(0, Math.min(0.4, Number(paddingRatio) || 0));
  const longitudePadding = (longitudeSpan || latitudeSpan) * padding;
  const latitudePadding = (latitudeSpan || longitudeSpan) * padding;
  minLongitude -= longitudePadding;
  maxLongitude += longitudePadding;
  minLatitude -= latitudePadding;
  maxLatitude += latitudePadding;
  return { minLongitude, maxLongitude, minLatitude, maxLatitude };
}

export function projectTourPoint(value, bounds) {
  const point = parseTourPoint(value);
  if (!point || !bounds) return null;
  const longitudeSpan = bounds.maxLongitude - bounds.minLongitude;
  const latitudeSpan = bounds.maxLatitude - bounds.minLatitude;
  return {
    x: clampPercent(longitudeSpan
      ? (point.longitude - bounds.minLongitude) / longitudeSpan * 100
      : 50),
    // SVG grows downward, so northern coordinates must map toward the top.
    y: clampPercent(latitudeSpan
      ? (bounds.maxLatitude - point.latitude) / latitudeSpan * 100
      : 50),
  };
}

export function projectTourPolyline(values, bounds) {
  return (values || [])
    .map((value) => projectTourPoint(value, bounds))
    .filter(Boolean)
    .map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`)
    .join(" ");
}

function clampPercent(value) {
  return Math.max(0, Math.min(100, Number(value)));
}
