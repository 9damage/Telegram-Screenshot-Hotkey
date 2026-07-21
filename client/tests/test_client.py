import unittest

from client.client import DEFAULT_SERVER_URL, normalize_server_url


class ServerUrlTests(unittest.TestCase):
    def test_old_http_ip_is_migrated_to_https_domain(self):
        self.assertEqual(
            normalize_server_url("http://147.45.38.195/upload"),
            DEFAULT_SERVER_URL,
        )

    def test_current_https_domain_is_preserved(self):
        self.assertEqual(
            normalize_server_url("https://api.shera2tap.ru/upload"),
            DEFAULT_SERVER_URL,
        )

    def test_trailing_slash_is_removed(self):
        self.assertEqual(
            normalize_server_url("https://example.com/upload/"),
            "https://example.com/upload",
        )


if __name__ == "__main__":
    unittest.main()
