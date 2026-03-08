from datetime import datetime
from pathlib import Path
import shutil
import tempfile
import unittest

from cx2pages.models import FetchRun, RankRow, Snapshot
from cx2pages.scraper import parse_rank_rows_from_text
from cx2pages.site import Settings, build_board, get_fleet_rows, render_site
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

    def test_build_board_with_fleet_comparison(self):
        rows1 = [
            RankRow(rank_position=1, title=None, player_name='aaaa', level=None, planets=4, points=1000, avg_points=250, fleet_score=120, empire_name='A'),
            RankRow(rank_position=2, title=None, player_name='bbbb', level=None, planets=3, points=900, avg_points=300, fleet_score=160, empire_name='B'),
        ]
        rows2 = [
            RankRow(rank_position=1, title=None, player_name='aaaa', level=None, planets=4, points=1100, avg_points=275, fleet_score=150, empire_name='A'),
            RankRow(rank_position=2, title=None, player_name='bbbb', level=None, planets=3, points=950, avg_points=316, fleet_score=140, empire_name='B'),
        ]
        state = {'version': 1, 'generated_at_utc': None, 'snapshots': [], 'fetch_runs': []}
        add_or_replace_snapshot(state, Snapshot(captured_at_utc=to_utc(datetime.fromisoformat('2026-03-08T00:00:00+09:00')), rows=rows1, source_url='x'))
        add_or_replace_snapshot(state, Snapshot(captured_at_utc=to_utc(datetime.fromisoformat('2026-03-08T01:00:00+09:00')), rows=rows2, source_url='x'))

        latest, board, _comparisons = build_board(state)
        self.assertIsNotNone(latest)
        aaaa = next(row for row in board if row['player_name'] == 'aaaa')
        self.assertEqual(aaaa['comparisons'][1]['delta_fleet'], 30)

        latest_fleet, fleet_rows, _fleet_comparisons = get_fleet_rows(state)
        self.assertIsNotNone(latest_fleet)
        self.assertEqual(fleet_rows[0]['player_name'], 'aaaa')
        self.assertEqual(fleet_rows[0]['fleet_rank_position'], 1)

    def test_render_site_outputs_index(self):
        text = Path('sample_data/jupiter002_public_ranking_2026-03-08.txt').read_text(encoding='utf-8')
        rows = parse_rank_rows_from_text(text, 'Jupiter-002')
        state = {'version': 1, 'generated_at_utc': None, 'snapshots': [], 'fetch_runs': []}
        add_or_replace_snapshot(state, Snapshot(captured_at_utc=to_utc(datetime.fromisoformat('2026-03-08T00:00:00+09:00')), rows=rows, source_url='x'))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'docs'
            render_site(Path('.').resolve(), out, Settings(server_label='Jupiter-002', server_rank_url='x'), state)
            self.assertTrue((out / 'index.html').exists())
            self.assertTrue((out / 'fleet.html').exists())
            self.assertTrue((out / 'data' / 'latest.json').exists())
            self.assertTrue((out / 'data' / 'fleet.json').exists())

    def test_render_site_without_title_and_level(self):
        rows = [
            RankRow(rank_position=1, title=None, player_name='aaaa', level=None, planets=6, points=10851, avg_points=1808, fleet_score=1733, empire_name=None),
            RankRow(rank_position=2, title=None, player_name='だいあん', level=None, planets=10, points=11810, avg_points=1181, fleet_score=1035, empire_name=None),
        ]
        state = {'version': 1, 'generated_at_utc': None, 'snapshots': [], 'fetch_runs': []}
        add_or_replace_snapshot(state, Snapshot(captured_at_utc=to_utc(datetime.fromisoformat('2026-03-08T18:00:00+09:00')), rows=rows, source_url='x'))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'docs'
            render_site(Path('.').resolve(), out, Settings(server_label='Jupiter-002', server_rank_url='x'), state)
            index_html = (out / 'index.html').read_text(encoding='utf-8')
            fleet_html = (out / 'fleet.html').read_text(encoding='utf-8')
            player_html = next((out / 'players').glob('*.html')).read_text(encoding='utf-8')
            self.assertIn('aaaa', index_html)
            self.assertNotIn('称号 / プレイヤー', index_html)
            self.assertIn('戦力ランキング', fleet_html)
            self.assertIn('1,733', fleet_html)
            self.assertIn('最新戦力', player_html)


if __name__ == '__main__':
    unittest.main()
