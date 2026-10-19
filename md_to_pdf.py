#!/usr/bin/env python3
"""Convert local Markdown to a branded PDF with a linked table of contents."""
import argparse
import json
import re
import sys
from html import escape
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, PageBreak, PageTemplate, Paragraph, Spacer, Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

INK = colors.HexColor('#15324d')
ACCENT = colors.HexColor('#087e8b')
MUTED = colors.HexColor('#526579')
DEFAULTS = dict(company='Mi empresa', title='', subtitle='Documentación de API',
                author='', version='1.0', header='', footer='Uso interno', logos=[])


def local_file(value, base):
    """Never fetch URLs; all image resources must be local files."""
    if not isinstance(value, str) or not value or urlsplit(value).scheme or value.startswith('//'):
        raise ValueError(f'Recurso no local o inválido: {value!r}')
    path = (base / unquote(value)).resolve()
    if not path.is_file():
        raise ValueError(f'No existe el recurso local: {path}')
    return path


def load_config(path):
    cfg = DEFAULTS.copy()
    if path:
        raw = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(raw, dict):
            raise ValueError('La configuración debe ser un objeto JSON.')
        unknown = set(raw) - set(cfg)
        if unknown:
            raise ValueError(f'Campos desconocidos: {", ".join(sorted(unknown))}')
        cfg.update(raw)
    for key in set(cfg) - {'logos'}:
        if not isinstance(cfg[key], str):
            raise ValueError(f'{key} debe ser texto.')
    if not isinstance(cfg['logos'], list):
        raise ValueError('logos debe ser una lista de rutas locales.')
    cfg['logos'] = [local_file(p, path.parent) for p in cfg['logos']]
    return cfg


def styles():
    s = getSampleStyleSheet()
    s['BodyText'].fontSize = 10
    s['BodyText'].leading = 15
    s['BodyText'].autoLeading = 'max'
    s['BodyText'].spaceAfter = 7
    s['BodyText'].textColor = INK
    for n in range(1, 7):
        s[f'Heading{n}'].textColor = INK
        s[f'Heading{n}'].spaceBefore = 14
        s[f'Heading{n}'].spaceAfter = 8
    s.add(ParagraphStyle('CoverTitle', fontName='Helvetica-Bold', fontSize=30,
                         leading=36, textColor=INK, spaceAfter=20))
    s.add(ParagraphStyle('CoverSub', parent=s['BodyText'], fontSize=15, leading=22))
    s.add(ParagraphStyle('CodeLine', fontName='Courier', fontSize=8, leading=11,
                         backColor=colors.HexColor('#f0f4f7'), borderPadding=(0, 5, 0, 5),
                         spaceBefore=0, spaceAfter=0, splitLongWords=1))
    s.add(ParagraphStyle('Cell', parent=s['BodyText'], fontSize=8, leading=11,
                         spaceAfter=0))
    s.add(ParagraphStyle('TOC0', parent=s['BodyText'], fontName='Helvetica-Bold',
                         spaceBefore=7, leftIndent=0, firstLineIndent=0))
    for n in (1, 2):
        s.add(ParagraphStyle(f'TOC{n}', parent=s['BodyText'], leftIndent=14*n,
                             firstLineIndent=0, spaceBefore=3))
    return s


def scaled_image(path, width, height):
    img = Image(str(path))
    scale = min(width / img.imageWidth, height / img.imageHeight)
    img.drawWidth = img.imageWidth * scale
    img.drawHeight = img.imageHeight * scale
    img.hAlign = 'LEFT'
    return img


