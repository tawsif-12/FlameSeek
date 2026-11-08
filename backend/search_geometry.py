"""Prepared polygon interiors with legacy ray-casting boundary semantics."""
import json
import math
from functools import lru_cache

from geo import haversine_km, point_in_polygons


@lru_cache(maxsize=32)
def prepared_polygons(encoded):
    from shapely.geometry import Polygon
    from shapely.prepared import prep
    polygons=json.loads(encoded);result=[]
    for rings in polygons:
        polygon=Polygon([p[:2] for p in rings[0]],[[p[:2] for p in ring] for ring in rings[1:]])
        # Legacy validation accepts self-intersections: retain ray casting for them.
        if not polygon.is_valid:
            result.append((polygon.bounds,rings,None,None));continue
        # A tiny boundary neighborhood preserves original floating point edge decisions.
        edge=polygon.boundary.buffer(1e-10)
        result.append((polygon.bounds,rings,prep(polygon),prep(edge)))
    return result


class PreparedArea:
    def __init__(self,area):
        self.original=area;self.bbox=self._candidate_box(area)
        self.polygons=prepared_polygons(json.dumps(area.polygons,separators=(',',':'))) if area.polygons else []

    @staticmethod
    def _candidate_box(area):
        w,s,e,n=area.bbox
        if area.center:
            lon,lat=area.center
            # Same Earth radius as the authoritative haversine implementation.
            angular=area.radius_km/6371.0088
            south=max(-90,lat-math.degrees(angular));north=min(90,lat+math.degrees(angular))
            if south<=-90 or north>=90:west,east=-180,180
            else:
                delta=math.degrees(math.asin(min(1,math.sin(angular)/math.cos(math.radians(lat)))))
                west,east=lon-delta,lon+delta
                # A wrapping circle still gets exact haversine checks on the original box.
                if west< -180 or east>180:west,east=-180,180
            # Expand by a tiny amount for double precision on exact circle boundaries.
            w,s,e,n=max(w,west-1e-9),max(s,south-1e-9),min(e,east+1e-9),min(n,north+1e-9)
        return w,s,e,n

    def contains(self,lat,lon):
        if lon is None or lat is None:return False
        w,s,e,n=self.original.bbox
        if not (w<=lon<=e and s<=lat<=n):return False
        area=self.original
        if area.center and haversine_km(lat,lon,area.center[1],area.center[0])>area.radius_km:return False
        if not self.polygons:return True
        from shapely.geometry import Point
        point=None
        for (w,s,e,n),rings,prepared,edge in self.polygons:
            if not (w<=lon<=e and s<=lat<=n):continue
            if prepared is None:
                if point_in_polygons(lon,lat,[rings]):return True
                continue
            if point is None:point=Point(lon,lat)
            if edge.intersects(point):
                if point_in_polygons(lon,lat,[rings]):return True
            elif prepared.contains(point):return True
        return False
