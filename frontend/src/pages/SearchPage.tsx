import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { normalizeApiError, searchPlaces } from "../api/client";
import { describeAoi, useAppContext } from "../context/AppContext";
import type { PlaceResult } from "../types/api";
import "../harmonized.css";
import "../search-refinements.css";

const SUGGESTIONS = ["Bangladesh", "California", "Amazon Rainforest", "New South Wales"];

const DESTINATIONS = [
  { to: "/fire-map?aoi=1", number: "01", title: "Fire Now", description: "Explore recent satellite detections in the selected area." },
  { to: "/fire-memory", number: "02", title: "Fire Memory", description: "Explore the area's long-term fire history and recurring patterns." },
  { to: "/fire-dna", number: "03", title: "Fire DNA", description: "Reveal its seasonal signature, trends, and unusual activity." },
  { to: "/fire-calendar", number: "04", title: "Burning Calendar", description: "See when burning activity typically rises and falls through the year." },
  { to: "/fire-events", number: "05", title: "Fire Events", description: "See each recent fire event in the area as its true burned-ground outline." },
] as const;

export default function SearchPage() {
  const { aoi, setAoi, setMemory } = useAppContext();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PlaceResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDestinations, setShowDestinations] = useState(Boolean(aoi));
  const requestRef = useRef(0);

  async function findPlaces(value = query) {
    const trimmed = value.trim();
    if (trimmed.length < 2) { setError("Enter at least two characters, then select Search."); return; }
    const request = ++requestRef.current;
    setQuery(trimmed);
    setSearching(true);
    setError(null);
    setResults([]);
    try {
      const found = await searchPlaces(trimmed);
      if (request !== requestRef.current) return;
      setResults(found);
      if (!found.length) setError(`No area matched “${trimmed}”. Try a city, district, state, country, forest, or protected area.`);
    } catch (reason) {
      if (request === requestRef.current) setError(normalizeApiError(reason));
    } finally {
      if (request === requestRef.current) setSearching(false);
    }
  }

  function chooseArea(place: PlaceResult) {
    const selected = place.geometry
      ? { geometry: place.geometry, bbox: place.bbox, name: place.name.split(",").slice(0, 2).join(","), kind: "place" as const }
      : { bbox: place.bbox, name: place.name, kind: "place" as const };
    setAoi(selected);
    setMemory(null);
    setQuery(place.name.split(",").slice(0, 2).join(","));
    setResults([]);
    setError(null);
    setShowDestinations(true);
  }

  function resetSelection() {
    setAoi(null);
    setMemory(null);
    setQuery("");
    setResults([]);
    setError(null);
    setShowDestinations(false);
  }

  return (
    <main className="minimal-search-page">
      <section className="minimal-search-stage" aria-labelledby="search-page-title">
        <div className="minimal-search-heading">
          <p>FlameSeek area intelligence</p>
          <h2 id="search-page-title">Search any area.<br />Understand its fire story.</h2>
          <span>Choose a precise location, then decide what you want to explore.</span>
        </div>

        <div className="minimal-search-workspace">
          <form className="minimal-search-box" onSubmit={(event) => { event.preventDefault(); void findPlaces(); }}>
            <span aria-hidden="true">⌕</span>
            <input aria-describedby="search-guidance" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search a country, state, district, or forest" aria-label="Search for a specific area" autoFocus />
            <button type="submit" disabled={searching} aria-label={searching ? "Searching for matching areas" : "Search for matching areas"}>{searching ? <i className="search-spinner" /> : "Search"}</button>
          </form>

          <p id="search-guidance" className="search-guidance">Enter a place name and press Search, then choose a matching result. For a custom boundary, <Link to="/fire-memory">select an area on the map</Link>.</p>
          {error && <p className="minimal-search-error" role="alert">{error}</p>}
          {searching && <p className="search-status" role="status">Finding matching locations?</p>}

          {results.length > 0 && (
            <div className="minimal-place-results" role="group" aria-label="Matching areas">
              {results.map((place) => (
                <button key={`${place.name}-${place.center.join(",")}`} type="button" onClick={() => chooseArea(place)}>
                  <span aria-hidden="true">⌖</span>
                  <span><strong>{place.name.split(",")[0]}</strong><small>{place.name.split(",").slice(1, 4).join(",") || place.addresstype}</small></span>
                  <em>{(place.addresstype || place.type).replace(/_/g, " ")}</em>
                </button>
              ))}
            </div>
          )}

          {!showDestinations && !searching && results.length === 0 && (
            <div className="minimal-search-suggestions" aria-label="Suggested areas">
              {SUGGESTIONS.map((suggestion) => <button type="button" key={suggestion} aria-pressed={query === suggestion} onClick={() => void findPlaces(suggestion)}>{suggestion}</button>)}
            </div>
          )}

          {showDestinations && aoi && results.length === 0 && (
            <section className="area-destinations" aria-labelledby="selected-area-title">
              <header>
                <div><small>Selected area</small><h3 id="selected-area-title">{describeAoi(aoi)}</h3></div>
                <button type="button" onClick={resetSelection}>Change area</button>
              </header>
              <Link to="/area" className="hz-open-intel">
                <span><strong>{describeAoi(aoi).split(",")[0]} Fire Intelligence</strong><small>Fire history · Current activity · Seasonal patterns · Future risk — all in one place</small></span>
                <b aria-hidden="true">→</b>
              </Link>
              <p>Or explore in depth:</p>
              <div>
                {DESTINATIONS.map((destination) => (
                  <Link to={destination.to} key={destination.to}>
                    <span>{destination.number}</span><h4>{destination.title}</h4><p>{destination.description}</p><b aria-hidden="true">→</b>
                  </Link>
                ))}
              </div>
            </section>
          )}
        </div>
      </section>
    </main>
  );
}
