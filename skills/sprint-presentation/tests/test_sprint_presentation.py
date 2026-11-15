import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from pptx import Presentation


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "sprint_presentation.py"
SPEC = SKILL_ROOT / "assets" / "example-experiment.json"


class SprintPresentationTests(unittest.TestCase):
    def test_create_and_append_experiment(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            starter = root / "sprint.pptx"
            completed = root / "sprint-with-experiment.pptx"

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "create",
                    "--sprint",
                    "Sprint Test",
                    "--title",
                    "Master - Instability Model Experiments",
                    "--subtitle",
                    "Yakov Elmaleh",
                    "--output",
                    str(starter),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            starter_presentation = Presentation(starter)
            self.assertEqual(1, len(starter_presentation.slides))

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "append",
                    "--presentation",
                    str(starter),
                    "--spec",
                    str(SPEC),
                    "--output",
                    str(completed),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            completed_presentation = Presentation(completed)
            self.assertEqual(5, len(completed_presentation.slides))
            self.assertEqual(
                "Per-project instability model - Data Analysis",
                completed_presentation.slides[2].shapes.title.text.replace("—", "-"),
            )
            self.assertEqual(
                "Conclusions",
                completed_presentation.slides[4].shapes.title.text,
            )

            with zipfile.ZipFile(completed) as archive:
                entries = archive.namelist()
            self.assertEqual(len(entries), len(set(entries)))


if __name__ == "__main__":
    unittest.main()
