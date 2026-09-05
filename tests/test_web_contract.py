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

    def test_battle_dom_and_shared_renderer_contract(self):
        html = (WEB / "battle.html").read_text()
        js = (WEB / "battle.js").read_text()
        ids = set(re.findall(r"\$\(['\"]([^'\"]+)['\"]\)", js))
        for side in ("left", "right"):
            ids.update(side + suffix for suffix in ("Name", "Status", "Risk", "Decision", "Algorithm"))
        for element_id in ids:
            self.assertIn(f'id="{element_id}"', html)
        for page in ("index.html", "battle.html"):
            content = (WEB / page).read_text()
            self.assertIn('src="/map-renderer.js"', content)
            self.assertNotIn("https://", content)
        self.assertIn('href="/battle.html"', (WEB / "index.html").read_text())
        self.assertIn('href="/"', html)

    def test_viewer_has_no_remote_runtime_assets(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("https://", html)
        self.assertNotIn("http://", html)

    def test_required_view_modes_are_present(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="crowdBtn"', html)
        self.assertIn('id="immersiveBtn"', html)
        self.assertIn('id="metroCanvas"', html)

    def test_algorithm_library_selector_is_present(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        js = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="algorithmSelect"', html)
        self.assertIn("control('algorithm'", js)
        self.assertIn("algorithmSummary", js)


if __name__ == "__main__":
    unittest.main()
