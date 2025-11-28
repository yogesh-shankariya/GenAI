#!/usr/bin/env python3
"""
qr_transfer.py
================

This script provides a simple way to transfer files between two machines by
encoding them into a series of QR code images and later reconstructing the
original files by decoding those images.  It supports both binary and text
files and preserves each file's relative location within a source
directory.  The script is designed for situations where devices cannot
communicate directly (for example, when the target machine is air‑gapped) and
where a camera can be used to capture QR codes.

Rationale
---------

According to the QR Code specification, a version‑40 symbol with low
error‑correction can store up to 2 953 bytes of data when using the 8‑bit
"byte" mode【101672083927264†L684-L697】【742050614598919†L175-L182】.  To remain
within this limit and provide a safety margin for metadata and error
correction, this script splits files into smaller chunks (by default
approximately 2 000 bytes of base64‑encoded text) before encoding them as
QR codes.  This chunk size can be adjusted via the command‑line interface.

Dependencies
------------

The encoding functionality uses the `qrcode` and `Pillow` packages.  For
decoding, the script relies on `pyzbar` (which provides bindings to the
zbar barcode reader) and `Pillow`.  You can install the required
dependencies with::

    pip install qrcode[pil] pyzbar pillow

Usage
-----

### Encoding

To encode an entire directory of files into QR codes, run::

    python qr_transfer.py encode \
      --source /path/to/repo \
      --output /path/to/qr_output \
      --exclude .git --exclude node_modules \
      --chunk-size 2000

This will walk the directory tree rooted at ``/path/to/repo``, skipping
any directory whose name matches the patterns provided with the
``--exclude`` option.  Every file is read in binary, base64 encoded to
ASCII, split into chunks of roughly ``chunk_size`` characters, and then
encoded into QR code images saved under ``/path/to/qr_output``.  The
generated image names are derived from the original file path and
include the chunk index and total number of chunks.

### Decoding

Once you have scanned the QR code images on the target machine and saved
them into a directory (for example by using a phone camera and copying
the images over USB), you can reconstruct the original files with::

    python qr_transfer.py decode \
      --input /path/to/scanned_images \
      --output /path/to/reconstructed_repo

The decoder reads every image in the ``input`` directory, extracts
metadata and chunk contents from the QR codes, sorts the chunks for
each file, concatenates them, base64 decodes the content back to
bytes, and writes the resulting files to their relative locations under
``/path/to/reconstructed_repo``.  If any chunks are missing or duplicated,
the decoder prints warnings.

This tool does not attempt to hide or encrypt your data.  If you are
transferring sensitive information, consider encrypting files before
encoding them.  Also be aware that transferring large repositories with
QR codes can require hundreds or thousands of images, which is
time‑consuming.  When possible, it is usually faster and more reliable to
copy data via removable storage (USB drives, external hard disks) or over
network protocols such as SSH/SCP or Git.
"""

import argparse
import base64
import os
from pathlib import Path
import re
import sys
from typing import Dict, Iterable, List, Optional, Tuple

# Third‑party imports.  These are only loaded when needed so that users
# who only perform encoding or decoding can install the appropriate
# dependencies.
try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_L
    from PIL import Image
except ImportError:
    qrcode = None  # type: ignore
    ERROR_CORRECT_L = None  # type: ignore
    Image = None  # type: ignore


def sanitize_filename(path: Path) -> str:
    """Return a filesystem‑safe name derived from a relative path.

    Path separators and unsafe characters are replaced with underscores.
    The original extension is preserved where possible.
    """
    # Replace any character that is not alphanumeric, dot or underscore
    sanitized = re.sub(r"[^A-Za-z0-9_.]", "_", str(path))
    return sanitized


def split_text(text: str, max_chars: int) -> List[str]:
    """Split ``text`` into a list of substrings each at most
    ``max_chars`` characters long.  Returns at least one chunk (the
    original string if it is shorter than ``max_chars``).
    """
    chunks = []
    for i in range(0, len(text), max_chars):
        chunks.append(text[i : i + max_chars])
    if not chunks:
        chunks.append("")
    return chunks


