"""Validate a music catalog file. Nothing in this module opens a socket.

Layer 1 is the vendored JSON Schema (draft 2020-12). Layer 2 is the policy
checks the schema cannot express. URLs are parsed and compared. They are not
fetched. A failure names the field and the rule. A secret-shaped value is not
printed back.

Vendored schema, unchanged, from ferrouslion/royal-council-docs
projects/ferrouslion-com/phase-1/music-catalog.schema.json
blob 61a00d455a032961c3b594a519962cff28fff685
at commit 16011732af824d7b3cf4b2a50272a07309bc983b.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

# Blob SHA of the vendored music-catalog.schema.json in royal-council-docs.
SCHEMA_BLOB_SHA = "61a00d455a032961c3b594a519962cff28fff685"
SCHEMA_SOURCE_COMMIT = "16011732af824d7b3cf4b2a50272a07309bc983b"

DEFAULT_SCHEMA = Path(__file__).with_name("music-catalog.schema.json")
MAX_CATALOG_BYTES = 1024 * 1024
ARTWORK_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "webp"})

# Same closing-script rule as scripts/rumble_vods/validate.py.
_SCRIPT_CLOSE_RE = re.compile(r"<\s*/\s*script", re.IGNORECASE)
_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
# A drive letter is "C:/" or "C:\". The lookbehind keeps "https://" from matching.
_DRIVE_LETTER_RE = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]")

# (casefolded needle, label printed instead of the matched text)
_FORBIDDEN = (
    ("token=", "token="),
    ("secret=", "secret="),
    ("aws_secret", "aws_secret"),
    ("akia", "AKIA"),
    ("begin openssh private key", "BEGIN OPENSSH PRIVATE KEY"),
    ("begin private key", "BEGIN PRIVATE KEY"),
    ("r2.cloudflarestorage.com", "r2.cloudflarestorage.com"),
    ("r2.dev", "r2.dev"),
    ("authorization:", "Authorization:"),
)


def json_pointer(parts: list[object]) -> str:
    """RFC 6901 pointer. The document root is ``/``."""
    if not parts:
        return "/"
    escaped = []
    for part in parts:
        text = str(part).replace("~", "~0").replace("/", "~1")
        escaped.append(text)
    return "/" + "/".join(escaped)


def _forbidden_labels(value: str) -> list[str]:
    folded = value.casefold()
    labels = [label for needle, label in _FORBIDDEN if needle in folded]
    if folded.startswith("data:"):
        labels.append("data:")
    return labels


def _schema_detail(error: object) -> str:
    """Short schema message. Never repeats a secret-shaped instance."""
    validator = getattr(error, "validator", "schema")
    schema = getattr(error, "schema", None)
    inner = schema.get("not") if isinstance(schema, dict) else None
    if validator == "not" and inner == {"required": ["playback"]}:
        return "not: link-out track must not include playback"
    message = " ".join(str(getattr(error, "message", "")).split())
    instance = getattr(error, "instance", None)
    secret = bool(_forbidden_labels(message)) or (
        isinstance(instance, str) and bool(_forbidden_labels(instance))
    )
    if secret or len(message) > 240:
        return f"{validator} rejected the value"
    return f"{validator}: {message}"


def _load_schema(path: Path) -> tuple[object | None, list[str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, [f"/: schema: could not read schema file ({exc.__class__.__name__})"]
    try:
        return json.loads(text), []
    except json.JSONDecodeError:
        return None, ["/: schema: schema file is not JSON"]


def _schema_errors(document: object, schema: object) -> list[str]:
    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError
    except ImportError:
        return ["/: schema: jsonschema is not installed at the pinned version"]
    try:
        validator = Draft202012Validator(schema)
    except SchemaError:
        return ["/: schema: vendored schema was rejected"]
    errors = []
    for error in validator.iter_errors(document):
        pointer = json_pointer(list(error.absolute_path))
        errors.append(f"{pointer}: schema: {_schema_detail(error)}")
    return errors


def _timestamp_problem(value: str) -> str | None:
    """Return a rule name when a timestamp-shaped string is not a real instant."""
    if _TIMESTAMP_RE.fullmatch(value) is None:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return "timestamp matches the pattern but is not a real date"
    if parsed.tzinfo is None:
        return "timestamp has no timezone"
    return None


def _string_policy(value: str, pointer: str) -> list[str]:
    errors = []
    for label in _forbidden_labels(value):
        errors.append(f"{pointer}: policy: forbidden pattern matched ({label})")
    if ".." in value:
        errors.append(f"{pointer}: policy: text contains '..'")
    if "\\" in value:
        errors.append(f"{pointer}: policy: text contains a backslash")
    if "file://" in value.casefold():
        errors.append(f"{pointer}: policy: text contains 'file://'")
    if _DRIVE_LETTER_RE.search(value):
        errors.append(f"{pointer}: policy: text contains a drive-letter path")
    timestamp = _timestamp_problem(value)
    if timestamp:
        errors.append(f"{pointer}: policy: {timestamp}")
    return errors


def _walk_strings(value: object, parts: list[object], errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                # The key itself can carry a forbidden pattern. Omit it from the pointer.
                for label in _forbidden_labels(key):
                    errors.append(
                        f"{json_pointer(parts)}: policy: forbidden pattern matched "
                        f"in an object key ({label})"
                    )
                if ".." in key or "\\" in key or "file://" in key.casefold():
                    errors.append(
                        f"{json_pointer(parts)}: policy: object key is not a safe path"
                    )
            child = parts + [key]
            _walk_strings(item, child, errors)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _walk_strings(item, parts + [index], errors)
        return
    if isinstance(value, str):
        errors.extend(_string_policy(value, json_pointer(parts)))


def _script_problem(value: object, pointer: str) -> str | None:
    if isinstance(value, str) and _SCRIPT_CLOSE_RE.search(value):
        return f"{pointer}: policy: text cannot contain a closing script tag"
    return None


def _last_segment(url: object) -> str | None:
    if not isinstance(url, str) or not url:
        return None
    segment = urlsplit(url).path.rstrip("/").split("/")[-1]
    return segment or None


def _artwork_bound(release_id: object, path: object) -> bool:
    if not isinstance(release_id, str) or not isinstance(path, str):
        return False
    prefix = f"./music/{release_id}."
    if not path.startswith(prefix):
        return False
    return path[len(prefix) :] in ARTWORK_EXTENSIONS


def _artwork_file_problem(path: str, repo_root: Path, pointer: str) -> str | None:
    relative = path[2:] if path.startswith("./") else path
    root = repo_root.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return f"{pointer}: policy: artwork path is not inside the repository"
    if not candidate.is_file():
        return f"{pointer}: policy: artwork file is not an existing file in the repository"
    return None


def _check_tracks(
    release: dict,
    release_index: int,
    release_id: object,
    *,
    role: str,
    errors: list[str],
) -> None:
    tracks = release.get("tracks")
    if not isinstance(tracks, list):
        return
    seen_ids: dict[str, int] = {}
    seen_numbers: dict[int, int] = {}
    numbers: list[int] = []
    for index, track in enumerate(tracks):
        prefix = f"/releases/{release_index}/tracks/{index}"
        if not isinstance(track, dict):
            errors.append(f"{prefix}: policy: track must be an object")
            continue
        track_id = track.get("id")
        if isinstance(track_id, str):
            if track_id in seen_ids:
                errors.append(f"{prefix}/id: policy: track id is duplicated")
            else:
                seen_ids[track_id] = index
        number = track.get("trackNumber")
        if isinstance(number, int) and not isinstance(number, bool):
            numbers.append(number)
            if number in seen_numbers:
                errors.append(f"{prefix}/trackNumber: policy: trackNumber is duplicated")
            else:
                seen_numbers[number] = index
        title = track.get("title")
        if role == "production" and isinstance(title, str) and "EXAMPLE" in title:
            errors.append(f"{prefix}/title: policy: role production rejects a title containing EXAMPLE")
        if role == "production" and track.get("example") is True:
            errors.append(f"{prefix}/example: policy: role production requires track example to be false")
        script = _script_problem(title, f"{prefix}/title")
        if script:
            errors.append(script)
        playback = track.get("playback")
        if isinstance(playback, dict):
            filename = playback.get("originalFilename")
            script = _script_problem(filename, f"{prefix}/playback/originalFilename")
            if script:
                errors.append(script)
            if "key" in playback:
                expected = None
                sha256 = playback.get("sha256")
                if isinstance(release_id, str) and isinstance(track_id, str) and isinstance(sha256, str):
                    expected = f"playback/{release_id}/{track_id}/{sha256}.mp3"
                if playback.get("key") != expected:
                    errors.append(
                        f"{prefix}/playback/key: policy: key must be "
                        "playback/<release.id>/<track.id>/<sha256>.mp3"
                    )
    if any(left >= right for left, right in zip(numbers, numbers[1:])):
        errors.append(
            f"/releases/{release_index}/tracks: policy: trackNumber values are not strictly ascending"
        )


def _check_release(
    release: object,
    index: int,
    seen_ids: dict[str, int],
    *,
    role: str,
    repo_root: Path,
    errors: list[str],
) -> None:
    pointer = f"/releases/{index}"
    if not isinstance(release, dict):
        errors.append(f"{pointer}: policy: release must be an object")
        return
    release_id = release.get("id")
    if isinstance(release_id, str):
        if release_id in seen_ids:
            errors.append(f"{pointer}/id: policy: release id is duplicated")
        else:
            seen_ids[release_id] = index
    title = release.get("title")
    if role == "production" and isinstance(title, str) and "EXAMPLE" in title:
        errors.append(f"{pointer}/title: policy: role production rejects a title containing EXAMPLE")
    for field in ("title", "summary"):
        script = _script_problem(release.get(field), f"{pointer}/{field}")
        if script:
            errors.append(script)
    artwork = release.get("artwork")
    path = artwork.get("path") if isinstance(artwork, dict) else None
    alt = artwork.get("alt") if isinstance(artwork, dict) else None
    if isinstance(artwork, dict):
        script = _script_problem(alt, f"{pointer}/artwork/alt")
        if script:
            errors.append(script)
        if "path" in artwork and not _artwork_bound(release_id, path):
            errors.append(
                f"{pointer}/artwork/path: policy: artwork path must be "
                "./music/<release.id>.jpg, .jpeg, .png, or .webp"
            )
        if role == "production" and isinstance(path, str):
            file_problem = _artwork_file_problem(path, repo_root, f"{pointer}/artwork/path")
            if file_problem:
                errors.append(file_problem)
    if "sunoShareId" in release or isinstance(release.get("externalUrl"), str):
        share = release.get("sunoShareId")
        segment = _last_segment(release.get("externalUrl"))
        if not isinstance(share, str) or share != segment:
            errors.append(
                f"{pointer}/sunoShareId: policy: sunoShareId must equal "
                "the last path segment of externalUrl"
            )
    _check_tracks(release, index, release_id, role=role, errors=errors)


def policy_errors(document: object, *, role: str, repo_root: Path) -> list[str]:
    """Python rules from the validation design. Schema errors are separate."""
    errors: list[str] = []
    if role not in ("production", "example"):
        errors.append("/: policy: role must be production or example")
        return errors
    if not isinstance(document, dict):
        errors.append("/: policy: catalog must be a JSON object")
        return errors
    example = document.get("example")
    if role == "production" and example is not False:
        errors.append("/example: policy: role production requires example to be false")
    if role == "example" and example is not True:
        errors.append("/example: policy: role example requires example to be true")
    _walk_strings(document, [], errors)
    releases = document.get("releases")
    if not isinstance(releases, list):
        return errors
    seen_ids: dict[str, int] = {}
    for index, release in enumerate(releases):
        _check_release(
            release,
            index,
            seen_ids,
            role=role,
            repo_root=repo_root,
            errors=errors,
        )
    return errors


def validate_bytes(
    raw: bytes,
    *,
    role: str,
    schema: object,
    repo_root: Path,
) -> list[str]:
    """Validate catalog bytes. Every problem is returned; none is dropped."""
    errors: list[str] = []
    if len(raw) > MAX_CATALOG_BYTES:
        errors.append(
            f"/: policy: catalog file is {len(raw)} bytes, "
            f"larger than 1 MiB ({MAX_CATALOG_BYTES} bytes)"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        errors.append("/: policy: catalog file is not UTF-8 text")
        return errors
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        errors.append(f"/: policy: catalog file is not JSON ({exc.msg})")
        return errors
    errors.extend(_schema_errors(document, schema))
    errors.extend(policy_errors(document, role=role, repo_root=repo_root))
    return errors


def validate_path(
    catalog_path: Path,
    *,
    role: str,
    schema_path: Path | None = None,
    repo_root: Path | None = None,
) -> list[str]:
    """Validate a catalog file. ``repo_root`` is the site repository root."""
    root = repo_root if repo_root is not None else Path.cwd()
    schema_file = schema_path if schema_path is not None else DEFAULT_SCHEMA
    if not catalog_path.is_file():
        return [f"/: policy: catalog file does not exist ({catalog_path.name})"]
    schema, schema_problems = _load_schema(schema_file)
    if schema_problems:
        return schema_problems
    raw = catalog_path.read_bytes()
    return validate_bytes(raw, role=role, schema=schema, repo_root=root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a music catalog JSON file.")
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--role", required=True, choices=("production", "example"))
    args = parser.parse_args(argv)
    errors = validate_path(
        Path(args.catalog),
        role=args.role,
        schema_path=Path(args.schema),
        repo_root=Path.cwd(),
    )
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"music catalog OK ({args.role})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
