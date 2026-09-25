import { buildWorldviewUrl } from "../utils/worldview";
import type { BBox } from "../types/api";

export default function WorldviewButton({ date, bbox }: { date: string; bbox: BBox }) {
  return (
    <a className="secondary-button" href={buildWorldviewUrl({ date, bbox })} target="_blank" rel="noreferrer">
      Open in NASA Worldview
    </a>
  );
}

