from datetime import datetime
import unittest
from unittest.mock import patch

import manage
from cx2pages.utils import JST


class ManageSchedulerTest(unittest.TestCase):
    def test_next_update_check_waits_one_second_just_before_05(self):
        now = datetime(2026, 4, 20, 23, 4, 59, 950000, tzinfo=JST)
        with patch("manage._current_hour_already_fetched", return_value=False):
            self.assertEqual(manage._next_update_check_delay_seconds(now), 1)

    def test_next_update_check_retries_soon_just_after_05_if_hour_missing(self):
        now = datetime(2026, 4, 20, 23, 5, 0, 100000, tzinfo=JST)
        with patch("manage._current_hour_already_fetched", return_value=False):
            self.assertEqual(manage._next_update_check_delay_seconds(now), 15)

    def test_next_update_check_waits_until_next_hour_after_success(self):
        now = datetime(2026, 4, 20, 23, 10, 0, tzinfo=JST)
        with patch("manage._current_hour_already_fetched", return_value=True):
            self.assertEqual(manage._next_update_check_delay_seconds(now), 3300)


if __name__ == "__main__":
    unittest.main()
