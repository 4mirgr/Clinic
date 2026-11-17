import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase


class PreviewExportTests(TestCase):
    def test_export_is_read_only_and_uses_only_synthetic_public_pages(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as scratch:
            output = Path(scratch) / 'public'
            result = subprocess.run([sys.executable, str(root / 'scripts/build_preview.py'), '--output', str(output)], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertIn('/clinic/', manifest)
            self.assertIn('/clinic/portal/', manifest)
            pages = list(output.glob('*.html'))
            self.assertGreaterEqual(len(pages), 10)
            for page in pages:
                html = page.read_text()
                self.assertIn('پیش‌نمایش آزمایشی', html, page.name)
                self.assertNotIn('csrfmiddlewaretoken', html, page.name)
                self.assertNotIn('/dash/', html, page.name)
                self.assertNotIn('/portal.js', html, page.name)
                self.assertNotIn('method="post"', html.lower(), page.name)
                self.assertNotIn('data-portal-api=', html, page.name)
            self.assertIn('disabled', (output / 'patient-form.html').read_text())
            self.assertIn('داده‌های نمایشی', (output / 'dashboard.html').read_text())
            for route, asset in manifest.items():
                self.assertTrue(route.startswith('/clinic/'))
                self.assertNotIn('..', asset['path'])
                self.assertFalse(asset['path'].startswith(('.data', '.env')))
