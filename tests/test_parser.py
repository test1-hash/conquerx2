from pathlib import Path
import unittest

from cx2pages.scraper import parse_rank_rows_from_text


class ParserTest(unittest.TestCase):
    def test_parse_fixture(self):
        text = Path('sample_data/jupiter002_public_ranking_2026-03-08.txt').read_text(encoding='utf-8')
        rows = parse_rank_rows_from_text(text, 'Jupiter-002')
        self.assertEqual(len(rows), 31)
        self.assertEqual(rows[0].rank_position, 1)
        self.assertEqual(rows[0].player_name, 'aaaa')


if __name__ == '__main__':
    unittest.main()
