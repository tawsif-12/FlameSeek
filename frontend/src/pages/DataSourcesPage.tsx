import { useEffect, useState } from "react";
import { getDataSources } from "../api/client";
import type { DataSource } from "../types/api";

export default function DataSourcesPage() {
  const [sources, setSources] = useState<DataSource[]>([]);

  useEffect(() => {
    getDataSources().then(setSources).catch(() => setSources([]));
  }, []);

  return (
    <main className="content-page">
      <p className="eyebrow">FIRMS, MODIS, VIIRS, Worldview</p>
      <h2>Data Sources</h2>
      <p className="lead">
        Active fire detections come from NASA FIRMS and are harmonized across MODIS and VIIRS before calendar statistics are shown.
      </p>
      <section className="source-grid">
        {sources.map((source) => (
          <article key={source.name} className="source-card">
            <h3>{source.name}</h3>
            <p>{source.description}</p>
            <a href={source.url} target="_blank" rel="noreferrer">
              Visit source
            </a>
            <span>Verified {source.last_verified}</span>
          </article>
        ))}
      </section>
    </main>
  );
}

