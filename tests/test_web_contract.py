import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


class WebContractTests(unittest.TestCase):
    def test_every_js_id_exists_in_html(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        js = (WEB / "app.js").read_text(encoding="utf-8")
        ids = set(re.findall(r"\$\(['\"]([^'\"]+)['\"]\)", js))
        missing = sorted(element_id for element_id in ids if f'id="{element_id}"' not in html)
        self.assertEqual(missing, [], f"app.js references missing DOM ids: {missing}")

    def test_viewer_has_no_remote_runtime_assets(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("https://", html)
        self.assertNotIn("http://", html)

    def test_required_view_modes_are_present(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="crowdBtn"', html)
        self.assertIn('id="immersiveBtn"', html)
        self.assertIn('id="metroCanvas"', html)


if __name__ == "__main__":
    unittest.main()
