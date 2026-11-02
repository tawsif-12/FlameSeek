import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { GeoJSON, MapContainer, TileLayer, useMap, useMapEvents } from "react-leaflet";
import L, { type LatLngBoundsExpression } from "leaflet";
import { HarmonizedEvent, ListResponse, snapshotGet, SnapshotMeta, useSiteData } from "../api/harmonized";
import { aoiBBox, aoiContains, describeAoi, useAppContext } from "../context/AppContext";
import { useLanguage } from "../context/LanguageContext";
import HarmonizedProvenance, { StatusPill } from "../components/HarmonizedProvenance";
import "../harmonized.css";

/* Fire events of a searched place (Search → "Fire Events"). Each event is drawn as its true
   ground footprint; the side list names every event so nothing on the map is unexplained. */

const INTENSITY_HEX = ["#8f3a14", "#d4561f", "#ff8a4c", "#ffc78a"]; // validated dark-surface ordinal ramp
const UNKNOWN_HEX = "#6b7a90";
/* Below this zoom a fire's true outline is smaller than a screen pixel, so the outline itself is
   drawn with a thick border in its intensity colour to stay visible (still the event's own shape). */
const TRUE_SHAPE_ZOOM = 11;

function ZoomWatcher({ onZoom }: { onZoom: (z: number) => void }) {
  const map = useMapEvents({ zoomend: () => onZoom(map.getZoom()) });
  useEffect(() => onZoom(map.getZoom()), [map, onZoom]);
  return null;
}

function clampBox(b: [number, number, number, number]) {
  const c = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
  return [c(b[0], -180, 180), c(b[1], -90, 90), c(b[2], -180, 180), c(b[3], -90, 90)].map((x) => x.toFixed(4)).join(",");
}

/** Frames the map on the place, or on one event when it is selected. */
function Frame({ box, focus }: { box: [number, number, number, number] | null; focus: GeoJSON.Geometry | null }) {
  const map = useMap();
  useEffect(() => {
    map.stop();
    if (focus) {
      const b = L.geoJSON(focus as GeoJSON.GeoJsonObject).getBounds();
      if (b.isValid()) map.fitBounds(b, { maxZoom: 14, padding: [60, 60], animate: false });
    } else if (box) {
      map.fitBounds([[box[1], box[0]], [box[3], box[2]]] as LatLngBoundsExpression, { padding: [24, 24], animate: false });
    }
  }, [box, focus, map]);
  return null;
}

