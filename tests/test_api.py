"""Тесты HTTP API (на настоящем сокете, без внешних зависимостей)."""
from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from boolgen.api import create_handler
from boolgen.pool import TaskPool
from boolgen.service import TaskService

PARAMS = {
    "task_type": "count_ones",
    "operations": ["NOT", "AND", "OR"],
    "variables": 3,
    "depth": 2,
    "nodes_max": 11,
    "count": 2,
    "difficulty": "easy",
}


class TestHttpApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = TaskService(pool=TaskPool(":memory:"))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(cls.service))
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.service.pool.close()

    def _get(self, path: str):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))

    def _post(self, path: str, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_health(self):
        status, payload = self._get("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")

    def test_index_page_served(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=10) as response:
            html = response.read().decode("utf-8")
        self.assertIn("<form", html)
        self.assertIn("app.js", html)

    def test_generate_hides_reference(self):
        status, payload = self._post("/api/generate", {"params": PARAMS})
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["tasks"]), 2)
        for task in payload["tasks"]:
            self.assertNotIn("reference", task)
            self.assertIn("prompt", task)

    def test_generate_rejects_bad_params(self):
        bad = dict(PARAMS, variables=9)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post("/api/generate", {"params": bad})
        self.assertEqual(ctx.exception.code, 400)

    def test_check_endpoint_grades_answer(self):
        _, payload = self._post("/api/generate", {"params": dict(PARAMS, count=1)})
        task = payload["tasks"][0]
        stored = self.service.pool.get(task["id"])
        correct = stored["reference"]["value"]
        status, result = self._post(
            "/api/check", {"task_id": task["id"], "params": PARAMS, "answer": str(correct)}
        )
        self.assertEqual(status, 200)
        self.assertTrue(result["correct"])
        _, wrong = self._post(
            "/api/check", {"task_id": task["id"], "params": PARAMS,
                           "answer": str(correct + 1)}
        )
        self.assertFalse(wrong["correct"])

    def test_pool_stats(self):
        self._post("/api/generate", {"params": PARAMS})
        status, stats = self._get("/api/pool/stats")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(stats["published"], 1)


if __name__ == "__main__":
    unittest.main()
