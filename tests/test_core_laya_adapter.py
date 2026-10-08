import sys
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from cliverse.laya_adapter import LayaAdapterError, LayaDecisionAdapter


class FakeRouter:
    def __init__(self, response):
        self.response = response
        self.call = None

    def predict(self, state, questions, **kwargs):
        self.call = (state, questions, kwargs)
        return self.response


class LayaDecisionAdapterTests(unittest.TestCase):
    def test_uses_injected_router_and_preserves_typed_response(self):
        state = {"request": "Build a login flow"}
        questions = {"intent": {"type": "choice", "choices": ["feature", "bug"]}}
        response = {
            "answers": {"intent": {"choice": "feature"}},
            "routing": {"model": "local"},
        }
        router = FakeRouter(response)
        adapter = LayaDecisionAdapter(router)

        self.assertEqual(adapter.predict(state, questions), response)
        self.assertEqual(router.call, (state, questions, {}))

    def test_does_not_construct_router_when_missing(self):
        with self.assertRaisesRegex(LayaAdapterError, "inference is disabled"):
            LayaDecisionAdapter(None)

    def test_rejects_unexpected_response_shape(self):
        with self.assertRaisesRegex(LayaAdapterError, "answers"):
            LayaDecisionAdapter(FakeRouter({"routing": {}})).predict({}, {})

        with self.assertRaisesRegex(LayaAdapterError, "non-mapping"):
            LayaDecisionAdapter(FakeRouter(None)).predict({}, {})


if __name__ == "__main__":
    unittest.main()