def encode_directory(
    source_dir: Path,
    output_dir: Path,
    excludes: Iterable[str],
    chunk_size: int = 2000,
    error_correction: Optional[str] = None,
) -> None:
    """Encode every file in ``source_dir`` into QR code images.

    :param source_dir: The root of the directory tree to encode.
    :param output_dir: Directory where QR code images will be saved.  It will
        be created if it does not exist.
    :param excludes: Iterable of glob patterns representing directory names or
        relative paths to exclude from processing (e.g., '.git', 'build').
    :param chunk_size: Maximum number of characters in the base64‑encoded
        payload for each QR code (metadata adds a small overhead).  This
        defaults to 2 000 to leave margin under the ~2 953‑byte capacity
        limit【101672083927264†L684-L697】【742050614598919†L175-L182】.
    :param error_correction: String representing the error correction level
        ('L', 'M', 'Q', or 'H').  Defaults to 'L' for highest capacity.
    """
    if qrcode is None or Image is None:
        raise RuntimeError(
            "Missing dependency: install 'qrcode[pil]' and 'pillow' to use the encoder."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    error_level_map = {
        'L': qrcode.constants.ERROR_CORRECT_L,
        'M': qrcode.constants.ERROR_CORRECT_M,
        'Q': qrcode.constants.ERROR_CORRECT_Q,
        'H': qrcode.constants.ERROR_CORRECT_H,
    }
    err_corr = error_level_map.get((error_correction or 'L').upper(), qrcode.constants.ERROR_CORRECT_L)

    for root, dirs, files in os.walk(source_dir):
        # Determine relative path to source_dir
        rel_root = Path(root).relative_to(source_dir)
        # Remove excluded directories in place
        dirs[:] = [d for d in dirs if not any(Path(rel_root, d).match(pattern) for pattern in excludes)]
        # Process files
        for file_name in files:
            rel_path = Path(rel_root, file_name)
            # Skip hidden files by default?  Only skip if pattern matches
            if any(rel_path.match(pattern) for pattern in excludes):
                continue
            abs_path = source_dir / rel_path
            # Read file bytes and encode to base64
            with open(abs_path, 'rb') as f:
                data_bytes = f.read()
            b64_text = base64.b64encode(data_bytes).decode('ascii')
            chunks = split_text(b64_text, chunk_size)
            num_chunks = len(chunks)
            sanitized = sanitize_filename(rel_path)
            digits = len(str(num_chunks))
            for idx, chunk in enumerate(chunks, start=1):
                # Prepend metadata: original relative path, index, total
                payload = f"{rel_path}|{idx}|{num_chunks}|{chunk}"
                qr = qrcode.QRCode(
                    version=None,  # let qrcode determine minimal version
                    error_correction=err_corr,
                    box_size=10,
                    border=4,
                )
                qr.add_data(payload)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                out_name = f"{sanitized}-chunk-{str(idx).zfill(digits)}-of-{num_chunks}.png"
                img_path = output_dir / out_name
                img.save(img_path)
                print(f"Created {img_path} for {rel_path} chunk {idx}/{num_chunks}")


def decode_directory(input_dir: Path, output_dir: Path) -> None:
    """Decode QR code images in ``input_dir`` and reconstruct files.

    The function expects that each image in ``input_dir`` contains a QR code
    with a payload formatted as ``<relative_path>|<index>|<total>|<base64>``.  The
    decoder groups chunks by ``relative_path`` and writes the decoded
    content to ``output_dir/relative_path``.
    """
    if Image is None:
        raise RuntimeError(
            "Missing dependency: install 'pillow' and 'pyzbar' to use the decoder."
        )
    try:
        from pyzbar.pyzbar import decode as qr_decode
    except ImportError as exc:
        raise RuntimeError("Missing dependency: install 'pyzbar' to decode QR codes") from exc

    # Map from relative path to {index: (total, chunk_str)}
    file_chunks: Dict[str, Dict[int, Tuple[int, str]]] = {}

    image_files = [f for f in input_dir.iterdir() if f.is_file() and f.suffix.lower() in {'.png', '.jpg', '.jpeg'}]
    for img_file in image_files:
        try:
            img = Image.open(img_file)
        except Exception as e:
            print(f"Warning: could not open {img_file}: {e}", file=sys.stderr)
            continue
        codes = qr_decode(img)
        if not codes:
            print(f"Warning: no QR code found in {img_file}", file=sys.stderr)
            continue
        # decode each code found (there could be multiple, but we expect one per image)
        for code in codes:
            try:
                payload = code.data.decode('utf-8')
            except Exception:
                # fallback to Latin‑1
                payload = code.data.decode('latin1')
            parts = payload.split('|', 3)
            if len(parts) != 4:
                print(f"Warning: payload format invalid in {img_file}: {payload}", file=sys.stderr)
                continue
            rel_path_str, idx_str, total_str, chunk_data = parts
            try:
                idx = int(idx_str)
                total = int(total_str)
            except ValueError:
                print(f"Warning: invalid chunk index/total in {img_file}: {payload}", file=sys.stderr)
                continue
            file_entry = file_chunks.setdefault(rel_path_str, {})
            # store (total, chunk_data) for this index
            if idx in file_entry:
                # duplicate chunk
                print(f"Notice: duplicate chunk {idx} for {rel_path_str} from {img_file}", file=sys.stderr)
            file_entry[idx] = (total, chunk_data)

    # reconstruct files
    for rel_path_str, chunks_map in file_chunks.items():
        total_counts = {total for (_, (total, _)) in chunks_map.items()}
        # Ideally there is only one total
        if len(total_counts) != 1:
            print(f"Warning: inconsistent total counts for {rel_path_str}", file=sys.stderr)
            total = max(total_counts)
        else:
            total = total_counts.pop()
        # Check for missing chunks
        missing = [i for i in range(1, total + 1) if i not in chunks_map]
        if missing:
            print(f"Warning: missing chunks {missing} for {rel_path_str}", file=sys.stderr)
        # Order chunks by index
        ordered = [chunks_map[i][1] for i in sorted(chunks_map)]
        # Concatenate and decode base64
        b64_text = ''.join(ordered)
        try:
            data = base64.b64decode(b64_text)
        except Exception as e:
            print(f"Error: failed to base64 decode {rel_path_str}: {e}", file=sys.stderr)
            continue
        # Write file
        out_path = output_dir / rel_path_str
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'wb') as f:
            f.write(data)
        print(f"Reconstructed {out_path} ({len(data)} bytes)")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Encode or decode files to/from QR code images for air‑gapped transfer."
    )
    subparsers = parser.add_subparsers(dest='command', required=True)
    # Encode subcommand
    enc_parser = subparsers.add_parser('encode', help='Encode a directory into QR code images')
    enc_parser.add_argument('--source', required=True, type=Path, help='Directory to encode')
    enc_parser.add_argument('--output', required=True, type=Path, help='Directory to save QR images')
    enc_parser.add_argument(
        '--exclude', '-x', action='append', default=[],
        help='Relative path or glob pattern to exclude (may be provided multiple times)'
    )
    enc_parser.add_argument(
        '--chunk-size', type=int, default=2000,
        help='Maximum characters of base64 payload per QR code (default 2000)'
    )
    enc_parser.add_argument(
        '--error-correction', choices=['L', 'M', 'Q', 'H'], default='L',
        help='QR code error correction level (default L for highest capacity)'
    )

    # Decode subcommand
    dec_parser = subparsers.add_parser('decode', help='Decode QR code images and reconstruct files')
    dec_parser.add_argument('--input', required=True, type=Path, help='Directory containing scanned QR images')
    dec_parser.add_argument('--output', required=True, type=Path, help='Directory to write reconstructed files')

    args = parser.parse_args(argv)
    if args.command == 'encode':
        encode_directory(args.source, args.output, args.exclude, args.chunk_size, args.error_correction)
    elif args.command == 'decode':
        decode_directory(args.input, args.output)
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == '__main__':  # pragma: no cover
    sys.exit(main())
