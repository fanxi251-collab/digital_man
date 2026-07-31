import { ref, unref } from "vue";

import { fetchMapConfig, loadAmapScript } from "../../../lib/amapLoader.js";
import { parseTourPoint } from "../lib/geo.js";

export function createGuidedTourMap(target, options = {}) {
  const configFetcher = options.configFetcher || fetchMapConfig;
  const scriptLoader = options.scriptLoader || loadAmapScript;
  const amapAccessor = options.amap || (() => globalThis.window?.AMap);
  const now = options.now || (() => Date.now());
  const mode = ref("loading");
  const notice = ref("正在准备随行地图…");
  let map = null;
  let amap = null;
  let currentRoute = null;
  let routeLine = null;
  let previewLine = null;
  let stopMarkers = [];
  let visitorMarker = null;
  let lastFollowAt = 0;

  async function initialize(route, stops = []) {
    destroyMap();
    currentRoute = route || null;
    mode.value = "loading";
    notice.value = "正在准备随行地图…";
    try {
      const config = await configFetcher();
      if (!config?.enabled || !config.js_api_key || !config.security_js_code) {
        activateFallback(config?.message || "高德地图配置不完整，已切换本地导览图。 ");
        return false;
      }
      await scriptLoader(config.js_api_key, config.security_js_code);
      amap = amapAccessor();
      const element = resolveTarget(target);
      if (!amap || !element) throw new Error("地图容器尚未就绪");
      const firstPoint = routePoints(route)[0] || [120.1, 31.425];
      map = new amap.Map(element, {
        zoom: 16,
        center: firstPoint,
        viewMode: "2D",
        mapStyle: config.map_style || "amap://styles/normal",
        animateEnable: true,
      });
      drawStops(stops);
      renderRoute(route);
      mode.value = "amap";
      notice.value = "青绿色为当前路线，暖金色为待接管路线。";
      return true;
    } catch (error) {
      activateFallback(`地图加载失败：${error?.message || "未知错误"}，已切换本地导览图。`);
      return false;
    }
  }

  function drawStops(stops) {
    if (!map || !amap) return;
    removeOverlays(stopMarkers);
    stopMarkers = (stops || []).flatMap((stop) => {
      const point = parseTourPoint(stop);
      if (!point) return [];
      return [new amap.Marker({
        map,
        position: [point.longitude, point.latitude],
        title: String(stop.attraction_name || "景点"),
        content: `<span class="guided-tour-stop-marker" aria-hidden="true"></span>`,
        offset: amap.Pixel ? new amap.Pixel(-8, -8) : undefined,
        zIndex: 110,
      })];
    });
  }

  function renderRoute(route) {
    currentRoute = route || null;
    routeLine = replaceLine(routeLine, route, {
      strokeColor: "#2f7d78",
      strokeWeight: 7,
      strokeOpacity: 0.94,
    });
    fitCurrentView();
  }

  function previewRoute(route) {
    previewLine = replaceLine(previewLine, route, {
      strokeColor: "#d4a64c",
      strokeWeight: 6,
      strokeOpacity: 0.9,
      strokeStyle: "dashed",
    });
  }

  function clearPreview() {
    removeOverlays(previewLine ? [previewLine] : []);
    previewLine = null;
  }

  function replaceLine(previous, route, style) {
    removeOverlays(previous ? [previous] : []);
    if (!map || !amap) return null;
    const path = routePoints(route);
    if (path.length < 2) return null;
    return new amap.Polyline({ map, path, ...style });
  }

  function updatePosition(position, { follow = true } = {}) {
    if (!map || !amap) return;
    const point = parseTourPoint(position);
    if (!point) return;
    const lngLat = [point.longitude, point.latitude];
    if (!visitorMarker) {
      visitorMarker = new amap.Marker({
        map,
        position: lngLat,
        title: "游客当前位置",
        content: visitorMarkerContent(position?.heading),
        offset: amap.Pixel ? new amap.Pixel(-12, -12) : undefined,
        zIndex: 160,
      });
    } else {
      visitorMarker.setPosition?.(lngLat);
      visitorMarker.setContent?.(visitorMarkerContent(position?.heading));
    }
    const timestamp = now();
    if (follow && timestamp - lastFollowAt >= 650) {
      map.setCenter?.(lngLat, true);
      lastFollowAt = timestamp;
    }
  }

  function focusStop(stop) {
    const point = parseTourPoint(stop);
    if (!map || !point) return;
    map.setZoomAndCenter?.(
      Number(stop?.focus_zoom) || 18,
      [point.longitude, point.latitude],
      true,
    );
  }

  function resumeFollow() {
    fitCurrentView();
  }

  function fitCurrentView() {
    if (!map) return;
    const overlays = [...stopMarkers, routeLine, visitorMarker].filter(Boolean);
    if (overlays.length) map.setFitView?.(overlays, false, [42, 42, 42, 42]);
  }

  function resize() {
    map?.resize?.();
  }

  function activateFallback(message) {
    destroyMap();
    mode.value = "fallback";
    notice.value = message;
  }

  function removeOverlays(items) {
    if (map && items.length) map.remove?.(items);
  }

  function destroyMap() {
    if (map) map.destroy?.();
    map = null;
    amap = null;
    routeLine = null;
    previewLine = null;
    stopMarkers = [];
    visitorMarker = null;
    lastFollowAt = 0;
  }

  function destroy() {
    destroyMap();
    mode.value = "idle";
  }

  return {
    mode,
    notice,
    initialize,
    drawStops,
    renderRoute,
    previewRoute,
    clearPreview,
    updatePosition,
    focusStop,
    resumeFollow,
    resize,
    destroy,
  };
}

function routePoints(route) {
  return (route?.points || route?.polyline || []).flatMap((value) => {
    const point = parseTourPoint(value);
    return point ? [[point.longitude, point.latitude]] : [];
  });
}

function resolveTarget(target) {
  const value = unref(target);
  if (typeof value === "string") return document.getElementById(value);
  return value || null;
}

function visitorMarkerContent(heading) {
  const rotation = Number.isFinite(Number(heading)) ? Number(heading) : 0;
  return `<span class="guided-tour-visitor-marker" style="--tour-heading:${rotation}deg" aria-hidden="true"><i></i></span>`;
}
