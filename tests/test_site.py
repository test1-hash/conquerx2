from datetime import datetime
from pathlib import Path
import shutil
import tempfile
import unittest

from cx2pages.models import FetchRun, Snapshot
from cx2pages.scraper import parse_rank_rows_from_text
from cx2pages.site import Settings, build_board, render_site
from cx2pages.state import add_fetch_run, add_or_replace_snapshot
from cx2pages.utils import JST, to_utc


class SiteBuildTest(unittest.TestCase):
    def test_build_board_with_comparison(self):
        text = Path('sample_data/jupiter002_public_ranking_2026-03-08.txt').read_text(encoding='utf-8')
        rows = parse_rank_rows_from_text(text, 'Jupiter-002')
        state = {'version': 1, 'generated_at_utc': None, 'snapshots': [], 'fetch_runs': []}
        snap1 = Snapshot(captured_at_utc=to_utc(datetime.fromisoformat('2026-03-08T00:00:00+09:00')), rows=rows, source_url='x')
        snap2 = Snapshot(captured_at_utc=to_utc(datetime.fromisoformat('2026-03-08T01:00:00+09:00')), rows=rows, source_url='x')
        add_or_replace_snapshot(state, snap1)
        add_or_replace_snapshot(state, snap2)
        add_fetch_run(state, FetchRun(started_at_utc=to_utc(datetime.fromisoformat('2026-03-08T01:00:00+09:00')), status='ok', row_count=len(rows), http_status=200, message=None, url='x'))
        latest, board, comparisons = build_board(state)
        self.assertIsNotNone(latest)
        self.assertEqual(len(board), 31)
        self.assertIn(1, comparisons)
        self.assertEqual(board[0]['comparisons'][1]['delta_points'], 0)

    def test_render_site_outputs_index(self):
        text = Path('sample_data/jupiter002_public_ranking_2026-03-08.txt').read_text(encoding='utf-8')
        rows = parse_rank_rows_from_text(text, 'Jupiter-002')
        state = {'version': 1, 'generated_at_utc': None, 'snapshots': [], 'fetch_runs': []}
        add_or_replace_snapshot(state, Snapshot(captured_at_utc=to_utc(datetime.fromisoformat('2026-03-08T00:00:00+09:00')), rows=rows, source_url='x'))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'docs'
            render_site(Path('.').resolve(), out, Settings(server_label='Jupiter-002', server_rank_url='x'), state)
            self.assertTrue((out / 'index.html').exists())
            self.assertTrue((out / 'data' / 'latest.json').exists())


if __name__ == '__main__':
    unittest.main()