class Document(BaseDocTemplate):
    def __init__(self, target, cfg, s):
        super().__init__(str(target), pagesize=(21*cm, 29.7*cm),
                         leftMargin=2*cm, rightMargin=2*cm,
                         topMargin=2.5*cm, bottomMargin=2.2*cm,
                         title=cfg['title'], author=cfg['author'])
        self.cfg = cfg
        self.addPageTemplates(PageTemplate(id='standard', frames=[Frame(
            self.leftMargin, self.bottomMargin, self.width, self.height,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)],
            onPage=self.decorate))

    def decorate(self, canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(1)
        canvas.line(self.leftMargin, 27.7*cm, 19*cm, 27.7*cm)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(MUTED)
        # Wrap long metadata inside bounded boxes, never across the page number.
        for text, y in [(self.cfg['header'] or self.cfg['company'], 28*cm),
                        (self.cfg['footer'], 1.25*cm)]:
            p = Paragraph(escape(text), ParagraphStyle('chrome', fontSize=8, leading=9))
            _, h = p.wrap(self.width-2*cm, 0.6*cm)
            if h > 0.65*cm:
                raise ValueError('Header/footer demasiado largo: usá hasta dos líneas cortas.')
            p.drawOn(canvas, self.leftMargin, y)
        canvas.drawRightString(19*cm, 1.25*cm, f'Página {doc.page}')
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if hasattr(flowable, 'toc_entry'):
            level, title, key = flowable.toc_entry
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(title, key, level=0, closed=False)
            if level <= 2:
                self.notify('TOCEntry', (level, escape(title), self.page, key))


class Renderer:
    def __init__(self, markdown, base, s, width):
        parser = MarkdownIt('commonmark').enable('table')
        # Route every URL through our stricter local-image / safe-link policy.
        parser.validateLink = lambda _url: True
        self.tokens = parser.parse(markdown)
        self.base, self.s, self.width = base, s, width
        self.anchors = {}
        self.headings = {}
        counts = {}
        for i, t in enumerate(self.tokens):
            if t.type == 'heading_open':
                title = self.tokens[i+1].content
                slug = re.sub(r'[^\w\- ]', '', title.lower()).replace(' ', '-') or 'section'
                count = counts.get(slug, 0)
                key = slug if count == 0 else f'{slug}-{count}'
                while key in self.anchors:
                    count += 1
                    key = f'{slug}-{count}'
                counts[slug] = count+1
                self.anchors[key] = key
                self.headings[i] = (int(t.tag[1:])-1, title, key)

    def inline(self, token):
        out = []
        for t in token.children or []:
            kind = t.type
            if kind in ('text', 'html_inline'):
                out.append(escape(t.content))
            elif kind in ('softbreak', 'hardbreak'):
                out.append('<br/>' if kind == 'hardbreak' else ' ')
            elif kind == 'code_inline':
                out.append(f'<font name="Courier">{escape(t.content)}</font>')
            elif kind in ('strong_open', 'strong_close', 'em_open', 'em_close'):
                tag = 'b' if kind.startswith('strong') else 'i'
                out.append(f'<{tag}>' if kind.endswith('open') else f'</{tag}>')
            elif kind == 'link_open':
                href = t.attrGet('href') or ''
                scheme = urlsplit(href).scheme.lower()
                if href.startswith('#'):
                    href = '#' + unquote(href[1:])
                    if href[1:] not in self.anchors:
                        raise ValueError(f'Ancla inexistente: {href}')
                elif scheme not in ('https', 'http', 'mailto'):
                    raise ValueError(f'Enlace no admitido: {href}')
                out.append(f'<a href="{escape(href, quote=True)}" color="#087e8b">')
            elif kind == 'link_close':
                out.append('</a>')
            elif kind == 'image':
                path = local_file(t.attrGet('src'), self.base)
                img = scaled_image(path, self.width-20, 140)
                out.append(f'<img src="{escape(str(path), quote=True)}" width="{img.drawWidth}" height="{img.drawHeight}"/>')
        return ''.join(out)

    def story(self):
        story, stack = [], []
        i = 0
        while i < len(self.tokens):
            t = self.tokens[i]
            if t.type == 'heading_open':
                level, title, key = self.headings[i]
                p = Paragraph(self.inline(self.tokens[i+1]), self.s[f'Heading{level+1}'])
                p.toc_entry = (level, title, key)
                story.append(p)
                i += 3
                continue
            if t.type in ('bullet_list_open', 'ordered_list_open'):
                stack.append([t.type, int(t.attrGet('start') or 1), False])
            elif t.type in ('bullet_list_close', 'ordered_list_close'):
                stack.pop()
            elif t.type == 'list_item_open':
                stack[-1][2] = True
            elif t.type == 'inline':
                st = self.s['BodyText']
                bullet = None
                if stack:
                    st = ParagraphStyle('list', parent=st, leftIndent=16*len(stack),
                                        bulletIndent=16*(len(stack)-1))
                    if stack[-1][2]:
                        bullet = '•' if stack[-1][0] == 'bullet_list_open' else f'{stack[-1][1]}.'
                        stack[-1][1] += 1
                        stack[-1][2] = False
                story.append(Paragraph(self.inline(t), st, bulletText=bullet))
            elif t.type in ('fence', 'code_block'):
                story.append(Spacer(1, 6))
                for line in t.content.rstrip('\n').split('\n'):
                    # Individual lines remain splittable: huge JSON never becomes one tall box.
                    story.append(Paragraph(escape(line.expandtabs(4)).replace(' ', '&#160;') or '&#160;',
                                           self.s['CodeLine']))
                story.append(Spacer(1, 10))
            elif t.type == 'table_open':
                rows, row = [], []
                while self.tokens[i].type != 'table_close':
                    cell = self.tokens[i]
                    if cell.type == 'tr_open':
                        row = []
                    elif cell.type == 'inline':
                        row.append(Paragraph(self.inline(cell), self.s['Cell']))
                    elif cell.type == 'tr_close':
                        rows.append(row)
                    i += 1
                if rows:
                    table = Table(rows, colWidths=[self.width/len(rows[0])]*len(rows[0]),
                                  repeatRows=1, splitInRow=1, hAlign='LEFT')
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#dcebf1')),
                        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f6f8fa')]),
                        ('GRID', (0,0), (-1,-1), .4, colors.HexColor('#cbd5df')),
                        ('VALIGN', (0,0), (-1,-1), 'TOP'),
                        ('LEFTPADDING', (0,0), (-1,-1), 7),
                        ('RIGHTPADDING', (0,0), (-1,-1), 7),
                        ('TOPPADDING', (0,0), (-1,-1), 7),
                        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
                    ]))
                    story.extend([table, Spacer(1, 10)])
            elif t.type == 'hr':
                story.append(Spacer(1, 12))
            elif t.type == 'html_block':
                story.append(Paragraph(escape(t.content), self.s['BodyText']))
            i += 1
        return story


