from __future__ import annotations

import re


def parse_multipart_form(body: bytes, content_type: str) -> tuple[dict[str, str], list[tuple[str, str, bytes]]]:
    match = re.search(r"boundary=([^;\s]+)", content_type, flags=re.IGNORECASE)
    if not match:
        raise ValueError("Multipart boundary is required.")
    boundary = match.group(1).strip().strip('"').encode("ascii")
    delimiter = b"--" + boundary
    fields: dict[str, str] = {}
    files: list[tuple[str, str, bytes]] = []
    for part in body.split(delimiter):
        chunk = part.strip(b"\r\n")
        if not chunk or chunk == b"--":
            continue
        header_blob, _, payload = chunk.partition(b"\r\n\r\n")
        if not header_blob:
            continue
        headers = header_blob.decode("utf-8", errors="replace")
        disposition = ""
        part_content_type = "application/octet-stream"
        for line in headers.split("\r\n"):
            if line.lower().startswith("content-disposition:"):
                disposition = line
            if line.lower().startswith("content-type:"):
                part_content_type = line.split(":", 1)[1].strip()
        name_match = re.search(r'name="([^"]+)"', disposition)
        if not name_match:
            continue
        name = name_match.group(1)
        filename_match = re.search(r'filename="([^"]*)"', disposition)
        content = payload.rstrip(b"\r\n")
        if filename_match is not None:
            files.append((name, filename_match.group(1) or "document", content))
        else:
            fields[name] = content.decode("utf-8")
    return fields, files
