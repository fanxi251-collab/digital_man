import { onBeforeUnmount, ref } from "vue";
import { fetchMapConfig, loadAmapScript, parseLngLat } from "../lib/amapLoader.js";
import { createPlaceMarkerElement } from "../lib/mapVisuals.js";

export function useInteractiveMap(elementId) {
  const notice = ref("正在准备互动地图...");
  let map = null;
  let places = [];
  let markers = [];
  let routeLine = null;
  let onSelect = null;
  let selectedPlaceId = "";

  async function initialize(items, selectHandler) {
    places = withValidCoordinates(items);
    onSelect = selectHandler;
    const config = await fetchMapConfig();
    if (!config.enabled || !config.js_api_key || !config.security_js_code) {
      notice.value = config.message || "高德前端地图配置不完整，仍可使用地点列表和文字路线。";
      return false;
    }
    try {
      await loadAmapScript(config.js_api_key, config.security_js_code);
      createMap();
      drawMarkers();
      notice.value = "青绿色为景点，暖金色为美食；点击标记可查看详情。";
      return true;
    } catch (error) {
      notice.value = `地图加载失败：${error.message}`;
      return false;
    }
  }

  function createMap() {
    const element = document.getElementById(elementId);
    if (!element || !window.AMap || map) return;
    map = new window.AMap.Map(element, {
      zoom: 16,
      center: places.length ? [places[0].longitude, places[0].latitude] : [120.09, 31.424],
      viewMode: "2D",
    });
  }

  function drawMarkers({ fit = true } = {}) {
    if (!map || !window.AMap) return;
    if (markers.length) map.remove(markers);
    markers = places.map((place) => {
      const selected = place.place_id === selectedPlaceId;
      const marker = new window.AMap.Marker({
        map,
        position: [place.longitude, place.latitude],
        title: place.name,
        content: createPlaceMarkerElement(place, selected),
        offset: new window.AMap.Pixel(selected ? -17 : -13, selected ? -34 : -26),
        zIndex: selected ? 120 : 100,
      });
      marker.on("click", () => onSelect?.(place));
      return marker;
    });
    if (fit && places.length) map.setFitView(markers);
  }

  function setPlaces(items) {
    places = withValidCoordinates(items);
    if (!map) return;
    if (routeLine) {
      map.remove(routeLine);
      routeLine = null;
    }
    drawMarkers({ fit: true });
  }

  function selectPlace(place) {
    if (!map || !place) return;
    selectedPlaceId = place.place_id || "";
    drawMarkers({ fit: false });
    map.setZoomAndCenter(17, [place.longitude, place.latitude]);
  }

  function renderRoute(summary) {
    if (!map || !window.AMap || !summary) return;
    const path = (summary.polyline || []).map(parseLngLat).filter(Boolean);
    if (path.length < 2) {
      notice.value = "路线坐标不足，暂时只能显示文字步骤。";
      return;
    }
    if (routeLine) map.remove(routeLine);
    routeLine = new window.AMap.Polyline({
      map,
      path,
      strokeColor: "#2f766d",
      strokeWeight: 7,
      strokeOpacity: .9,
    });
    map.setFitView([...markers, routeLine]);
    notice.value = "路线已绘制，实际通行请以现场指引为准。";
  }

  function resize() {
    map?.resize();
  }

  function destroy() {
    if (map) map.destroy();
    map = null;
    markers = [];
    routeLine = null;
  }

  onBeforeUnmount(destroy);
  return { notice, initialize, setPlaces, selectPlace, renderRoute, resize, destroy };
}

function withValidCoordinates(items) {
  return items.filter((item) => Number.isFinite(item.longitude) && Number.isFinite(item.latitude));
}
