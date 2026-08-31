from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

NS_MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
NS_REL_DOC = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS_REL_PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'


def _col_index(ref: str) -> int:
    letters = re.match(r'([A-Z]+)', ref.upper())
    if not letters:
        return 0
    n = 0
    for ch in letters.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _col_letters(n: int) -> str:
    out = ''
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


class XlsxBook:
    """Small, dependency-free XLSX reader for tabular event exports.

    Reads cached cell values, shared strings and inline strings. Formula cells without
    cached values are returned as None, which is deliberate: the app reconstructs
    the B2C segment from Main + 분류 기준 when spill results are unavailable.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.zf = zipfile.ZipFile(self.path, 'r')
        self.shared = self._read_shared_strings()
        self._sheets = self._read_sheet_map()
        self._cache: dict[str, list[list[Any]]] = {}

    @property
    def sheetnames(self) -> list[str]:
        return list(self._sheets)

    def close(self) -> None:
        self.zf.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _read_shared_strings(self) -> list[str]:
        if 'xl/sharedStrings.xml' not in self.zf.namelist():
            return []
        root = ET.fromstring(self.zf.read('xl/sharedStrings.xml'))
        out = []
        for si in root.findall(f'{{{NS_MAIN}}}si'):
            texts = [t.text or '' for t in si.iter(f'{{{NS_MAIN}}}t')]
            out.append(''.join(texts))
        return out

    def _read_sheet_map(self) -> dict[str, str]:
        wb = ET.fromstring(self.zf.read('xl/workbook.xml'))
        rels = ET.fromstring(self.zf.read('xl/_rels/workbook.xml.rels'))
        rel_map = {}
        for rel in rels.findall(f'{{{NS_REL_PKG}}}Relationship'):
            rel_map[rel.attrib['Id']] = rel.attrib['Target']
        sheets: dict[str, str] = {}
        for sh in wb.find(f'{{{NS_MAIN}}}sheets') or []:
            name = sh.attrib['name']
            rid = sh.attrib.get(f'{{{NS_REL_DOC}}}id')
            target = rel_map.get(rid or '', '')
            if target.startswith('/'):
                target = target.lstrip('/')
            elif not target.startswith('xl/'):
                target = 'xl/' + target.lstrip('./')
            sheets[name] = target
        return sheets

    def rows(self, name: str) -> list[list[Any]]:
        if name in self._cache:
            return self._cache[name]
        target = self._sheets[name]
        root = ET.fromstring(self.zf.read(target))
        sheet_data = root.find(f'{{{NS_MAIN}}}sheetData')
        rows: list[list[Any]] = []
        if sheet_data is None:
            self._cache[name] = rows
            return rows
        for row_el in sheet_data.findall(f'{{{NS_MAIN}}}row'):
            row: list[Any] = []
            for c in row_el.findall(f'{{{NS_MAIN}}}c'):
                ref = c.attrib.get('r', 'A1')
                idx = _col_index(ref)
                while len(row) <= idx:
                    row.append(None)
                cell_type = c.attrib.get('t')
                value: Any = None
                if cell_type == 'inlineStr':
                    is_el = c.find(f'{{{NS_MAIN}}}is')
                    if is_el is not None:
                        value = ''.join((t.text or '') for t in is_el.iter(f'{{{NS_MAIN}}}t'))
                else:
                    v = c.find(f'{{{NS_MAIN}}}v')
                    if v is not None and v.text is not None:
                        raw = v.text
                        if cell_type == 's':
                            try:
                                value = self.shared[int(raw)]
                            except Exception:
                                value = raw
                        elif cell_type == 'b':
                            value = raw == '1'
                        elif cell_type in {'str', 'e'}:
                            value = raw
                        else:
                            try:
                                value = int(raw) if re.fullmatch(r'-?\d+', raw) else float(raw)
                            except Exception:
                                value = raw
                row[idx] = value
            rows.append(row)
        self._cache[name] = rows
        return rows


def count_data_rows(rows: list[list[Any]]) -> int:
    return sum(1 for r in rows[1:] if any(v is not None and str(v).strip() for v in r))


def _cell_xml(ref: str, value: Any, style: int = 0) -> str:
    if value is None or value == '':
        return ''
    s_attr = f' s="{style}"' if style else ''
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"{s_attr}><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"{s_attr}><v>{value}</v></c>'
    text = str(value)
    preserve = ' xml:space="preserve"' if text[:1].isspace() or text[-1:].isspace() or '\n' in text else ''
    return f'<c r="{ref}" t="inlineStr"{s_attr}><is><t{preserve}>{escape(text)}</t></is></c>'


def write_simple_xlsx(path: Path, sheets: list[tuple[str, list[dict[str, Any]]]], fields: list[str]) -> None:
    """Write a human-review XLSX using only stdlib ZIP/XML."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content_types = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
                     '<Default Extension="xml" ContentType="application/xml"/>',
                     '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
                     '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    for i in range(1, len(sheets)+1):
        content_types.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
    content_types.append('</Types>')

    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''

    safe_names=[]
    for name,_ in sheets:
        n = re.sub(r'[\\/*?:\[\]]', '_', name)[:31] or 'Sheet'
        base=n; k=2
        while n in safe_names:
            suffix=f'_{k}'; n=(base[:31-len(suffix)] + suffix); k+=1
        safe_names.append(n)

    wb_sheets = ''.join(f'<sheet name="{escape(n)}" sheetId="{i}" r:id="rId{i}"/>' for i,n in enumerate(safe_names,1))
    workbook_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="{NS_MAIN}" xmlns:r="{NS_REL_DOC}"><sheets>{wb_sheets}</sheets></workbook>'''
    wb_rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
               f'<Relationships xmlns="{NS_REL_PKG}">']
    for i in range(1,len(sheets)+1):
        wb_rels.append(f'<Relationship Id="rId{i}" Type="{NS_REL_DOC}/worksheet" Target="worksheets/sheet{i}.xml"/>')
    wb_rels.append(f'<Relationship Id="rId{len(sheets)+1}" Type="{NS_REL_DOC}/styles" Target="styles.xml"/>')
    wb_rels.append('</Relationships>')

    # Style 0 normal, style 1 dark header with white bold font and wrap.
    styles = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="{NS_MAIN}">
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF111827"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''

    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ''.join(content_types))
        z.writestr('_rels/.rels', root_rels)
        z.writestr('xl/workbook.xml', workbook_xml)
        z.writestr('xl/_rels/workbook.xml.rels', ''.join(wb_rels))
        z.writestr('xl/styles.xml', styles)
        for si, (_name, data) in enumerate(sheets,1):
            # Reasonable widths; email body wider.
            cols=[]
            for ci,f in enumerate(fields,1):
                width = 55 if f == 'email_body' else 28 if f in {'short_rationale','primary_sales_angle','recipient_emails'} else 18
                cols.append(f'<col min="{ci}" max="{ci}" width="{width}" customWidth="1"/>')
            rows_xml=[]
            header_cells=''.join(_cell_xml(f'{_col_letters(ci)}1', f, 1) for ci,f in enumerate(fields))
            rows_xml.append(f'<row r="1" ht="24" customHeight="1">{header_cells}</row>')
            for ri,row in enumerate(data,2):
                cells=''.join(_cell_xml(f'{_col_letters(ci)}{ri}', row.get(f,'')) for ci,f in enumerate(fields))
                rows_xml.append(f'<row r="{ri}">{cells}</row>')
            max_row=max(1,len(data)+1); max_col=_col_letters(max(0,len(fields)-1))
            xml=f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="{NS_MAIN}"><dimension ref="A1:{max_col}{max_row}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>{''.join(cols)}</cols><sheetData>{''.join(rows_xml)}</sheetData><autoFilter ref="A1:{max_col}{max_row}"/></worksheet>'''
            z.writestr(f'xl/worksheets/sheet{si}.xml', xml)
