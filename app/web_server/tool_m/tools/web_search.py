import html
import re
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TOOL_NAME = "web_search"
TOOL_DISPLAY_NAME = "web search"
TOOL_DESCRIPTION = "Searches the web and returns a small list of relevant results."
TOOL_PARAMETERS = {
    "query": {
        "type": "string",
        "required": True,
        "description": "The search query to run on the public web.",
    },
    "max_results": {
        "type": "integer",
        "required": False,
        "default": 5,
        "description": "Maximum number of results to return.",
    },
}
TOOL_CAPABILITIES = [
    "find current or external information on the public web",
    "return source URLs, titles, and short snippets",
]
TOOL_USE_WHEN = [
    "The user needs recent, changing, or source-backed information.",
    "The model needs to verify a fact outside the local conversation.",
]
TOOL_RISK_LEVEL = "external_network"

SEARCH_ENDPOINT = "https://duckduckgo.com/html/?q={query}"
SEARCH_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/137.0.0.0 Safari/537.36 HORIZONE/0.1"
)
BOT_CHALLENGE_MARKERS = (
    "anomaly-modal",
    "duckduckgo.com/anomaly.js",
    "Unfortunately, bots use DuckDuckGo too.",
)
NO_RESULTS_MARKERS = (
    'class="no-results"',
    "No results found",
    "No results.",
)
RESULT_PATTERN = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
SNIPPET_PATTERN = re.compile(
    r'<a[^>]*class="result__a"[^>]*>.*?</a>.*?<a[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
TAG_PATTERN = re.compile(r"<[^>]+>")


class WebSearchError(RuntimeError):
    pass


def run(arguments: dict) -> dict:
    query = str((arguments or {}).get("query", "")).strip()
    if not query:
        raise ValueError("The 'query' argument is required.")

    max_results = int((arguments or {}).get("max_results") or 5)
    max_results = max(1, min(max_results, 10))

    request = Request(
        SEARCH_ENDPOINT.format(query=quote_plus(query)),
        headers={
            "User-Agent": SEARCH_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.8",
        },
    )

    try:
        with urlopen(request, timeout=8) as response:
            status = int(getattr(response, "status", 200) or 200)
            content_type = str(response.headers.get("content-type") or "").lower()
            payload = response.read().decode("utf-8", errors="ignore")
    except HTTPError as error:
        raise WebSearchError(
            f"The web search service returned HTTP {error.code}."
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise WebSearchError("The web search service could not be reached.") from error

    if _is_bot_challenge(payload):
        raise WebSearchError("The web search service blocked automated access.")
    if status != 200:
        raise WebSearchError(f"The web search service returned HTTP {status}.")
    if content_type and "html" not in content_type:
        raise WebSearchError("The web search service returned an unsupported response.")

    results = _extract_results(payload, max_results)
    if not results and not _is_explicit_no_results(payload):
        raise WebSearchError("The web search service returned an unrecognized response.")

    return {
        "query": query,
        "results": results,
        "result_count": len(results),
    }


def _extract_results(payload, max_results):
    matches = list(RESULT_PATTERN.finditer(payload))
    snippets = SNIPPET_PATTERN.findall(payload)
    results = []

    for index, match in enumerate(matches[:max_results]):
        title = _clean_html(match.group("title"))
        url = _normalize_result_url(match.group("url"))
        snippet = _clean_html(snippets[index]) if index < len(snippets) else ""

        if not title or not url:
            continue

        results.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
            }
        )

    return results


def _is_bot_challenge(payload):
    normalized_payload = str(payload or "").lower()
    return any(marker.lower() in normalized_payload for marker in BOT_CHALLENGE_MARKERS)


def _is_explicit_no_results(payload):
    normalized_payload = str(payload or "").lower()
    return any(marker.lower() in normalized_payload for marker in NO_RESULTS_MARKERS)


def _normalize_result_url(url):
    normalized_url = html.unescape(url or "").strip()
    parsed = urlparse(normalized_url)
    if "duckduckgo.com" not in (parsed.netloc or ""):
        return normalized_url

    redirected_url = parse_qs(parsed.query).get("uddg", [])
    if redirected_url:
        return unquote(redirected_url[0])

    return normalized_url


def _clean_html(value):
    text = TAG_PATTERN.sub("", value or "")
    return html.unescape(text).strip()
