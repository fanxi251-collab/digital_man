let amapLoadPromise = null;

export async function fetchMapConfig() {
  const response = await fetch("/api/tools/map/config");
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

export function loadAmapScript(jsApiKey, securityCode) {
  if (globalThis.window?.AMap) return Promise.resolve();
  if (amapLoadPromise) return amapLoadPromise;
  // Security config must register before the AMap script so Web keys pass platform checks.
  globalThis.window._AMapSecurityConfig = { securityJsCode: securityCode };
  amapLoadPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(jsApiKey)}`;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("高德 JS API 加载失败"));
    document.head.appendChild(script);
  });
  return amapLoadPromise;
}

export function parseLngLat(point) {
  const [longitude, latitude] = String(point || "").split(",").map(Number);
  return Number.isFinite(longitude) && Number.isFinite(latitude) ? [longitude, latitude] : null;
}

/** Test helper: reset the module-level script load promise between cases. */
export function resetAmapLoadPromiseForTests() {
  amapLoadPromise = null;
}
