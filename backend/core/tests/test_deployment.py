import re

from django.test import SimpleTestCase, override_settings


@override_settings(SECURE_SSL_REDIRECT=False)
class DeploymentTests(SimpleTestCase):
    def test_built_frontend_and_its_assets_are_served_on_the_api_origin(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = b"".join(response.streaming_content).decode()
        asset = re.search(r'src="([^"]+\.js)"', html)[1]
        result = self.client.get(asset)
        self.assertEqual(result.status_code, 200)
        self.assertIn("javascript", result["Content-Type"])
        self.assertEqual(self.client.get("/api/not-a-route/").status_code, 404)
        self.assertEqual(self.client.get("/assets/missing.js").status_code, 404)

    def test_health_check_does_not_require_a_database_or_session(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertNotIn("sessionid", response.cookies)
