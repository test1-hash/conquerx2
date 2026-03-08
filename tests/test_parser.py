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

    def test_parse_html_table(self):
        html = '''
        <div class="h2doc">
          <div>
            <div class="padding10"><strong>Jupiter-002 サーバー</strong></div>
            <table class="list rank">
              <tr>
                <th>ランク</th><th>プレーヤー</th><th>レベル</th><th>所有惑星数</th><th>ポイント</th><th>平均ポイント</th><th>所属帝国</th>
              </tr>
              <tr>
                <td>1</td><td>初心者</td><td>aaaa</td><td>14</td><td>4</td><td>7,597</td><td>1,899</td><td></td>
              </tr>
              <tr>
                <td>5</td><td>帝国の一員</td><td>雷光</td><td>10</td><td>2</td><td>2,670</td><td>1,335</td><td>スペースストーム</td>
              </tr>
            </table>
          </div>
        </div>
        '''
        rows = parse_rank_rows_from_text(html, 'Jupiter-002')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].player_name, 'aaaa')
        self.assertIsNone(rows[0].empire_name)
        self.assertEqual(rows[1].title, '帝国の一員')
        self.assertEqual(rows[1].empire_name, 'スペースストーム')


if __name__ == '__main__':
    unittest.main()
