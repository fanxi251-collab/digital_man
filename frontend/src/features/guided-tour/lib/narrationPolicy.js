export function narrationRequest(stop) {
  const localAudioUrl = String(stop?.local_audio_url || "").trim();
  if (localAudioUrl) return { localAudioUrl, onlineUrl: stopSynthesisUrl(stop) };
  return { localAudioUrl: "", onlineUrl: attractionSynthesisUrl(stop) };
}

export function stopSynthesisUrl(stop) {
  const stopId = encodeURIComponent(String(stop?.stop_id || "").trim());
  return stopId
    ? `/api/visitor/guided-tour/narrations/stops/${stopId}/synthesize`
    : "";
}

export function attractionSynthesisUrl(stop) {
  const attractionId = encodeURIComponent(String(stop?.attraction_id || "").trim());
  return attractionId
    ? `/api/visitor/guided-tour/narrations/attractions/${attractionId}/synthesize`
    : "";
}
