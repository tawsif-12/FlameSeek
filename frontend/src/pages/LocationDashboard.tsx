import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { Link, NavLink, Navigate, useLocation, useNavigate, useParams } from 'react-router-dom';
import { Activity, CalendarDays, ChevronLeft, ChevronRight, Dna, Flame, Info, MapPin, Menu, X } from 'lucide-react';
import { areaFromUrl, dashboardUrl, locationId, LOCATION_SECTIONS, type LocationSection } from '../api/locationRoutes';
import { describeAoi, LocationAreaScope, useAppContext } from '../context/AppContext';
import '../location-dashboard.css';
import { resolvePlace } from '../api/client';

const FEATURES = {
  intelligence: lazy(() => import('./AreaIntelligencePage')),
  now: lazy(() => import('./FireGlobePage')),
  dna: lazy(() => import('./FireDnaPage')),
  calendar: lazy(() => import('./FireMemoryPage')),
};
const ITEMS = [
  { section: 'intelligence', label: 'Fire Intelligence', Icon: Activity },
  { section: 'now', label: 'Fire Now', Icon: Flame },
  { section: 'calendar', label: 'Burning Calendar', Icon: CalendarDays },
  { section: 'dna', label: 'Fire DNA', Icon: Dna },
] as const;

export default function LocationDashboard() {
  const { section = 'intelligence' } = useParams();
  const route = useLocation();
  const navigate = useNavigate();
  const { aoi, setAoi, setMemory } = useAppContext();
  const areaToken = new URLSearchParams(route.search).get('area') || new URLSearchParams(route.hash.replace(/^#/, '')).get('area');
  const area = useMemo(() => areaFromUrl(`?area=${encodeURIComponent(areaToken || '')}`), [areaToken]);
  // Repair old country links created by the point-only 25 km fallback.
  useEffect(() => {
    if (area?.kind !== 'radius' || !area.id?.match(/^geonames:[1-9][0-9]*:radius:25$/)) return;
    const request = new AbortController();
    void resolvePlace(area.id.replace(/:radius:25$/, ''), request.signal).then(place => {
      if (request.signal.aborted || !place?.geometry || !['country', 'administrative'].includes(place.type) && !['country', 'administrative'].includes(place.addresstype)) return;
      const fullArea = { id: place.place_id, geometry: place.geometry, bbox: place.bbox, name: place.place_name || place.name, kind: 'place' as const };
      navigate(dashboardUrl(fullArea, LOCATION_SECTIONS.includes(section as LocationSection) ? section as LocationSection : 'intelligence'), { replace: true });
    }).catch(() => { /* Existing area remains usable; selection can be retried. */ });
    return () => request.abort();
  }, [area, navigate, section]);
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem('flameseek.sidebar.collapsed') === '1'; } catch { return false; } });
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 900px)').matches);
  const [drawer, setDrawer] = useState(false);
  const sidebar = useRef<HTMLElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const closeDrawer = () => { setDrawer(false); toggle.current?.focus(); };
  useEffect(() => {
    const media = window.matchMedia('(max-width: 900px)');
    const update = () => { setMobile(media.matches); setDrawer(false); };
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => { try { localStorage.setItem('flameseek.sidebar.collapsed', collapsed ? '1' : '0'); } catch { /* Optional preference. */ } }, [collapsed]);
  useEffect(() => { window.dispatchEvent(new Event('resize')); }, [collapsed]);
  useEffect(() => { setDrawer(false); }, [route.pathname, areaToken]);
  useEffect(() => {
    if (area && JSON.stringify(aoi) !== JSON.stringify(area)) { setMemory(null); setAoi(area); }
  }, [area, aoi, setAoi, setMemory]);
  useEffect(() => {
    if (!drawer || !mobile) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    sidebar.current?.querySelector<HTMLElement>('[aria-current="page"]')?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); closeDrawer(); }
      if (event.key === 'Tab') {
        const controls = sidebar.current?.querySelectorAll<HTMLElement>('button:not([hidden]),a[href]');
        if (!controls?.length) return;
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => { document.body.style.overflow = previousOverflow; document.removeEventListener('keydown', onKey); };
  }, [drawer, mobile]);

  if (!area) return <main className="content-page"><h2>Choose a location</h2><p>This link does not contain a usable area boundary.</p><Link to="/search">Explore locations</Link></main>;
  if (route.pathname === '/location') return <Navigate replace to={dashboardUrl(area)} />;
  if (section === 'memory' || section === 'events') {
    return <Navigate replace to={dashboardUrl(area, section, Object.fromEntries(new URLSearchParams(route.search)))} />;
  }
  if (!LOCATION_SECTIONS.includes(section as LocationSection)) return <Navigate replace to={dashboardUrl(area)} />;
  const selectedSection = section as LocationSection;
  const Feature = FEATURES[selectedSection];
  const name = describeAoi(area);
  const ready = JSON.stringify(aoi) === JSON.stringify(area);
  const id = locationId(area);
  return <div className={`location-dashboard${collapsed ? ' sidebar-collapsed' : ''}`} data-location-id={id}>
    <div className="location-mobile-bar"><button ref={toggle} type="button" aria-label="Open location navigation" aria-controls="location-sidebar" aria-expanded={drawer} onClick={() => setDrawer(true)}><Menu aria-hidden="true" size={20} /></button><span>{name}</span><strong>{ITEMS.find(item => item.section === section)?.label}</strong></div>
    {mobile && drawer && <button className="location-drawer-backdrop" type="button" aria-label="Close location navigation" onClick={closeDrawer} />}
    <aside ref={sidebar} id="location-sidebar" className={`location-sidebar${drawer ? ' drawer-open' : ''}`} hidden={mobile && !drawer} role={mobile && drawer ? 'dialog' : undefined} aria-modal={mobile && drawer ? true : undefined} aria-label="Location navigation">
      <div className="location-sidebar-top"><span className="location-sidebar-label">LOCATION WORKSPACE</span>{mobile ? <button type="button" aria-label="Close location navigation" onClick={closeDrawer}><X size={20} aria-hidden="true" /></button> : <button type="button" aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} onClick={() => setCollapsed(value => !value)}>{collapsed ? <ChevronRight size={20} aria-hidden="true" /> : <ChevronLeft size={20} aria-hidden="true" />}</button>}</div>
      <div className="location-identity" title={name}><MapPin size={20} aria-hidden="true" /><div className="location-sidebar-label"><span>Selected location</span><h2>{name}</h2></div></div>
      <button type="button" className="location-change" title="Change location" aria-label="Change location" onClick={() => { setMemory(null); setAoi(null); navigate('/search'); }}><MapPin size={16} aria-hidden="true" /><span className="location-sidebar-label">Change Location</span></button>
      <nav aria-label="Location sections">{ITEMS.map(({ section: destination, label, Icon }) => <NavLink key={destination} to={dashboardUrl(area, destination)} aria-label={label} title={label} onClick={() => mobile && closeDrawer()}><Icon size={20} aria-hidden="true" /><span className="location-sidebar-label">{label}</span></NavLink>)}</nav>
      <footer className="location-sidebar-foot"><Info size={16} aria-hidden="true" /><p>Satellite observations are evidence. Missing coverage is not a confirmed absence of fire.</p></footer>
    </aside>
    <div className="location-content" data-section={selectedSection}>
      {ready ? <LocationAreaScope key={JSON.stringify(area)} area={area}><Suspense fallback={<div className="location-loading" role="status">Loading {ITEMS.find(item => item.section === section)?.label} for {name}…</div>}><Feature key={`${id}:${selectedSection}`} /></Suspense></LocationAreaScope> : <div className="location-loading" role="status">Loading the boundary for {name}…</div>}
    </div>
  </div>;
}
