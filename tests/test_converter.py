import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from md_to_pdf import convert

ROOT = Path(__file__).resolve().parents[1]


class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'api.md'
        self.target = self.root / 'api.pdf'

    def write(self, text):
        self.source.write_text(text, encoding='utf-8')

    def test_demo_cover_logos_linked_index_and_chrome_on_every_page(self):
        convert(ROOT/'examples/api.md', self.target, ROOT/'examples/empresa.json')
        pdf = PdfReader(self.target)
        self.assertGreaterEqual(len(pdf.pages), 4)
        self.assertIn('API de clientes', pdf.pages[0].extract_text())
        self.assertEqual(len(pdf.pages[0].images), 2)
        toc = pdf.pages[1]
        self.assertIn('Índice', toc.extract_text())
        self.assertIn('Introducción', toc.extract_text())
        links = [a.get_object() for a in toc.get('/Annots', [])]
        self.assertTrue(any('/Dest' in a for a in links))
        # Each TOC destination resolves to a real heading page, not cover/index.
        page_ids = {p.indirect_reference.idnum: i for i, p in enumerate(pdf.pages)}
        for link in links:
            if '/Dest' in link:
                number = page_ids[link['/Dest'][0].idnum]+1
                self.assertGreaterEqual(number, 3)
                self.assertRegex(toc.extract_text(), rf'\b{number}\b')
        for n, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            self.assertIn('EMPRESA DE EJEMPLO | API de clientes', text)
            self.assertIn('Confidencial', text)
            self.assertIn(f'Página {n}', text)
        all_text = ''.join(p.extract_text() for p in pdf.pages)
        for value in ['María Muñoz', 'POST /clientes', '201 Created', 'cliente_no_encontrado']:
            self.assertIn(value, all_text)

    def test_long_code_tables_duplicate_titles_and_local_image(self):
        logo = ROOT/'examples/logo-demo.png'
        self.write('# Inicio\n\n![demo]('+str(logo)+')\n\n## Detalle\n\n'
                   '```json\n'+''.join(f'  "campo_{i}": "valor",\n' for i in range(160))+
                   '"larga": "'+('x'*1200)+'"\n```\n\n## Detalle\n\n'
                   '| Campo | Valor |\n| --- | --- |\n'+
                   ''.join(f'| fila_{i} | información |\n' for i in range(100)))
        convert(self.source, self.target)
        pdf = PdfReader(self.target)
        self.assertGreater(len(pdf.pages), 5)
        text = ''.join(p.extract_text() for p in pdf.pages)
        self.assertIn('campo_159', text)
        self.assertIn('fila_99', text)
        self.assertTrue(any(p.images for p in pdf.pages[2:]))
        self.assertIn('Detalle', pdf.pages[1].extract_text())

    def test_no_clobber_and_atomic_failure(self):
        self.write('# Título\n\nTexto.')
        with self.assertRaises(ValueError):
            convert(self.source, self.source, force=True)
        self.target.write_bytes(b'existing')
        with self.assertRaises(ValueError):
            convert(self.source, self.target)
        self.write('# Título\n\n![missing](missing.png)')
        with self.assertRaises(ValueError):
            convert(self.source, self.target, force=True)
        self.assertEqual(self.target.read_bytes(), b'existing')

    def test_remote_images_are_rejected(self):
        for url in ['https://example.com/image.png', '//example.com/image.png',
                    'file:///etc/passwd', 'data:image/png;base64,AA']:
            with self.subTest(url=url):
                self.write('# API\n\n![imagen]('+url+')')
                with self.assertRaises(ValueError):
                    convert(self.source, self.target)
        self.assertFalse(self.target.exists())

    def test_config_paths_relative_to_config_not_cwd(self):
        (self.root/'assets').mkdir()
        logo = self.root/'assets/logo.png'
        logo.write_bytes((ROOT/'examples/logo-demo.png').read_bytes())
        config = self.root/'assets/company.json'
        config.write_text(json.dumps({'logos': ['logo.png'], 'title': 'Configuración'}))
        self.write('# API\n\nCorrecto.')
        convert(self.source, self.target, config)
        self.assertEqual(len(PdfReader(self.target).pages[0].images), 1)

    def test_document_without_headings_has_honest_index(self):
        self.write('Un párrafo sin títulos.')
        convert(self.source, self.target)
        pdf = PdfReader(self.target)
        self.assertIn('Sin títulos para indexar.', pdf.pages[1].extract_text())
        self.assertIn('Un párrafo sin títulos.', pdf.pages[2].extract_text())

    def test_percent_encoded_internal_anchor_resolves(self):
        self.write('# Introducción\n\n[Ir](#introducci%C3%B3n)')
        convert(self.source, self.target)
        pdf = PdfReader(self.target)
        links = [a.get_object() for a in pdf.pages[2].get('/Annots', [])]
        self.assertTrue(any('/Dest' in link for link in links))
        for link in links:
            if '/Dest' in link:
                self.assertEqual(link['/Dest'][0].idnum,
                                 pdf.pages[2].indirect_reference.idnum)

    def test_only_deep_headings_have_no_placeholder_index(self):
        self.write('#### Profundo\n\nTexto.\n\n###### Más profundo')
        convert(self.source, self.target)
        text = PdfReader(self.target).pages[1].extract_text()
        self.assertIn('Sin títulos para indexar.', text)
        self.assertNotIn('Placeholder', text)

    def test_duplicate_heading_slug_does_not_collide_with_suffix_title(self):
        self.write('# foo\n\n# foo-1\n\n# foo\n\n[Último](#foo-2)')
        convert(self.source, self.target)
        pdf = PdfReader(self.target)
        self.assertEqual([entry.title for entry in pdf.outline], ['foo', 'foo-1', 'foo'])
        toc_links = [a.get_object() for a in pdf.pages[1].get('/Annots', [])]
        self.assertGreaterEqual(sum('/Dest' in link for link in toc_links), 3)

    def test_interactive_cli_and_friendly_error(self):
        self.write('# Entrada\n\nFunciona.')
        command = [sys.executable, str(ROOT/'md_to_pdf.py')]
        result = subprocess.run(command, input=str(self.source)+'\n', text=True,
                                capture_output=True, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.target.exists())
        result = subprocess.run(command+['no-existe.md'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Error:', result.stderr)
        self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
