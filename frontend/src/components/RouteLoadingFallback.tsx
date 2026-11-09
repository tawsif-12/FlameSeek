export default function RouteLoadingFallback({ immersive = false }: { immersive?: boolean }) {
  return (
    <main className={`route-loading ${immersive ? "route-loading--immersive" : "content-page"}`} role="status" aria-live="polite">
      <div className="route-loading__inner">
        <span className="route-loading__orbit" aria-hidden="true"><i /></span>
        <div className="route-loading__copy">
          <span className="route-loading__line route-loading__line--short" />
          <span className="route-loading__line" />
          <span className="route-loading__line route-loading__line--medium" />
        </div>
        <span className="sr-only">Loading page</span>
      </div>
    </main>
  );
}
