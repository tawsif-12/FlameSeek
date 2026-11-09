import type { AOI, PlaceResult } from '../types/api';

export const LOCATION_SECTIONS = ['intelligence', 'now', 'calendar', 'dna'] as const;
export type LocationSection = typeof LOCATION_SECTIONS[number];

export function locationId(area: AOI): string {
  if (area.id) return area.id;
  const text = JSON.stringify([area.name, area.bbox, area.geometry, area.center, area.radius_km]);
  let hash = 14695981039346656037n;
  for (let i = 0; i < text.length; i++) hash = BigInt.asUintN(64, (hash ^ BigInt(text.charCodeAt(i))) * 1099511628211n);
  return `area-${hash.toString(16)}`;
}

export function areaFromUrl(search: string, hash = ''): AOI | null {
  try {
    const value = new URLSearchParams(search).get('area') || new URLSearchParams(hash.replace(/^#/, '')).get('area');
    if (!value) return null;
    const area = JSON.parse(value) as AOI;
    if (!area || typeof area !== 'object') return null;
    const validPoint = (p: number[]) => Array.isArray(p) && p.length >= 2 && p.every(Number.isFinite) && p[0] >= -180 && p[0] <= 180 && p[1] >= -90 && p[1] <= 90;
    if (area.bbox && !(area.bbox.length === 4 && area.bbox.every(Number.isFinite) && validPoint(area.bbox.slice(0, 2)) && validPoint(area.bbox.slice(2)) && area.bbox[0] < area.bbox[2] && area.bbox[1] < area.bbox[3])) return null;
    if (area.geometry) {
      if (!['Polygon', 'MultiPolygon'].includes(area.geometry.type)) return null;
      const polygons = area.geometry.type === 'Polygon' ? [area.geometry.coordinates as number[][][]] : area.geometry.coordinates as number[][][][];
      if (!polygons.length || !polygons.every(poly => poly.length && poly.every(ring => ring.length >= 4 && ring.every(validPoint) && JSON.stringify(ring[0]) === JSON.stringify(ring[ring.length - 1])))) return null;
    }
    if (area.center && (!validPoint(area.center) || !Number.isFinite(area.radius_km) || (area.radius_km ?? 0) <= 0 || (area.radius_km ?? 0) > 500)) return null;
    if (!area.geometry && !area.bbox && !area.center) return null;
    if (area.name !== undefined && typeof area.name !== 'string') return null;
    if (area.id !== undefined && typeof area.id !== 'string') return null;
    return area;
  } catch { return null; }
}

export function dashboardUrl(area: AOI, section: LocationSection | 'memory' | 'events' = 'intelligence', extra: Record<string, string> = {}): string {
  if (section === 'memory') section = 'calendar';
  if (section === 'events') { section = 'intelligence'; extra = { ...extra, view: 'events' }; }
  const payload = JSON.stringify(area);
  const params = new URLSearchParams({ ...extra, location_id: locationId(area) });
  params.delete('area');
  // Large country polygons must not overflow server request-line/header limits.
  // Fragments remain self-contained on refresh but are not sent to the server.
  const fragment = encodeURIComponent(payload).length > 4096 ? `#${new URLSearchParams({ area: payload })}` : '';
  if (!fragment) params.set('area', payload);
  if (section === 'now') params.set('aoi', '1');
  return `/location/${section}?${params}${fragment}`;
}

export function placeArea(place: PlaceResult): AOI | null {
  if (!place.geometry || !['Polygon', 'MultiPolygon'].includes(place.geometry.type)) return null;
  return { id: place.place_id, geometry: place.geometry, bbox: place.bbox, name: place.place_name || place.name.split(',')[0], kind: 'place' };
}

export function featureHref(path: string, area: AOI | null, inDashboard: boolean): string {
  if (!area || !inDashboard) return path;
  const [pathname, query] = path.split('?');
  const section = ({ '/area': 'intelligence', '/fire-map': 'now', '/fire-memory': 'calendar', '/fire-dna': 'dna', '/fire-calendar': 'calendar', '/fire-events': 'events' } as Record<string, LocationSection | 'events'>)[pathname];
  return section ? dashboardUrl(area, section, Object.fromEntries(new URLSearchParams(query))) : path;
}
