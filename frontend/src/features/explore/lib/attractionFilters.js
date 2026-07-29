export function filterAttractions(attractions, filters = {}) {
  const keyword = String(filters.keyword || "").trim().toLowerCase();
  const category = String(filters.category || "");
  return attractions.filter((item) => {
    const searchable = `${item.name} ${item.summary} ${(item.tags || []).join(" ")}`.toLowerCase();
    const matchesText = !keyword || searchable.includes(keyword);
    return matchesText && (!category || item.category === category);
  });
}
