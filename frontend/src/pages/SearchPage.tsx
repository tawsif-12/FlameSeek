import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { normalizeApiError, searchPlaces, resolvePlace } from '../api/client';
import { areaFromUrl, dashboardUrl, placeArea } from '../api/locationRoutes';
import AOISelector from '../components/AOISelector';
import { useAppContext } from '../context/AppContext';
import type { AOI, PlaceResult } from '../types/api';
import '../harmonized.css';
import '../search-refinements.css';

export default function SearchPage() {
  const { aoi, setAoi, setMemory } = useAppContext();
  const navigate = useNavigate();
  const route = useLocation();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<PlaceResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [mapOpen, setMapOpen] = useState(false);
  const [point, setPoint] = useState<PlaceResult | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const suggestionTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  function invalidate() { generation.current++; controller.current?.abort(); if (suggestionTimer.current) clearTimeout(suggestionTimer.current); setSearching(false); }
  function openArea(area: AOI) {
    if (!areaFromUrl(`?area=${encodeURIComponent(JSON.stringify(area))}`)) { setError('Draw a valid rectangle, polygon, or circle before opening its dashboard.'); return; }
    invalidate(); setMemory(null); setAoi(area); navigate(dashboardUrl(area));
  }
  async function choose(place: PlaceResult) {
    if (place.requires_resolution && place.place_id) {
      invalidate();
      const id = generation.current;
      const request = new AbortController(); controller.current = request;
      setSearching(true); setError(null); setOpen(false);
      try {
        const resolved = await resolvePlace(place.place_id, request.signal);
        if (id !== generation.current || request.signal.aborted) return;
        place = resolved ?? place;
      } catch (reason) {
        if (id === generation.current && !request.signal.aborted) setError(normalizeApiError(reason));
        return;
      } finally { if (id === generation.current) setSearching(false); }
    }
    const area = placeArea(place);
    if (area) { openArea(area); return; }
    invalidate(); setAoi(null); setPoint(place); setResults([]); setOpen(false);
    setQuery(place.place_name || place.name.split(',')[0]);
  }
  async function search(value = query, fromLink = false, suggest = false) {
    invalidate();
    const name = value.trim();
    if (name.length < 2) { setError('Enter at least two characters.'); return; }
    const id = generation.current;
    const request = new AbortController(); controller.current = request;
    if (!suggest) setQuery(name);
    setSearching(true); setError(null); setResults([]); setOpen(true); setActive(-1); setSearched(true); setPoint(null);
    try {
      const found = await searchPlaces(name, request.signal, suggest);
      if (id !== generation.current || request.signal.aborted) return;
      if (fromLink && found[0]) { choose(found[0]); return; }
      setResults(found);
    } catch (reason) {
      if (id === generation.current && !request.signal.aborted) setError(normalizeApiError(reason));
    } finally { if (id === generation.current) setSearching(false); }
  }
  useEffect(() => {
    setAoi(null); setMemory(null);
    const linked = areaFromUrl(route.search, route.hash);
    if (linked) { openArea(linked); return; }
    const params = new URLSearchParams(route.search);
    const name = params.get('place') || params.get('location');
    if (name) void search(name, true);
    return () => { generation.current++; controller.current?.abort(); };
  }, [route.search, route.hash]);
  useEffect(() => () => { generation.current++; controller.current?.abort(); if (suggestionTimer.current) clearTimeout(suggestionTimer.current); }, []);
  useEffect(() => { if (active >= 0) document.getElementById(`explore-place-${active}`)?.scrollIntoView({ block: 'nearest' }); }, [active]);

  return <main className="minimal-search-page">
    <section className="minimal-search-stage" aria-labelledby="search-page-title">
      <div className="minimal-search-heading"><p>FlameSeek Explore</p><h2 id="search-page-title">Find a place.<br />Explore its fire story.</h2><span>Describe a place or ask about fires there to find its dashboard.</span></div>
      <div className="minimal-search-workspace">
        <form aria-busy={searching} className="minimal-search-box explore-search-box" onSubmit={event => { event.preventDefault(); void search(); }}>
          <span aria-hidden="true">⌕</span>
          <input ref={input} autoFocus value={query} placeholder={'Try fires in Bangladesh or Sundarbans forest'} aria-label="Search for a location" role="combobox" aria-autocomplete="list" aria-expanded={open && results.length > 0} aria-controls="explore-places" aria-activedescendant={open && active >= 0 ? `explore-place-${active}` : undefined} aria-describedby="search-guidance"
            onChange={event => { const value = event.target.value; invalidate(); setAoi(null); setQuery(value); setResults([]); setOpen(false); setActive(-1); setError(null); setSearched(false); setPoint(null); if (value.trim().length >= 2) { setSearching(true); setOpen(true); suggestionTimer.current = setTimeout(() => void search(value, false, true), 150); } }}
            onKeyDown={event => {
              if (event.key === 'Escape') { event.preventDefault(); invalidate(); setOpen(false); setActive(-1); }
              if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && results.length) { event.preventDefault(); setOpen(true); setActive(index => event.key === 'ArrowDown' ? (index + 1) % results.length : (index < 0 ? results.length - 1 : (index - 1 + results.length) % results.length)); }
              if (event.key === 'Enter' && open && active >= 0) { event.preventDefault(); choose(results[active]); }
            }} />
          {!!query && <button type="button" className="explore-clear" aria-label="Clear location search" onClick={() => { invalidate(); setAoi(null); setMapOpen(false); setQuery(''); setResults([]); setPoint(null); setError(null); setSearched(false); setOpen(false); input.current?.focus(); }}>×</button>}
          <button type="submit">Search</button>
        </form>
        <p id="search-guidance" className="search-guidance">Live suggestions appear as you type. Use the arrow keys and Enter to choose a location.</p>
        <p className="search-attribution">Place suggestions from <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> via <a href="https://photon.komoot.io" target="_blank" rel="noreferrer">Photon</a>.</p>
        <button className="explore-map-button" type="button" onClick={() => { setMapOpen(true); if (!mapOpen) setAoi(null); }}>Select an area on the map</button>
        {searching && <p className="search-status" role="status">Finding matching locations…</p>}
        {error && <div className="minimal-search-error" role="alert">{error} <button type="button" onClick={() => void search()}>Retry search</button></div>}
        {!searching && searched && !error && !results.length && open && <p className="search-status" role="status">No results for “{query}”. Try another spelling or include the district or country.</p>}
        {open && !!results.length && <ul id="explore-places" className="minimal-place-results explore-place-results" role="listbox" aria-label="Matching locations">{results.map((place, index) => <li id={`explore-place-${index}`} key={`${place.place_id || place.name}-${place.center}`} role="option" aria-selected={index === active}><button type="button" onClick={() => choose(place)} onMouseEnter={() => setActive(index)}><span><strong>{place.place_name || place.name.split(',')[0]}</strong><small>{place.parent_region || place.name.split(',').slice(1).join(', ')}</small>{place.names?.['name:bn'] && <small lang="bn">{place.names['name:bn']}</small>}</span><em>{(place.addresstype || place.type || 'place').replace(/_/g, ' ')}</em></button></li>)}</ul>}
        {point && <p className="search-status" role="status">Only a point was found for {point.place_name || point.name.split(',')[0]}. Select an area on the map to define its boundary.</p>}
        {mapOpen && <section className="explore-map-panel" aria-label="Custom area boundary"><h3>Draw a rectangle, polygon, or circle</h3><AOISelector key={point?.center.join(',') || 'custom'} mapOnly initialCenter={point?.center} /><button type="button" className="primary-button" disabled={!aoi} onClick={() => aoi && openArea(aoi)}>Open location dashboard</button></section>}
      </div>
    </section>
  </main>;
}
