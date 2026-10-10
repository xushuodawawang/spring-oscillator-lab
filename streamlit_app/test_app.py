"""验证部署入口能启动，以及从任意工作目录读取提交的前端。"""
from pathlib import Path
import os
import tempfile
import unittest

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


class StreamlitDeploymentTests(unittest.TestCase):
    def test_start_from_another_working_directory(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                app = AppTest.from_file(str(ROOT / "streamlit_app/app.py"), default_timeout=20).run()
                self.assertEqual(len(app.exception), 0, list(app.exception))
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
