"""
Unit tests for cookie parsing and replication across STV mirror domains.
"""

import json
from pathlib import Path
import tempfile
import unittest

from browser_manager import parse_cookies_input


class TestCookieParser(unittest.TestCase):
    def test_parse_cookie_header_string(self):
        cookie_str = "PHPSESSID=abc123xyz; user=vip_member; token=tok999"
        cookies = parse_cookies_input(cookie_str, target_hosts=["14.225.254.182", "sangtacviet.vip"])
        
        # 3 cookies * 2 hosts = 6
        self.assertEqual(len(cookies), 6)
        names = {c["name"] for c in cookies}
        self.assertEqual(names, {"PHPSESSID", "user", "token"})

        # Verify urls
        urls = {c["url"] for c in cookies}
        self.assertIn("http://14.225.254.182", urls)
        self.assertIn("https://sangtacviet.vip", urls)

    def test_parse_cookie_json_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            sample_json = [
                {"name": "_gac", "value": "gac_val_1", "domain": ".sangtacviet.vip"},
                {"name": "auth_token", "value": "secret_token_2"}
            ]
            json.dump(sample_json, f)
            temp_path = f.name

        try:
            cookies = parse_cookies_input(temp_path, target_hosts=["14.225.254.182"])
            self.assertEqual(len(cookies), 2)
            self.assertEqual(cookies[0]["name"], "_gac")
            self.assertEqual(cookies[0]["value"], "gac_val_1")
            self.assertEqual(cookies[0]["url"], "http://14.225.254.182")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_parse_empty_source(self):
        self.assertEqual(parse_cookies_input(None), [])
        self.assertEqual(parse_cookies_input(""), [])


if __name__ == "__main__":
    unittest.main()
