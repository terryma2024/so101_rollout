"""Inspect image size, create bounded previews, hash evidence, or explicitly print PDFs."""
import argparse
import hashlib
import subprocess
from pathlib import Path

from PIL import Image
from .common import write_json


def preview(source, output, max_edge=1600):
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve():
        raise ValueError('preview must not replace the original')
    if output.exists():
        raise FileExistsError(output)
    if max_edge < 1 or max_edge > 1600:
        raise ValueError('preview long edge must be between 1 and 1600')
    with Image.open(source) as original:
        original_size = list(original.size)  # Inspect before loading full pixels.
        im = original.copy()
    im.thumbnail((max_edge, max_edge))
    output.parent.mkdir(parents=True, exist_ok=True)
    im.save(output)
    return {'source': str(source), 'original_size': original_size,
            'preview': str(output), 'preview_size': list(im.size)}


def manifest(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    files = []
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise ValueError(f'symlink not supported in source manifest: {p}')
        if p.is_file() and p != output:
            with p.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            files.append({'path': str(p.relative_to(root)), 'bytes': p.stat().st_size, 'sha256': digest})
    write_json(output, {'root': str(root), 'files': files})
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    size = sub.add_parser('size'); size.add_argument('image', type=Path)
    prev = sub.add_parser('preview'); prev.add_argument('image', type=Path); prev.add_argument('output', type=Path)
    sha = sub.add_parser('manifest'); sha.add_argument('root', type=Path); sha.add_argument('output', type=Path)
    pr = sub.add_parser('print'); pr.add_argument('--printer', required=True); pr.add_argument('pdfs', nargs='+', type=Path)
    args = parser.parse_args()
    if args.command == 'size':
        with Image.open(args.image) as im:
            print({'path': str(args.image), 'size': im.size})
    elif args.command == 'preview':
        print(preview(args.image, args.output))
    elif args.command == 'manifest':
        print(f'{len(manifest(args.root, args.output))} files hashed')
    else:
        for pdf in args.pdfs:
            if not pdf.is_file() or pdf.suffix.lower() != '.pdf':
                parser.error(f'not a PDF file: {pdf}')
        # No shell and no automatic print from any renderer. Colour preserves warnings.
        subprocess.run(['lp', '-d', args.printer, '-n', '1', '-o', 'media=A4', '-o',
                        'sides=one-sided', '-o', 'print-color-mode=color', '-o', 'ColorModel=RGB',
                        '--', *map(str, args.pdfs)], check=True)


if __name__ == '__main__':
    main()
