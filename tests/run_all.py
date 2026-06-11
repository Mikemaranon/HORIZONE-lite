import importlib
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
APP_WEB_SERVER_PATH = REPO_ROOT / "app" / "web_server"

for path in [str(APP_WEB_SERVER_PATH), str(REPO_ROOT)]:
    if path not in sys.path:
        sys.path.insert(0, path)


DOMAINS = [
    "tests.api_m.run",
    "tests.config_m.run",
    "tests.data_m.run",
    "tests.model_m.run",
    "tests.runtime_m.run",
    "tests.tool_m.run",
]

TOP_LEVEL_TESTS = [
    "tests.test_server",
]


def main():
    failed_domains = []

    for domain_runner in DOMAINS:
        module = importlib.import_module(domain_runner)
        exit_code = module.main()
        if exit_code != 0:
            failed_domains.append(domain_runner)

    for test_module in TOP_LEVEL_TESTS:
        suite = unittest.defaultTestLoader.loadTestsFromName(test_module)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        if not result.wasSuccessful():
            failed_domains.append(test_module)

    if failed_domains:
        print("\nFailed domains:")
        for domain in failed_domains:
            print(f"- {domain}")
        return 1

    print("\nAll test domains passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
