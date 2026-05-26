from pathlib import Path

from tests.test_support import ApiTestCase


class NativeDialogsApiTests(ApiTestCase):
    def test_directory_picker_endpoint_returns_selected_directory(self):
        selected_root = Path(self.temp_dir.name) / "workspace"
        selected_root.mkdir()
        captured = {}

        def fake_select_directory(initial_path=None, title=None):
            captured["initial_path"] = initial_path
            captured["title"] = title
            return {
                "root_path": str(selected_root),
                "display_name": "workspace",
            }

        self.api_manager.services.native_directory_picker.select_directory = fake_select_directory

        response = self.client.post(
            "/api/native/directory-picker",
            json={
                "initial_path": str(selected_root),
                "title": "Choose workspace folder",
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["canceled"])
        self.assertEqual(payload["directory"]["root_path"], str(selected_root))
        self.assertEqual(payload["directory"]["display_name"], "workspace")
        self.assertEqual(captured["initial_path"], str(selected_root))
        self.assertEqual(captured["title"], "Choose workspace folder")

    def test_directory_picker_endpoint_reports_cancel(self):
        self.api_manager.services.native_directory_picker.select_directory = lambda **_: None

        response = self.client.post(
            "/api/native/directory-picker",
            json={},
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["canceled"])
        self.assertIsNone(payload["directory"])
