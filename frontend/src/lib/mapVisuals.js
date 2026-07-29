export function createPlaceMarkerElement(place, selected) {
  const marker = document.createElement("span");
  marker.className = [
    "map-place-marker",
    place.kind === "food" ? "is-food" : "is-attraction",
    selected ? "is-selected" : "",
  ].filter(Boolean).join(" ");
  marker.title = place.name || "";
  const core = document.createElement("i");
  core.className = "map-place-marker-core";
  marker.appendChild(core);
  return marker;
}