export default function HarmonizedMapPage() {
  const { t, lang, fmt } = useLanguage();
  const { aoi } = useAppContext();
  const { data: site } = useSiteData();
  const [win, setWin] = useState("current_2026");
  const [list, setList] = useState<ListResponse<HarmonizedEvent> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<HarmonizedEvent | null>(null);
  const [zoom, setZoom] = useState(6);
  const req = useRef(0);
  const small = zoom < TRUE_SHAPE_ZOOM;

  const box = useMemo(() => (aoi ? aoiBBox(aoi) : null), [aoi]);
  const words = (site?.translation.words.en.intensity as string[] | undefined) ?? [];
  const thresholds = site?.intensity_classes_mw ?? [];
  const classOf = useCallback((e: HarmonizedEvent) => words.indexOf(String(e.translation?.en?.intensity ?? "")), [words]);
  const colourOf = (cls: number) => (cls >= 0 ? INTENSITY_HEX[cls] : UNKNOWN_HEX);
  const peak = (e: HarmonizedEvent) => Math.max(e.FRP_VIIRS_max ?? -1, e.FRP_MODIS_max ?? -1);

  // All events of the window in the searched place.
  useEffect(() => {
    if (!box) return;
    const id = ++req.current;
    setLoading(true);
    setError(null);
    setSelected(null);
    snapshotGet<ListResponse<HarmonizedEvent>>("/fires", { window: win, bbox: clampBox(box), limit: 5000, geometry: true })
      .then((r) => id === req.current && setList(r))
      .catch((e) => id === req.current && (setError((e as Error).message), setList(null)))
      .finally(() => id === req.current && setLoading(false));
  }, [box, win]);

  // Keep only events inside the place's own outline (not just its bounding box), strongest first.
  const events = useMemo(() => {
    const inside = (list?.data ?? []).filter((e) => !aoi || aoiContains(aoi, e.centroid_lat, e.centroid_lon));
    return inside.sort((a, b) => peak(b) - peak(a));
  }, [list, aoi]);

  const footprints = useMemo(() => ({
    type: "FeatureCollection" as const,
    features: events.filter((e) => e.footprint).map((e) => ({ type: "Feature" as const, geometry: e.footprint!, properties: { fire_id: e.fire_id, cls: classOf(e) } })),
  }), [events, classOf]);

  const placeOutline = useMemo(() => {
    if (!aoi) return null;
    if (aoi.geometry) return { type: "Feature" as const, geometry: aoi.geometry as GeoJSON.Geometry, properties: {} };
    if (!box) return null;
    const [w, s, e, n] = box;
    return { type: "Feature" as const, geometry: { type: "Polygon" as const, coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] }, properties: {} };
  }, [aoi, box]);

  const open = useCallback(async (fireId: string) => {
    try {
      const r = await snapshotGet<SnapshotMeta & { data: HarmonizedEvent }>(`/events/${encodeURIComponent(fireId)}`, { window: win });
      setSelected(r.data);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [win]);

  const legend = useMemo(() => {
    const local = (site?.translation.words[lang]?.intensity as string[] | undefined) ?? [];
    const th = thresholds;
    const ranges = th.length === 3 ? [`< ${th[0]} MW`, `${th[0]}–${th[1]} MW`, `${th[1]}–${th[2]} MW`, `≥ ${th[2]} MW`] : [];
    return local.map((w, i) => ({ w, range: ranges[i] ?? "", c: INTENSITY_HEX[i] }));
  }, [site, lang, thresholds]);

  const tr = selected?.translation?.[lang] as Record<string, string | string[]> | undefined;

  if (!aoi || !box) {
    return (
      <main className="content-page space-shell space-page">
        <div className="space-hero-strip">
          <div className="space-hero-orbit" aria-hidden="true"><span /><span /></div>
          <header className="nasa-page-intro">
            <p className="eyebrow"><span className="dot" /> Harmonized record</p>
            <h2>{t("map_title")}</h2>
            <p className="lead">{t("pick_place")}</p>
            <Link to="/search" className="oc-btn-primary hz-cta">{t("go_search")} →</Link>
          </header>
        </div>
      </main>
    );
  }

  return (
    <main className="content-page space-shell space-page">
      <div className="space-hero-strip">
        <div className="space-hero-orbit" aria-hidden="true"><span /><span /></div>
        <header className="nasa-page-intro">
          <p className="eyebrow"><span className="dot" /> {t("fire_events_in")}</p>
          <h2>{describeAoi(aoi)}</h2>
          <p className="lead">{t("map_lead")}</p>
          <div className="hz-hero-actions">
            <Link to="/search" className="hz-link-btn">{t("change_place")}</Link>
          </div>
          <HarmonizedProvenance window={win} />
        </header>
      </div>

      <div className="hz-map-layout">
        <div className="hz-map-frame">
          <MapContainer center={[(box[1] + box[3]) / 2, (box[0] + box[2]) / 2]} zoom={6} preferCanvas scrollWheelZoom>
            <TileLayer attribution="Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics"
              url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" />
            <TileLayer attribution="Labels &copy; Esri"
              url="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}" />
            <Frame box={box} focus={selected?.footprint ?? null} />
            <ZoomWatcher onZoom={setZoom} />
            {placeOutline && (
              <GeoJSON key={`aoi-${describeAoi(aoi)}`} data={placeOutline} interactive={false}
                style={{ color: "#6ad7ff", weight: 2, dashArray: "6 5", fill: false }} />
            )}
            <GeoJSON
              key={`fp-${win}-${events.length}-${events[0]?.fire_id ?? ""}-${selected?.fire_id ?? ""}-${small}`}
              data={footprints}
              style={(f) => {
                const isSel = f?.properties?.fire_id === selected?.fire_id;
                const fill = colourOf(f?.properties?.cls ?? -1);
                return {
                  color: isSel ? "#6ad7ff" : small ? fill : "#ffffff",
                  weight: isSel ? 3 : small ? 9 : 1.4,
                  lineJoin: "round" as const,
                  fillColor: fill, fillOpacity: 0.9,
                };
              }}
              onEachFeature={(f, layer) => {
                const e = events.find((x) => x.fire_id === f.properties.fire_id);
                if (e) layer.bindTooltip(`${String(e.translation?.[lang]?.intensity ?? "")} · ${e.end_time.slice(0, 10)}`, { sticky: true });
                layer.on("click", () => open(f.properties.fire_id));
              }}
            />
          </MapContainer>
          <div className="hz-honesty hz-honesty-float" role="note">
            <strong>{t("honesty_title")}</strong>
            <ul><li>{t("honesty_1")}</li><li>{t("honesty_2")}</li></ul>
          </div>
        </div>

        <aside className="glass-card hz-side">
          <div>
            <label htmlFor="hz-win">{t("map_window")}</label>
            <select id="hz-win" value={win} onChange={(e) => setWin(e.target.value)}>
              {Object.keys(site?.meta.windows ?? { current_2026: 1 }).map((w) => <option key={w} value={w}>{w}</option>)}
            </select>
          </div>

          <div className="hz-count">
            {loading && <span>{t("loading")}</span>}
            {error && <span style={{ color: "var(--sp-warn)" }}>{t("error")}: {error}</span>}
            {list && !loading && <><b>{fmt(events.length)} {t("events_found")}</b> — {t("window_basis")}{list.count > list.data.length ? ` (${t("first")} ${fmt(list.data.length)} ${t("map_of")} ${fmt(list.count)})` : ""}</>}
          </div>

          {selected && tr ? (
            <div className="hz-panel glass-card" style={{ padding: 14 }} aria-live="polite">
              <div className="hz-panel-head"><span>{selected.fire_id}</span><button className="hz-link-btn" onClick={() => setSelected(null)}>{t("back_to_list")}</button></div>
              <dl>
                <dt>{t("p_int")}</dt><dd>{String(tr.intensity ?? "")}</dd>
                <dt>{t("p_platforms")}</dt><dd>{(selected.platforms_seen ?? "").split(";").filter(Boolean).join(", ") || t("awaiting")}</dd>
                <dt>{t("p_sensor")}</dt><dd>{selected.sensor_flag ?? t("awaiting")}</dd>
                <dt>{t("p_last")}</dt><dd>{String(tr.last_seen ?? "")}</dd>
                <dt>{t("p_conf")}</dt><dd>{String(tr.confidence ?? "")}</dd>
                <dt>{t("p_trend")}</dt><dd>{String(tr.trend ?? "")}</dd>
                <dt>{t("p_frp_modis")}</dt><dd>{selected.FRP_MODIS_max != null ? `${fmt(selected.FRP_MODIS_max, 1)} MW` : t("awaiting")}</dd>
                <dt>{t("p_frp_viirs")}</dt><dd>{selected.FRP_VIIRS_max != null ? `${fmt(selected.FRP_VIIRS_max, 1)} MW` : t("awaiting")}</dd>
                <dt>{t("p_area")}</dt><dd>{selected.footprint_area_km2 != null ? `${fmt(selected.footprint_area_km2, 2)} km²` : t("awaiting")}</dd>
                <dt>{t("p_start")}</dt><dd>{selected.start_time}</dd>
                <dt>{t("p_end")}</dt><dd>{selected.end_time}</dd>
              </dl>
              <ul className="hz-list" style={{ fontSize: 12, marginTop: 8, color: "var(--sp-text-dim)" }}>
                {((tr.honesty_notes as string[]) ?? []).map((n) => <li key={n}>{n}</li>)}
              </ul>
              <div style={{ marginTop: 8 }}><StatusPill status={String(tr.status ?? "provisional")} /></div>
            </div>
          ) : (
            <div>
              <label>{t("event_list")}</label>
              {!loading && events.length === 0 && <p className="hz-count">{t("no_events")}</p>}
              <div className="hz-event-list">
                {events.slice(0, 200).map((e) => {
                  const p = peak(e);
                  return (
                    <button key={e.fire_id} className="hz-event-row" onClick={() => open(e.fire_id)}>
                      <span className="hz-sw" style={{ background: colourOf(classOf(e)) }} aria-hidden="true" />
                      <span>
                        <strong>{String(e.translation?.[lang]?.intensity ?? t("awaiting"))}</strong>
                        <small>{e.end_time.slice(0, 16).replace("T", " ")} UTC · {(e.platforms_seen ?? "").split(";").filter(Boolean).join(", ")}</small>
                      </span>
                      <em>{p >= 0 ? `${fmt(p, 1)} MW` : "—"}</em>
                    </button>
                  );
                })}
              </div>
              {events.length > 200 && <p className="hz-src">{t("list_capped")}</p>}
            </div>
          )}

          <div>
            <label>{t("legend")}</label>
            <div className="hz-legend">
              {legend.map((l) => <span key={l.w}><span className="hz-sw" style={{ background: l.c }} />{l.w} ({l.range})</span>)}
              <span><span className="hz-sw" style={{ background: UNKNOWN_HEX }} />{t("awaiting")}</span>
              <span><span className="hz-sw" style={{ background: "transparent", borderColor: "#6ad7ff", borderStyle: "dashed" }} />{t("place_outline")}</span>
            </div>
            <p className="hz-src">{t("shape_note")}</p>
          </div>
        </aside>
      </div>
    </main>
  );
}
