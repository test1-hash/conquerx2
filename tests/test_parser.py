from pathlib import Path
import unittest

from cx2pages.scraper import (
    extract_game_connect_auth_url,
    is_new_user_registration_page,
    parse_game_player_detail,
    parse_rank_rows_from_export,
    parse_rank_rows_from_game_html,
    parse_rank_rows_from_text,
)


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

    def test_parse_export_files(self):
        users_text = '''
        [User List]
        62868,0,10851,1733,aaaa,1772690454
        62869,0,11810,1035,だいあん,1772715656
        62875,2666,5497,177,TK,1772693992
        '''
        planets_text = '''
        [Planet List]
        1,1,10,62868,0,1
        1,2,10,62868,0,1
        1,3,10,62869,0,1
        1,4,10,62869,0,1
        1,5,10,62869,0,1
        1,6,10,62875,2666,1
        '''
        empires_text = '''
        [Empire List]
        2666,15590,スペースストーム
        '''
        rows = parse_rank_rows_from_export(users_text, planets_text, empires_text)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0].player_name, 'だいあん')
        self.assertEqual(rows[0].rank_position, 1)
        self.assertEqual(rows[0].planets, 3)
        self.assertEqual(rows[0].avg_points, 3936)
        self.assertEqual(rows[0].fleet_score, 1035)
        self.assertIsNone(rows[0].level)
        self.assertEqual(rows[2].empire_name, 'スペースストーム')

    def test_parse_game_rank_html(self):
        html = '''
        <table class="list">
          <tr>
            <th>順位</th><th colspan="2">ユーザー</th><th>Lv.</th><th>惑星数</th><th>ポイント</th><th>平均ポイント</th><th>所属帝国</th>
          </tr>
          <tr class="hodd">
            <td>1</td>
            <td width="24"><div class="usertitleicon20x usertitleicon20x_1" title="初心者<br>説明"></div></td>
            <td><span class="pointer" onclick='openPlayerDialog("aaaa");'>aaaa</span></td>
            <td>21</td><td>23</td><td>53,162</td><td>2,311</td><td></td>
          </tr>
          <tr>
            <td>2</td>
            <td width="24"><div class="usertitleicon20x usertitleicon20x_2" title="匠の業<br>説明"></div></td>
            <td><span class="pointer" onclick='openPlayerDialog("だいあん");'>だいあん</span></td>
            <td>21</td><td>24</td><td>46,440</td><td>1,935</td><td>アシリア</td>
          </tr>
        </table>
        '''
        rows = parse_rank_rows_from_game_html(html)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].player_name, 'aaaa')
        self.assertEqual(rows[0].title, '初心者')
        self.assertEqual(rows[0].points, 53162)
        self.assertEqual(rows[1].empire_name, 'アシリア')

    def test_parse_game_player_detail(self):
        text = '''
        {
          "player": {
            "usernick": "aaaa",
            "score": 53162,
            "score_ship": 10206,
            "userlevel": 21,
            "owned_planet_count": 23,
            "empirename": null,
            "usertitle": {
              "titlename": "初心者"
            }
          }
        }
        '''
        detail = parse_game_player_detail(text)
        self.assertEqual(detail.player_name, 'aaaa')
        self.assertEqual(detail.fleet_score, 10206)
        self.assertEqual(detail.level, 21)
        self.assertEqual(detail.planets, 23)
        self.assertEqual(detail.title, '初心者')

    def test_extract_game_connect_auth_url(self):
        text = """
        <script>
        window.location.href = 'https://game-jp-02.conquerx2.com/auth/auth.php?key=abc123&area=jp&lang=jp&migration_id=0';
        </script>
        """
        self.assertEqual(
            extract_game_connect_auth_url(text),
            'https://game-jp-02.conquerx2.com/auth/auth.php?key=abc123&area=jp&lang=jp&migration_id=0',
        )

    def test_is_new_user_registration_page(self):
        text = """
        <html>
          <body>
            <form action="./" method="post" id="fo_register_newuser">
              <input type="text" name="nickname" value="test">
            </form>
          </body>
        </html>
        """
        self.assertTrue(is_new_user_registration_page(text))
        self.assertFalse(is_new_user_registration_page('<html><body>game main</body></html>'))


if __name__ == '__main__':
    unittest.main()
