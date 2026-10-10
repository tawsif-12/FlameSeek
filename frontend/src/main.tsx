import React from "react";
import ReactDOM from "react-dom/client";
import { Navigate, Route, BrowserRouter as Router, Routes } from "react-router-dom";
import "./demo/demo.css";
import { Shell } from "./demo/ui";
import Overview from "./demo/pages/Overview";
import { AreaOfInterest, FireNowGlobe, ObservationQuality } from "./demo/pages/FireNow";
import { Anomaly, BurningCalendar } from "./demo/pages/FireMemory";
import FireIdentity from "./demo/pages/FireIdentity";
import { EvidenceFusion, EvidenceNews, EvidenceSources, FireCase } from "./demo/pages/FireEvidence";
import { Exposure, FireFuture, FirePast } from "./demo/pages/Outlook";
import { Harmonization, Workflow } from "./demo/pages/Methods";

// Demo build: every screen under ./demo runs on scripted, illustrative data and makes no API calls.
// The live pages (./pages, ./components) are kept in the tree but are not routed.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Router>
      <Routes>
        <Route element={<Shell />}>
          <Route path="/" element={<Overview />} />
          <Route path="/fire-memory" element={<BurningCalendar />} />
          <Route path="/fire-memory/anomaly" element={<Anomaly />} />
          <Route path="/fire-now" element={<FireNowGlobe />} />
          <Route path="/fire-now/area" element={<AreaOfInterest />} />
          <Route path="/fire-now/quality" element={<ObservationQuality />} />
          <Route path="/fire-identity" element={<FireIdentity />} />
          <Route path="/fire-evidence" element={<EvidenceSources />} />
          <Route path="/fire-evidence/news" element={<EvidenceNews />} />
          <Route path="/fire-evidence/fusion" element={<EvidenceFusion />} />
          <Route path="/fire-evidence/case" element={<FireCase />} />
          <Route path="/fire-past" element={<FirePast />} />
          <Route path="/fire-future" element={<FireFuture />} />
          <Route path="/exposure" element={<Exposure />} />
          <Route path="/methods" element={<Workflow />} />
          <Route path="/methods/harmonization" element={<Harmonization />} />
          <Route path="/fire-map" element={<Navigate to="/fire-now" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Router>
  </React.StrictMode>,
);
