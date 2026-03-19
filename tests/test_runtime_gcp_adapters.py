# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapter_ingestion.runtime.adapters.gcp import PubSubJobQueue


class DeadlineExceeded(Exception):
    pass


class _RaisingSubscriber:
    def pull(self, request: dict, timeout: int) -> object:
        raise DeadlineExceeded("empty pull window")


class PubSubJobQueueTests(unittest.TestCase):
    def test_dequeue_returns_none_on_deadline_exceeded(self) -> None:
        queue = PubSubJobQueue.__new__(PubSubJobQueue)
        queue._subscriber = _RaisingSubscriber()
        queue._subscription_path = "projects/test/subscriptions/test-sub"
        self.assertIsNone(queue.dequeue())


if __name__ == "__main__":
    unittest.main()
