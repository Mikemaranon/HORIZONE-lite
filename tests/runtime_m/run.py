import sys
import unittest
from pathlib import Path


def main():
    domain_dir = Path(__file__).resolve().parent
    repo_root = domain_dir.parent.parent
    app_web_server_path = repo_root / "app" / "web_server"

    for path in [str(app_web_server_path), str(repo_root)]:
        if path not in sys.path:
            sys.path.insert(0, path)

    suite = unittest.defaultTestLoader.discover(
        start_dir=str(domain_dir),
        pattern="test_*.py",
        top_level_dir=str(repo_root),
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
