import { createContext, ReactNode, useContext, useEffect, useState } from "react";

export type Lang = "en" | "bn";

/* English / Bangla strings for the harmonized-record pages. Fire descriptions (intensity,
   confidence, trend, honesty notes) come from the pipeline translation layer via the API.
   Bangla interface strings are a first draft for native-speaker review. */
const STRINGS = {
  en: {
    toggle: "বাংলা",
    nav_events: "Fire Events", nav_method: "Methodology", nav_about: "About",
    window: "Window", data_version: "Data version", last_obs: "Last observation", api_offline: "API offline — from exported snapshot manifest",
    awaiting: "awaiting data",
    record_tag: "HARMONIZED RECORD",
    record_title: "One Fire Record From Five Satellites",
    record_desc: "Raw satellite detections are quality-checked, given their true ground footprint, and grouped into fire events. Every number below is read from the pipeline's own outputs.",
    events_in_window: "fire events in the current window",
    window_utc: "Window (UTC)", updated: "Last updated (last satellite observation)",
    raw_to_events: "From raw detections to fire events",
    card_map: "Live 3D globe of fires seen by satellites. To see the harmonized fire events of a place, use Search.",
    card_method: "How the record is built, how it was validated, and what is still missing.",
    card_about: "The team behind FlameSeek.",
    open: "Open",
    map_title: "Harmonized Fire Events",
    map_lead: "Every fire event the satellites recorded in this place during the window, drawn as its true burned-ground outline. Pick one from the list to zoom to it.",
    pick_place: "Fire events are shown for a place. Search for a country, district or forest first, then choose “Fire Events”.",
    go_search: "Search a place", fire_events_in: "Fire events in", change_place: "← Change place",
    events_found: "fire events in this place", window_basis: "all events recorded in the window", first: "showing first",
    back_to_list: "← Back to list", event_list: "Events (strongest first)", no_events: "No fire events were recorded in this place during the window. That does not mean there was no fire (clouds and gaps hide fires).",
    list_capped: "Showing the 200 strongest; all are drawn on the map.", place_outline: "Searched place",
    shape_note: "Each coloured shape is one fire event: the ground covered by its satellite pixels. Zoomed out, small fires are drawn with a thick border so they stay visible; zoom in to see the true shape. Hover for its name, click for details.",
    map_window: "Window", map_show: "Show", map_events: "Events (footprints)", map_raw: "Raw detections (points)", map_region: "Region",
    map_showing: "Showing", map_of: "of",
    map_active_basis: "events whose last detection is in the final 24 h of the window",
    map_raw_basis: "quality-filtered detections in the final 24 h of the window",
    map_zoom: "Zoom in to level 9 or more to see true footprints; markers show events at smaller scales.",
    honesty_title: "Read this first",
    honesty_1: "Not real time: an offline snapshot ending at the window end above.",
    honesty_2: "No fire shown does not mean no fire: clouds, smoke and gaps between satellite passes hide fires.",
    legend: "Observed intensity (fire radiative power)",
    p_platforms: "Seen by", p_sensor: "Sensors", p_last: "Last seen", p_conf: "Confidence", p_int: "Intensity", p_trend: "Trend",
    p_frp_modis: "Max MODIS FRP in one overpass", p_frp_viirs: "Max VIIRS FRP in one overpass", p_area: "Footprint area",
    p_start: "First detection", p_end: "Last detection", close: "Close", loading: "Loading…", error: "Could not load",
  },
  bn: {
    toggle: "EN",
    nav_events: "আগুনের ঘটনা", nav_method: "পদ্ধতি", nav_about: "আমাদের সম্পর্কে",
    window: "সময়সীমা", data_version: "ডেটা সংস্করণ", last_obs: "সর্বশেষ পর্যবেক্ষণ", api_offline: "API বন্ধ — রপ্তানিকৃত স্ন্যাপশট থেকে",
    awaiting: "তথ্য আসার অপেক্ষায়",
    record_tag: "সমন্বিত রেকর্ড",
    record_title: "পাঁচটি উপগ্রহ থেকে একটি আগুনের রেকর্ড",
    record_desc: "উপগ্রহের কাঁচা শনাক্তকরণ যাচাই করে, প্রকৃত এলাকা দিয়ে, আগুনের ঘটনায় সাজানো হয়। নিচের প্রতিটি সংখ্যা পাইপলাইনের নিজস্ব ফলাফল থেকে নেওয়া।",
    events_in_window: "টি আগুনের ঘটনা, বর্তমান সময়সীমায়",
    window_utc: "সময়সীমা (UTC)", updated: "সর্বশেষ হালনাগাদ (শেষ উপগ্রহ পর্যবেক্ষণ)",
    raw_to_events: "কাঁচা শনাক্তকরণ থেকে আগুনের ঘটনা",
    card_map: "উপগ্রহে দেখা আগুনের লাইভ ৩ডি গ্লোব। কোনো এলাকার সমন্বিত আগুনের ঘটনা দেখতে Search ব্যবহার করুন।",
    card_method: "রেকর্ড কীভাবে তৈরি ও যাচাই হয়েছে, আর কী বাকি।",
    card_about: "FlameSeek-এর পেছনের দল।",
    open: "খুলুন",
    map_title: "সমন্বিত আগুনের ঘটনা",
    map_lead: "এই এলাকায় সময়সীমার মধ্যে উপগ্রহে ধরা পড়া প্রতিটি আগুনের ঘটনা, প্রকৃত পোড়া এলাকার সীমানাসহ। তালিকা থেকে একটি বেছে নিলে মানচিত্র সেখানে যাবে।",
    pick_place: "আগুনের ঘটনা একটি এলাকার জন্য দেখানো হয়। আগে একটি দেশ, জেলা বা বন খুঁজুন, তারপর “আগুনের ঘটনা” বেছে নিন।",
    go_search: "এলাকা খুঁজুন", fire_events_in: "আগুনের ঘটনা:", change_place: "← এলাকা বদলান",
    events_found: "টি আগুনের ঘটনা এই এলাকায়", window_basis: "সময়সীমায় রেকর্ড হওয়া সব ঘটনা", first: "প্রথম",
    back_to_list: "← তালিকায় ফিরুন", event_list: "ঘটনা (শক্তিশালী আগে)", no_events: "এই সময়সীমায় এই এলাকায় কোনো আগুনের ঘটনা রেকর্ড হয়নি। এর মানে আগুন ছিল না এমন নয় (মেঘ ও বিরতিতে আগুন আড়াল হয়)।",
    list_capped: "শক্তিশালী ২০০টি দেখানো হচ্ছে; মানচিত্রে সবগুলো আঁকা আছে।", place_outline: "খোঁজা এলাকা",
    shape_note: "প্রতিটি রঙিন আকৃতি একটি আগুনের ঘটনা: উপগ্রহের পিক্সেল যে মাটি ঢেকেছে। দূর থেকে ছোট আগুন মোটা সীমারেখায় আঁকা হয় যাতে দেখা যায়; প্রকৃত আকৃতি দেখতে জুম করুন। নাম দেখতে মাউস রাখুন, বিস্তারিত দেখতে ক্লিক করুন।",
    map_window: "সময়সীমা", map_show: "দেখান", map_events: "ঘটনা (এলাকা)", map_raw: "কাঁচা শনাক্তকরণ (বিন্দু)", map_region: "অঞ্চল",
    map_showing: "দেখানো হচ্ছে", map_of: "এর মধ্যে",
    map_active_basis: "যেসব ঘটনার শেষ শনাক্তকরণ সময়সীমার শেষ ২৪ ঘণ্টায়",
    map_raw_basis: "সময়সীমার শেষ ২৪ ঘণ্টার মান-যাচাইকৃত শনাক্তকরণ",
    map_zoom: "প্রকৃত এলাকা দেখতে ৯ বা তার বেশি জুম করুন; ছোট স্কেলে চিহ্ন দিয়ে ঘটনা দেখানো হয়।",
    honesty_title: "আগে এটি পড়ুন",
    honesty_1: "এটি সরাসরি নয়: উপরের সময়সীমার শেষে থামানো একটি স্ন্যাপশট।",
    honesty_2: "আগুন দেখা না গেলেই আগুন নেই এমন নয়: মেঘ, ধোঁয়া ও উপগ্রহের অনুপস্থিতিতে আগুন আড়াল হতে পারে।",
    legend: "পর্যবেক্ষিত তীব্রতা (আগুনের বিকিরণ শক্তি)",
    p_platforms: "শনাক্ত করেছে", p_sensor: "সেন্সর", p_last: "শেষ দেখা", p_conf: "আস্থা", p_int: "তীব্রতা", p_trend: "প্রবণতা",
    p_frp_modis: "এক পাসে সর্বোচ্চ MODIS FRP", p_frp_viirs: "এক পাসে সর্বোচ্চ VIIRS FRP", p_area: "এলাকার আয়তন",
    p_start: "প্রথম শনাক্তকরণ", p_end: "শেষ শনাক্তকরণ", close: "বন্ধ", loading: "লোড হচ্ছে…", error: "লোড করা যায়নি",
  },
} as const;

export type StringKey = keyof typeof STRINGS.en;

const LanguageContext = createContext<{ lang: Lang; setLang: (l: Lang) => void; t: (k: StringKey) => string; fmt: (n: number, d?: number) => string }>({
  lang: "en", setLang: () => undefined, t: (k) => STRINGS.en[k], fmt: (n) => String(n),
});

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("lang");
    if (fromUrl === "en" || fromUrl === "bn") return fromUrl;
    try {
      return (localStorage.getItem("flameseek-lang") as Lang) || "en";
    } catch {
      return "en";
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem("flameseek-lang", lang);
    } catch {
      /* per-viewer convenience only */
    }
  }, [lang]);
  const t = (k: StringKey) => STRINGS[lang][k];
  const fmt = (n: number, d = 0) =>
    new Intl.NumberFormat(lang === "bn" ? "bn-BD" : "en-US", { maximumFractionDigits: d, minimumFractionDigits: d }).format(n);
  return <LanguageContext.Provider value={{ lang, setLang, t, fmt }}>{children}</LanguageContext.Provider>;
}

export const useLanguage = () => useContext(LanguageContext);
