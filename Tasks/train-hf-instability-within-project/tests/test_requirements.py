"""Offline guard for the verified HF dependency intersection."""

from pathlib import Path
import unittest


TASK = Path(__file__).resolve().parents[1]


class RequirementsTests(unittest.TestCase):
    def test_hub_pin_satisfies_transformers_and_tokenizers(self):
        pins = {}
        for line in (TASK / "requirements.txt").read_text().splitlines():
            line = line.split("#", 1)[0].split(";", 1)[0].strip()
            if line:
                name, version = line.split("==")
                pins[name] = version
        if pins["transformers"] != "5.18.0":
            self.fail("Reverify published Transformers/Tokenizers constraints before changing this guard.")
        hub = tuple(int(part) for part in pins["huggingface-hub"].split("."))
        self.assertGreaterEqual(hub, (1, 31, 0))
        self.assertLess(hub, (2, 0, 0))


if __name__ == "__main__":
    unittest.main()