def convert(source, target, config=None, force=False):
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target or (config and target == Path(config).resolve()):
        raise ValueError('El PDF no puede sobrescribir el Markdown ni la configuración.')
    if source.suffix.lower() not in ('.md', '.markdown'):
        raise ValueError('La entrada debe ser un archivo .md o .markdown.')
    if target.suffix.lower() != '.pdf':
        raise ValueError('La salida debe terminar en .pdf.')
    if target.exists() and not force:
        raise ValueError(f'La salida ya existe: {target}. Usá --force para reemplazarla.')
    cfg = load_config(Path(config).resolve() if config else None)
    cfg['title'] = cfg['title'] or source.stem.replace('-', ' ').replace('_', ' ')
    s = styles()
    doc = Document(target, cfg, s)
    render = Renderer(source.read_text(encoding='utf-8'), source.parent, s, doc.width)
    # Validate all resource references before creating an output file.
    body = render.story()
    logo_images = [scaled_image(p, 6*cm, 2*cm) for p in cfg['logos']]
    story = []
    for img in logo_images:
        story.extend([img, Spacer(1, 14)])
    story.extend([Spacer(1, 2*cm), Paragraph(escape(cfg['company']), s['CoverSub']),
                  Spacer(1, 14), Paragraph(escape(cfg['title']), s['CoverTitle']),
                  Paragraph(escape(cfg['subtitle']), s['CoverSub']), Spacer(1, 24),
                  Paragraph(f'Versión {escape(cfg["version"])}', s['BodyText'])])
    if cfg['author']:
        story.append(Paragraph(f'Autor: {escape(cfg["author"])}', s['BodyText']))
    toc = TableOfContents()
    toc.levelStyles = [s[f'TOC{n}'] for n in range(3)]
    toc.dotsMinLevel = 0
    has_index_entries = any(level <= 2 for level, _, _ in render.headings.values())
    index = toc if has_index_entries else Paragraph('Sin títulos para indexar.', s['BodyText'])
    story.extend([PageBreak(), Paragraph('Índice', s['Heading1']), index, PageBreak(), *body])
    target.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement protects an existing PDF even when layout fails.
    import os
    import tempfile
    fd, temporary = tempfile.mkstemp(suffix='.pdf', dir=target.parent)
    os.close(fd)
    try:
        doc.filename = temporary
        doc.multiBuild(story)
        Path(temporary).replace(target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('markdown', nargs='?', help='Archivo .md (si falta, se pregunta)')
    parser.add_argument('-o', '--output', type=Path)
    parser.add_argument('-c', '--config', type=Path)
    parser.add_argument('--force', action='store_true', help='Reemplazar un PDF existente')
    args = parser.parse_args()
    try:
        value = args.markdown or input('Ruta del archivo Markdown: ').strip()
        if not value:
            raise ValueError('Indicá un archivo Markdown.')
        source = Path(value).expanduser()
        output = args.output or source.with_suffix('.pdf')
        target = convert(source, output, args.config, args.force)
        print(f'PDF creado: {target}')
        return 0
    except (OSError, ValueError, EOFError, KeyboardInterrupt) as exc:
        print(f'Error: {exc or "Operación cancelada"}', file=sys.stderr)
        return 1
    except Exception as exc:
        print(f'Error al generar el PDF: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
