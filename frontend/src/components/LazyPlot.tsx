import React, { Suspense, useEffect, useRef, useState } from "react";
import type PlotComponent from "react-plotly.js";

const Plot = React.lazy(() => import("react-plotly.js"));

/** Loads Plotly only when a chart is close to the viewport. */
type PlotProps = React.ComponentProps<typeof PlotComponent>;

export default function LazyPlot(props: PlotProps) {
  const host = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const node = host.current;
    if (!node || visible) return;
    if (!("IntersectionObserver" in window)) {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      setVisible(true);
      observer.disconnect();
    }, { rootMargin: "500px 0px" });
    observer.observe(node);
    return () => observer.disconnect();
  }, [visible]);

  return (
    <div ref={host} className="lazy-plot-host" style={props.style}>
      {visible ? (
        <Suspense fallback={<div className="chart-skeleton" aria-label="Loading chart" role="status" />}>
          <Plot {...props} useResizeHandler={props.useResizeHandler ?? true} style={{ width: "100%", height: "100%", ...props.style }} />
        </Suspense>
      ) : <div className="chart-skeleton" aria-hidden="true" />}
    </div>
  );
}
