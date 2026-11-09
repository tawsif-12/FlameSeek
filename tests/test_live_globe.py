"""Check procedure merging and power semantics at the live-globe boundary."""
import unittest
import networkx as nx
import numpy as np
import pandas as pd
from pipeline.live_globe import harmonize
from pipeline.events import component_labels


class LiveGlobeTests(unittest.TestCase):
    def row(self, **changes):
        return dict(lat=23.8, lon=90.3, acq_datetime='2026-11-03T06:00:00+00:00',
                    confidence_pct=60, frp=10, sensor='viirs_snpp', satellite='N',
                    scan_km=.4, track_km=.4, daynight='D', **changes)

    def test_duplicate_and_overpass_power(self):
        a = self.row()
        b = {**a, 'lon': 90.3001, 'frp': 20}
        later = {**a, 'acq_datetime': '2026-11-03T07:00:00+00:00', 'frp': 25}
        low = {**a, 'lon': 91, 'confidence_pct': 25}
        result = harmonize([a, a, b, later, low])
        self.assertEqual(len(result['hotspots']), 1)
        point = result['hotspots'][0]
        self.assertEqual(point['harmonized']['observations'], 3)
        self.assertEqual(point['frp'], 30)  # max(10+20, 25), not 55
        self.assertEqual(result['metadata']['reason_counts']['duplicate_detection'], 1)
        self.assertEqual(result['metadata']['reason_counts']['low_confidence'], 1)
        self.assertGreater(point['harmonized']['footprint_area_km2'], 0)

    def test_empty(self):
        self.assertEqual(harmonize([])['hotspots'], [])

    def test_component_labels_preserve_sparse_detection_ids_and_row_order(self):
        graph = nx.Graph()
        graph.add_nodes_from([9001, 42, 700000, 8])
        graph.add_edge(9001, 700000)
        positions = pd.Series([0, 1, 2, 3], index=[42, 8, 9001, 700000])
        np.testing.assert_array_equal(component_labels(graph, positions), [1, 2, 0, 0])

    def test_representative_is_repeatable_when_peak_power_is_tied(self):
        a = self.row()
        b = {**a, 'lon': 90.3001, 'brightness_k': 340}
        result = harmonize([a, b])['hotspots'][0]
        self.assertEqual(result['lookup_detection']['lon'], a['lon'])
        self.assertEqual(result['harmonized']['observations'], 2)


if __name__ == '__main__':
    unittest.main()
