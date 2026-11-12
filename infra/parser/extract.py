"""Untrusted-file subprocess: no network, DB, application imports or credentials."""
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

MAX_OUTPUT = 8 * 1024 * 1024
MAX_PAGES = 200


def extract(path, media):
    segments = []
    ocr = False
    if media == 'application/pdf':
        from pypdf import PdfReader
        reader = PdfReader(path, strict=True)
        if reader.is_encrypted:
            raise ValueError('ENCRYPTED_FILE')
        if len(reader.pages) > MAX_PAGES:
            raise ValueError('TOO_MANY_PAGES')
        for n, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ''
            if len(text.strip()) < 20:
                ocr = True
                with tempfile.TemporaryDirectory() as directory:
                    base = str(Path(directory) / 'page')
                    subprocess.run(['pdftoppm', '-f', str(n), '-l', str(n), '-singlefile',
                                    '-scale-to', '2400', '-png', str(path), base],
                                   check=True, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=30)
                    result = subprocess.run(['tesseract', base+'.png', 'stdout', '-l', 'eng'],
                                            check=True, capture_output=True, timeout=30)
                    text = result.stdout.decode('utf-8')
            segments.append({'page': n, 'text': text})
            if sum(len(s['text']) for s in segments) > MAX_OUTPUT:
                raise ValueError('EXTRACTION_TOO_LARGE')
    elif media.endswith('wordprocessingml.document'):
        with zipfile.ZipFile(path) as archive:
            files = archive.infolist()
            if len(files) > 2000 or sum(f.file_size for f in files) > 50 * 1024 * 1024:
                raise ValueError('UNSAFE_ARCHIVE')
            for f in files:
                name = f.filename.lower()
                if '..' in Path(name).parts or name.startswith('/') or 'vbaproject' in name:
                    raise ValueError('UNSAFE_ARCHIVE')
                if f.flag_bits & 1:
                    raise ValueError('ENCRYPTED_FILE')
                if f.file_size > 10 * 1024 * 1024 or f.file_size > max(f.compress_size,1) * 200:
                    raise ValueError('UNSAFE_ARCHIVE')
                if name.endswith('.rels') and b'targetmode="external"' in archive.read(f).lower():
                    raise ValueError('EXTERNAL_RESOURCE')
        from docx import Document
        document = Document(path)
        heading = None
        for n, paragraph in enumerate(document.paragraphs, 1):
            if paragraph.style.name.startswith('Heading'):
                heading = paragraph.text
            if paragraph.text.strip():
                segments.append({'paragraph':n,'heading':heading,'text':paragraph.text})
        for t, table in enumerate(document.tables, 1):
            for n, row in enumerate(table.rows, 1):
                segments.append({'table':t,'row':n,'text':' | '.join(c.text for c in row.cells)})
    else:
        text = path.read_bytes().decode('utf-8')
        if '\x00' in text:
            raise ValueError('INVALID_TEXT')
        heading = None
        for n, line in enumerate(text.splitlines(), 1):
            if line.startswith('#'):
                heading = line.lstrip('#').strip()
            if line.strip():
                segments.append({'line':n,'heading':heading,'text':line})
    if not segments or not any(s['text'].strip() for s in segments):
        raise ValueError('UNREADABLE_FILE')
    result = {'segments':segments,'ocr':ocr,'extractor_version':'advisory-extractor-0.3'}
    if len(json.dumps(result).encode()) > MAX_OUTPUT:
        raise ValueError('EXTRACTION_TOO_LARGE')
    return result


def main():
    mode, media = sys.argv[1:]
    path = Path('/input/document')
    if mode == 'scan':
        result = subprocess.run(['clamscan','--database=/signatures','--no-summary',
                                 '--alert-exceeds-max=yes','--alert-encrypted=yes','--max-filesize=25M','--max-scansize=60M',str(path)],
                                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=90)
        if result.returncode:
            raise ValueError('UNSAFE_FILE' if result.returncode == 1 else 'SCANNER_UNAVAILABLE')
        return {'clean':True}
    return extract(path,media)


if __name__ == '__main__':
    try:
        print(json.dumps(main()))
    except Exception as exc:
        known = {'ENCRYPTED_FILE','TOO_MANY_PAGES','UNSAFE_ARCHIVE','EXTERNAL_RESOURCE',
                 'EXTRACTION_TOO_LARGE','INVALID_TEXT','UNREADABLE_FILE','UNSAFE_FILE',
                 'SCANNER_UNAVAILABLE'}
        code = str(exc) if isinstance(exc,ValueError) and str(exc) in known else 'EXTRACTION_FAILED'
        print(json.dumps({'error_code':code}))
        sys.exit(1)
