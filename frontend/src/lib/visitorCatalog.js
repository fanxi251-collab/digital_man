async function fetchVisitorJson(url, listKey) {
  const response = await fetch(url);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  const items = data[listKey];
  return Array.isArray(items) ? items : [];
}

export async function fetchVisitorAttractions() {
  const attractions = await fetchVisitorJson("/api/visitor/attractions", "attractions");
  return { attractions };
}

export async function fetchVisitorFoods() {
  const foods = await fetchVisitorJson("/api/visitor/foods", "foods");
  return { foods };
}
