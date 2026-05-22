import html
import re
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
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

SEARCH_ENDPOINT = "https://duckduckgo.com/html/?q={query}"
RESULT_PATTERN = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
SNIPPET_PATTERN = re.compile(
    r'<a[^>]*class="result__a"[^>]*>.*?</a>.*?<a[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
TAG_PATTERN = re.compile(r"<[^>]+>")


def run(arguments: dict) -> dict:
    query = str((arguments or {}).get("query", "")).strip()
    if not query:
        raise ValueError("The 'query' argument is required.")

    max_results = int((arguments or {}).get("max_results") or 5)
    max_results = max(1, min(max_results, 10))

    request = Request(
        SEARCH_ENDPOINT.format(query=quote_plus(query)),
        headers={
            "User-Agent": "HORIZONE-lite/0.1",
        },
    )

    with urlopen(request, timeout=8) as response:
        payload = response.read().decode("utf-8", errors="ignore")

    results = _extract_results(payload, max_results)
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
