import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import app as app_module  # noqa: E402


class AppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["DB_PATH"] = os.path.join(self.tmp.name, "test.db")
        app_module.app.testing = True
        self.client = app_module.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def metric(self, name):
        text = self.client.get("/metrics").get_data(as_text=True)
        for line in text.splitlines():
            if line.startswith(name + " "):
                return float(line.split()[1])
        self.fail(f"метрика {name} не найдена")

    def test_notes_crud(self):
        self.client.post("/notes/new", data={"title": "Первая", "body": "текст"})
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn("Первая", page)

        self.client.post("/notes/1/edit", data={"title": "Изменённая", "body": "новый текст"})
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn("Изменённая", page)
        self.assertNotIn("Первая", page)

        self.client.post("/notes/1/delete")
        self.assertIn("Заметок пока нет", self.client.get("/").get_data(as_text=True))

    def test_html_is_escaped(self):
        self.client.post("/notes/new", data={"title": "<script>x</script>", "body": ""})
        self.assertNotIn("<script>x</script>", self.client.get("/").get_data(as_text=True))

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ok")

    def test_visits_count_only_main_page(self):
        self.assertEqual(self.metric("app_visits_last_hour"), 0)
        for _ in range(3):
            self.client.get("/")
        # служебные запросы (health check, метрики, статус) посещениями не считаются
        self.client.get("/health")
        self.client.get("/status")
        self.assertEqual(self.metric("app_visits_last_hour"), 3)

    def test_metrics_has_resources(self):
        for name in (
            "app_container_memory_usage_bytes",
            "app_container_memory_limit_bytes",
            "app_container_cpu_usage_seconds_total",
            "app_host_memory_available_bytes",
            "app_disk_free_bytes",
        ):
            self.assertGreater(self.metric(name), 0, name)

    def test_status_page(self):
        resp = self.client.get("/status")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Health check", resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
