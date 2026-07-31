import { parseTourPoint } from "./geo.js";

export function buildPublishedTourStops(attractions, coreStops = []) {
  const publicAttractions = (attractions || []).filter(isUsablePublishedAttraction);
  const attractionByName = new Map(publicAttractions.map((item) => [item.name, item]));
  const coreNames = new Set((coreStops || []).map((stop) => stop.attraction_name));
  const approved = (coreStops || []).flatMap((stop) => {
    const point = parseTourPoint(stop);
    if (!point || !String(stop?.narration_text || "").trim()) return [];
    const record = attractionByName.get(stop.attraction_name);
    return [{
      ...stop,
      ...point,
      ...(record ? { attraction_id: record.attraction_id } : {}),
    }];
  });
  const additional = publicAttractions.flatMap((attraction) => {
    if (coreNames.has(attraction.name)) return [];
    const point = parseTourPoint(attraction);
    if (!point) return [];
    return [{
      stop_id: `attraction:${attraction.attraction_id}`,
      attraction_id: attraction.attraction_id,
      attraction_name: attraction.name,
      narration_text: attraction.summary.trim(),
      ...point,
      trigger_radius_m: 35,
      dwell_ms: 3000,
      focus_zoom: 18,
    }];
  });
  return [...approved, ...additional];
}

export function stopsNearRoute(stops, route, maximumDistance = 60) {
  const points = (route?.points || []).map(parseTourPoint).filter(Boolean);
  if (points.length < 2) return [];
  const threshold = Math.max(1, Number(maximumDistance) || 60);
  return (stops || []).filter((stop) => {
    const point = parseTourPoint(stop);
    if (!point) return false;
    for (let index = 1; index < points.length; index += 1) {
      if (distanceToLocalSegment(point, points[index - 1], points[index]) <= threshold) return true;
    }
    return false;
  });
}

function isUsablePublishedAttraction(attraction) {
  if (!attraction || (attraction.status && attraction.status !== "published")) return false;
  return Boolean(
    String(attraction.attraction_id || "").trim()
    && String(attraction.name || "").trim()
    && String(attraction.summary || "").trim()
    && parseTourPoint(attraction),
  );
}

function distanceToLocalSegment(point, start, end) {
  const referenceLatitude = (point.latitude + start.latitude + end.latitude) / 3;
  const longitudeScale = Math.cos(referenceLatitude * Math.PI / 180) * 111195.0802335;
  const latitudeScale = 111195.0802335;
  const px = point.longitude * longitudeScale;
  const py = point.latitude * latitudeScale;
  const ax = start.longitude * longitudeScale;
  const ay = start.latitude * latitudeScale;
  const bx = end.longitude * longitudeScale;
  const by = end.latitude * latitudeScale;
  const dx = bx - ax;
  const dy = by - ay;
  if (!dx && !dy) return Math.hypot(px - ax, py - ay);
  const ratio = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)));
  return Math.hypot(px - (ax + ratio * dx), py - (ay + ratio * dy));
}
