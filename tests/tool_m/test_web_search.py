import unittest
from unittest.mock import patch

from tool_m.tools import web_search


class _FakeResponse:
    def __init__(self, payload, *, status=200, content_type="text/html; charset=UTF-8"):
        self._payload = payload.encode("utf-8")
        self.status = status
        self.headers = {"content-type": content_type}

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class WebSearchTests(unittest.TestCase):
    def test_run_uses_browser_headers_and_extracts_results(self):
        payload = """
        <div class="result">
          <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fmatch">KOI match</a>
          <a class="result__snippet">Latest &amp; verified result.</a>
        </div>
        """
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return _FakeResponse(payload)

        with patch.object(web_search, "urlopen", side_effect=fake_urlopen):
            result = web_search.run({"query": "KOI latest match", "max_results": 5})

        self.assertIn("Mozilla/5.0", captured["request"].get_header("User-agent"))
        self.assertEqual(captured["timeout"], 8)
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["results"][0]["url"], "https://example.com/match")
        self.assertEqual(result["results"][0]["snippet"], "Latest & verified result.")

    def test_run_rejects_duckduckgo_bot_challenge(self):
        payload = """
        <div class="anomaly-modal" data-testid="anomaly-modal">
          <div class="anomaly-modal__title">Unfortunately, bots use DuckDuckGo too.</div>
        </div>
        """

        with patch.object(
            web_search,
            "urlopen",
            return_value=_FakeResponse(payload, status=202),
        ):
            with self.assertRaisesRegex(web_search.WebSearchError, "blocked automated access"):
                web_search.run({"query": "KOI latest match"})

    def test_run_rejects_unrecognized_search_html_instead_of_reporting_zero_results(self):
        payload = "<html><title>DuckDuckGo</title><p>Unexpected response.</p></html>"

        with patch.object(web_search, "urlopen", return_value=_FakeResponse(payload)):
            with self.assertRaisesRegex(web_search.WebSearchError, "unrecognized response"):
                web_search.run({"query": "KOI latest match"})


if __name__ == "__main__":
    unittest.main()
