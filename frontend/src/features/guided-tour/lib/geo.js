const EARTH_RADIUS_METERS = 6371008.8;

export function parseTourPoint(value) {
  let longitude;
  let latitude;
  if (Array.isArray(value)) {
    [longitude, latitude] = value;
  } else if (typeof value === "string") {
    [longitude, latitude] = value.split(",", 2);
  } else if (value && typeof value === "object") {
    longitude = value.longitude ?? value.lng;
    latitude = value.latitude ?? value.lat;
  }

  longitude = Number(longitude);
  latitude = Number(latitude);
  if (
    !Number.isFinite(longitude)
    || !Number.isFinite(latitude)
    || longitude < -180
    || longitude > 180
    || latitude < -90
    || latitude > 90
  ) return null;
  return { longitude, latitude };
}

export function distanceMeters(first, second) {
  const start = parseTourPoint(first);
  const end = parseTourPoint(second);
  if (!start || !end) return Number.POSITIVE_INFINITY;
  if (start.longitude === end.longitude && start.latitude === end.latitude) return 0;

  const latitudeDelta = toRadians(end.latitude - start.latitude);
  const longitudeDelta = toRadians(end.longitude - start.longitude);
  const startLatitude = toRadians(start.latitude);
  const endLatitude = toRadians(end.latitude);
  const haversine = (
    Math.sin(latitudeDelta / 2) ** 2
    + Math.cos(startLatitude) * Math.cos(endLatitude) * Math.sin(longitudeDelta / 2) ** 2
  );
  return 2 * EARTH_RADIUS_METERS * Math.asin(Math.min(1, Math.sqrt(haversine)));
}

export function buildRouteMetrics(polyline) {
  const points = [];
  for (const value of polyline || []) {
    const point = parseTourPoint(value);
    if (!point || samePoint(point, points.at(-1))) continue;
    points.push(point);
  }

  let totalDistance = 0;
  const segments = [];
  for (let index = 1; index < points.length; index += 1) {
    const start = points[index - 1];
    const end = points[index];
    const length = distanceMeters(start, end);
    if (!Number.isFinite(length) || length <= 0) continue;
    segments.push({
      start,
      end,
      length,
      startDistance: totalDistance,
      endDistance: totalDistance + length,
      heading: routeHeading(start, end),
    });
    totalDistance += length;
  }
  return { points, segments, totalDistance };
}

export function interpolateRoutePosition(metrics, travelledDistance) {
  const points = metrics?.points || [];
  if (!points.length) return null;
  const segments = metrics?.segments || [];
  if (!segments.length) return { ...points[0], heading: 0 };

  const distance = Math.max(0, Math.min(Number(travelledDistance) || 0, metrics.totalDistance));
  const segment = segments.find((item) => distance <= item.endDistance) || segments.at(-1);
  const ratio = segment.length
    ? Math.max(0, Math.min(1, (distance - segment.startDistance) / segment.length))
    : 0;
  return {
    longitude: interpolate(segment.start.longitude, segment.end.longitude, ratio),
    latitude: interpolate(segment.start.latitude, segment.end.latitude, ratio),
    heading: segment.heading,
  };
}

function routeHeading(start, end) {
  // Local planar bearing keeps the visitor arrow visually stable because scenic routes cover short distances.
  const longitudeScale = Math.cos(toRadians((start.latitude + end.latitude) / 2));
  const east = (end.longitude - start.longitude) * longitudeScale;
  const north = end.latitude - start.latitude;
  return Math.round((toDegrees(Math.atan2(east, north)) + 360) % 360);
}

function samePoint(first, second) {
  return Boolean(
    first
    && second
    && first.longitude === second.longitude
    && first.latitude === second.latitude,
  );
}

function interpolate(start, end, ratio) {
  return start + (end - start) * ratio;
}

function toRadians(value) {
  return value * Math.PI / 180;
}

function toDegrees(value) {
  return value * 180 / Math.PI;
}
