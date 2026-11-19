"""Stdlib tests for the music catalog check. No network.

Fixtures are built in this module. The example document is the Phase 1
design example (example: true). The production catalog is the link-out for
Forged, Not Born. Fixture helpers still build that link-out with an empty
track list.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.music_catalog.validate import (
    MAX_CATALOG_BYTES,
    SCHEMA_BLOB_SHA,
    SCHEMA_SOURCE_COMMIT,
    main,
    validate_bytes,
    validate_path,
)

REPO = Path(__file__).resolve().parents[2]
SCHEMA_PATH = Path(__file__).with_name("music-catalog.schema.json")
CATALOG_PATH = REPO / "music" / "catalog.json"
WORKFLOW_PATH = REPO / ".github" / "workflows" / "music-catalog-checks.yml"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

# Phase 1 music-catalog.example.json. Real album fields, placeholder tracks.
DESIGN_EXAMPLE = json.loads(
    """
{
  "documentStatus": "Status: Proposal / pending review",
  "schemaVersion": 1,
  "example": true,
  "exampleNotice": "Status: Proposal / pending review. EXAMPLE DATA, not the live catalog and not a file on ferrouslion.com. The album title, Suno URL, Suno share id, and artwork path are the public card from the current site. Track titles are placeholders. The draft release and its playback object are a shape sample: sha256 and bytes describe the UTF-8 string EXAMPLE NOT A FILE, not an MP3. No bucket, hostname, or audio file is claimed.",
  "updatedAt": "2026-11-18T14:38:00Z",
  "releases": [
    {
      "id": "forged-not-born",
      "type": "music-release",
      "title": "Forged, Not Born",
      "releaseKind": "album",
      "status": "published",
      "presentation": "link-out",
      "summary": "",
      "publishedAt": null,
      "externalUrl": "https://suno.com/s/UaKR3kLXhf8arBJf",
      "sunoShareId": "UaKR3kLXhf8arBJf",
      "artwork": {
        "path": "./music/forged-not-born.jpg",
        "alt": "Forged, Not Born album cover by FerrousLion"
      },
      "tracks": [
        {
          "id": "example-track-1",
          "title": "EXAMPLE track 1 (placeholder, not a real song)",
          "trackNumber": 1,
          "durationSeconds": null,
          "example": true
        },
        {
          "id": "example-track-2",
          "title": "EXAMPLE track 2 (placeholder, not a real song)",
          "trackNumber": 2,
          "durationSeconds": null,
          "example": true
        }
      ]
    },
    {
      "id": "example-draft",
      "type": "music-release",
      "title": "EXAMPLE draft (not a real release)",
      "releaseKind": "single",
      "status": "draft",
      "presentation": "stored-only",
      "summary": "Shape sample for a supplied MP3. Not a release and not a file.",
      "publishedAt": null,
      "externalUrl": null,
      "artwork": {
        "path": "./music/example-draft.jpg",
        "alt": "EXAMPLE placeholder artwork path, not a file on the site"
      },
      "tracks": [
        {
          "id": "example-track",
          "title": "EXAMPLE track (placeholder, not a real song)",
          "trackNumber": 1,
          "durationSeconds": null,
          "example": true,
          "playback": {
            "role": "original",
            "suppliedAs": "mp3",
            "container": "mp3",
            "contentType": "audio/mpeg",
            "originalFilename": "example-not-a-song.mp3",
            "key": "playback/example-draft/example-track/2cc57764d0293ab2c3a02d8fb34ace479ac44dbbb514f257b170f23b4b05c299.mp3",
            "bytes": 18,
            "sha256": "2cc57764d0293ab2c3a02d8fb34ace479ac44dbbb514f257b170f23b4b05c299",
            "bitrateKbps": null,
            "bitrateMode": "unknown",
            "sampleRateHz": null,
            "channels": null,
            "backup": {
              "copied": false,
              "locationId": null
            }
          }
        }
      ]
    }
  ]
}
"""
)

DIGEST = hashlib.sha256(b"catalog-policy-test").hexdigest()
SUNO_URL = "https://suno.com/s/UaKR3kLXhf8arBJf"
SHARE_ID = "UaKR3kLXhf8arBJf"


def playback(**overrides: object) -> dict:
    row = {
        "role": "original",
        "suppliedAs": "mp3",
        "container": "mp3",
        "contentType": "audio/mpeg",
        "originalFilename": "forged-track.mp3",
        "key": f"playback/forged-not-born/track-one/{DIGEST}.mp3",
        "bytes": len(b"catalog-policy-test"),
        "sha256": DIGEST,
        "bitrateKbps": None,
        "bitrateMode": "unknown",
        "sampleRateHz": None,
        "channels": None,
        "backup": {"copied": True, "locationId": "backup-label"},
    }
    row.update(overrides)
    return row


def track(**overrides: object) -> dict:
    row = {
        "id": "track-one",
        "title": "Track One",
        "trackNumber": 1,
        "durationSeconds": None,
        "example": False,
    }
    row.update(overrides)
    return row


def release(**overrides: object) -> dict:
    row = {
        "id": "forged-not-born",
        "type": "music-release",
        "title": "Forged, Not Born",
        "releaseKind": "album",
        "status": "published",
        "presentation": "link-out",
        "summary": "",
        "publishedAt": None,
        "externalUrl": SUNO_URL,
        "sunoShareId": SHARE_ID,
        "artwork": {
            "path": "./music/forged-not-born.jpg",
            "alt": "Forged, Not Born album cover by FerrousLion",
        },
        "tracks": [],
    }
    row.update(overrides)
    return row


def catalog(*releases: dict, **overrides: object) -> dict:
    document = {
        "schemaVersion": 1,
        "example": False,
        "updatedAt": "2026-11-18T16:22:00Z",
        "releases": list(releases) if releases else [release()],
    }
    document.update(overrides)
    return document


def check(document: dict, *, role: str = "production", repo_root: Path = REPO) -> list[str]:
    raw = json.dumps(document).encode("utf-8")
    return validate_bytes(raw, role=role, schema=SCHEMA, repo_root=repo_root)


def schema_errors(errors: list[str]) -> list[str]:
    return [error for error in errors if ": schema:" in error]


def policy_errors(errors: list[str]) -> list[str]:
    return [error for error in errors if ": policy:" in error]


class PassingTests(unittest.TestCase):
    def test_vendored_schema_is_the_design_blob(self) -> None:
        data = SCHEMA_PATH.read_bytes()
        digest = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        self.assertEqual(digest, SCHEMA_BLOB_SHA)
        self.assertEqual(SCHEMA_SOURCE_COMMIT, "16011732af824d7b3cf4b2a50272a07309bc983b")
        Draft202012Validator.check_schema(SCHEMA)

    def test_design_example_under_example_role(self) -> None:
        payload = b"EXAMPLE NOT A FILE"
        playback_row = DESIGN_EXAMPLE["releases"][1]["tracks"][0]["playback"]
        self.assertEqual(len(payload), 18)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), playback_row["sha256"])
        errors = check(DESIGN_EXAMPLE, role="example", repo_root=Path("/tmp"))
        self.assertEqual(errors, [])

    def test_production_linkout_with_empty_tracks(self) -> None:
        document = catalog()
        self.assertEqual(document["example"], False)
        self.assertEqual(document["releases"][0]["tracks"], [])
        self.assertEqual(document["releases"][0]["summary"], "")
        self.assertEqual(errors := check(document), [])
        self.assertEqual(document["releases"][0]["externalUrl"], SUNO_URL)

    def test_www_suno_host_and_gap_in_track_numbers(self) -> None:
        document = catalog(
            release(
                externalUrl="https://www.suno.com/s/UaKR3kLXhf8arBJf",
                tracks=[
                    track(trackNumber=1),
                    track(id="track-three", title="Track Three", trackNumber=3),
                ],
            )
        )
        self.assertEqual(check(document), [])

    def test_published_stored_only_with_null_measurements(self) -> None:
        document = catalog(
            release(
                presentation="stored-only",
                tracks=[track(playback=playback())],
            )
        )
        stored = document["releases"][0]["tracks"][0]
        self.assertIsNone(stored["durationSeconds"])
        self.assertIsNone(stored["playback"]["bitrateKbps"])
        self.assertIsNone(stored["playback"]["sampleRateHz"])
        self.assertIsNone(stored["playback"]["channels"])
        self.assertTrue(stored["playback"]["backup"]["copied"])
        self.assertEqual(stored["playback"]["backup"]["locationId"], "backup-label")
        self.assertEqual(check(document), [])

    def test_draft_stored_only_backup_not_copied(self) -> None:
        document = catalog(
            release(
                status="draft",
                presentation="stored-only",
                summary="",
                externalUrl=None,
                tracks=[
                    track(
                        playback=playback(
                            backup={"copied": False, "locationId": None},
                        )
                    )
                ],
            )
        )
        del document["releases"][0]["sunoShareId"]
        self.assertEqual(check(document), [])

    def test_leap_day_and_explicit_offset(self) -> None:
        leap = catalog()
        leap["updatedAt"] = "2024-02-29T00:00:00Z"
        offset = catalog()
        offset["updatedAt"] = "2026-11-18T10:22:00-06:00"
        self.assertEqual(check(leap), [])
        self.assertEqual(check(offset), [])

    def test_example_role_does_not_require_the_artwork_file(self) -> None:
        document = catalog()
        document["example"] = True
        document["documentStatus"] = "Status: Proposal / pending review"
        document["exampleNotice"] = "Labeled example. The artwork path is a shape."
        with tempfile.TemporaryDirectory() as tmp:
            errors = check(document, role="example", repo_root=Path(tmp))
        self.assertEqual(errors, [])

    def test_catalog_of_exactly_one_mib_is_not_over_the_cap(self) -> None:
        raw = b"{" + b" " * (MAX_CATALOG_BYTES - 1)
        self.assertEqual(len(raw), MAX_CATALOG_BYTES)
        errors = validate_bytes(raw, role="production", schema=SCHEMA, repo_root=REPO)
        self.assertFalse(any("1 MiB" in error for error in errors))
        self.assertTrue(any("not JSON" in error for error in errors))


class SchemaFailureTests(unittest.TestCase):
    def test_linkout_track_with_playback(self) -> None:
        document = catalog(release(tracks=[track(playback=playback())]))
        errors = check(document)
        self.assertTrue(schema_errors(errors))
        self.assertTrue(any("must not include playback" in error for error in errors))
        self.assertEqual(policy_errors(errors), [])

    def test_stored_only_track_without_playback(self) -> None:
        document = catalog(release(presentation="stored-only", tracks=[track()]))
        errors = check(document)
        self.assertTrue(any("playback" in error for error in schema_errors(errors)))
        self.assertEqual(policy_errors(errors), [])

    def test_published_stored_only_with_copied_false(self) -> None:
        document = catalog(
            release(
                presentation="stored-only",
                tracks=[
                    track(
                        playback=playback(backup={"copied": False, "locationId": None})
                    )
                ],
            )
        )
        errors = check(document)
        self.assertTrue(schema_errors(errors))
        self.assertTrue(any("copied" in error for error in errors))

    def test_copied_true_with_null_location_id(self) -> None:
        document = catalog(
            release(
                status="draft",
                presentation="stored-only",
                externalUrl=None,
                tracks=[
                    track(playback=playback(backup={"copied": True, "locationId": None}))
                ],
            )
        )
        del document["releases"][0]["sunoShareId"]
        errors = check(document)
        self.assertTrue(any("locationId" in error for error in schema_errors(errors)))
        self.assertEqual(policy_errors(errors), [])

    def test_extra_masters_property(self) -> None:
        document = catalog(release(masters={}))
        errors = check(document)
        self.assertTrue(any("masters" in error for error in schema_errors(errors)))
        self.assertEqual(policy_errors(errors), [])

    def test_supplied_as_wav(self) -> None:
        document = catalog(
            release(
                status="draft",
                presentation="stored-only",
                externalUrl=None,
                tracks=[
                    track(
                        playback=playback(
                            suppliedAs="wav",
                            backup={"copied": False, "locationId": None},
                        )
                    )
                ],
            )
        )
        del document["releases"][0]["sunoShareId"]
        errors = check(document)
        self.assertTrue(any("suppliedAs" in error and "mp3" in error for error in errors))
        self.assertEqual(policy_errors(errors), [])

    def test_artwork_path_with_parent_segment(self) -> None:
        document = catalog(
            release(
                artwork={
                    "path": "./music/../forged-not-born.jpg",
                    "alt": "Forged, Not Born album cover by FerrousLion",
                }
            )
        )
        errors = check(document)
        self.assertTrue(any("artwork" in error for error in schema_errors(errors)))

    def test_external_url_on_r2_dev_is_rejected_without_echoing_it(self) -> None:
        secret_host = "https://pub-marker.r2.dev/object-marker"
        document = catalog(release(externalUrl=secret_host))
        errors = check(document)
        joined = "\n".join(errors)
        self.assertTrue(schema_errors(errors))
        self.assertIn("forbidden pattern matched (r2.dev)", joined)
        self.assertNotIn("pub-marker", joined)
        self.assertNotIn("object-marker", joined)

    def test_single_with_two_tracks(self) -> None:
        document = catalog(
            release(
                releaseKind="single",
                tracks=[track(), track(id="track-two", title="Track Two", trackNumber=2)],
            )
        )
        errors = check(document)
        self.assertTrue(any("maxItems" in error for error in schema_errors(errors)))
        self.assertEqual(policy_errors(errors), [])

    def test_bitrate_set_while_mode_is_unknown(self) -> None:
        document = catalog(
            release(
                presentation="stored-only",
                tracks=[track(playback=playback(bitrateKbps=128, bitrateMode="unknown"))],
            )
        )
        errors = check(document)
        self.assertTrue(any("bitrateMode" in error for error in schema_errors(errors)))
        self.assertEqual(policy_errors(errors), [])

    def test_production_track_title_containing_example(self) -> None:
        document = catalog(release(tracks=[track(title="EXAMPLE track")]))
        errors = check(document)
        self.assertTrue(any("EXAMPLE" in error for error in schema_errors(errors)))

    def test_example_true_under_production_role(self) -> None:
        document = catalog()
        document["example"] = True
        errors = check(document, role="production")
        self.assertTrue(schema_errors(errors))
        self.assertTrue(
            any("requires example to be false" in error for error in policy_errors(errors))
        )


class PolicyFailureTests(unittest.TestCase):
    def test_key_binding(self) -> None:
        other = "a" * 64
        cases = {
            "hash": playback(key=f"playback/forged-not-born/track-one/{other}.mp3"),
            "release id": playback(key=f"playback/other-release/track-one/{DIGEST}.mp3"),
            "track id": playback(key=f"playback/forged-not-born/other-track/{DIGEST}.mp3"),
        }
        for name, row in cases.items():
            with self.subTest(name=name):
                document = catalog(
                    release(presentation="stored-only", tracks=[track(playback=row)])
                )
                errors = check(document)
                self.assertEqual(schema_errors(errors), [])
                self.assertTrue(any("playback/key" in error for error in policy_errors(errors)))

    def test_artwork_slug_must_match_release_id(self) -> None:
        document = catalog(release(id="other-release"))
        errors = check(document)
        self.assertEqual(schema_errors(errors), [])
        self.assertTrue(any("artwork path must be" in error for error in errors))
        self.assertFalse(any("not an existing file" in error for error in errors))

    def test_share_id_must_match_the_url(self) -> None:
        document = catalog(release(sunoShareId="DifferentId1"))
        errors = check(document)
        self.assertEqual(schema_errors(errors), [])
        self.assertTrue(any("sunoShareId must equal" in error for error in errors))

    def test_duplicate_ids_and_track_order(self) -> None:
        duplicate_release = catalog(release(), release())
        duplicate_track = catalog(
            release(
                tracks=[
                    track(),
                    track(title="Track Two", trackNumber=2),
                ]
            )
        )
        duplicate_number = catalog(
            release(
                tracks=[
                    track(),
                    track(id="track-two", title="Track Two", trackNumber=1),
                ]
            )
        )
        unordered = catalog(
            release(
                tracks=[
                    track(trackNumber=2),
                    track(id="track-two", title="Track Two", trackNumber=1),
                ]
            )
        )
        cases = (
            (duplicate_release, "release id is duplicated"),
            (duplicate_track, "track id is duplicated"),
            (duplicate_number, "trackNumber is duplicated"),
            (unordered, "not strictly ascending"),
        )
        for document, text in cases:
            with self.subTest(text=text):
                errors = check(document)
                self.assertEqual(schema_errors(errors), [], errors)
                self.assertTrue(any(text in error for error in errors), errors)

    def test_forbidden_patterns_do_not_echo_the_value(self) -> None:
        samples = (
            ("token=super-secret-value", "token="),
            ("secret=super-secret-value", "secret="),
            ("aws_secret super-secret-value", "aws_secret"),
            ("AKIAsuper-secret-value", "AKIA"),
            ("BEGIN PRIVATE KEY super-secret-value", "BEGIN PRIVATE KEY"),
            ("prefix r2.cloudflarestorage.com super-secret-value", "r2.cloudflarestorage.com"),
            ("prefix r2.dev super-secret-value", "r2.dev"),
            ("Authorization: super-secret-value", "Authorization:"),
            ("data:audio/mpeg;base64,super-secret-value", "data:"),
        )
        for summary, label in samples:
            with self.subTest(label=label):
                document = catalog(release(summary=summary))
                errors = check(document)
                joined = "\n".join(errors)
                self.assertEqual(schema_errors(errors), [], joined)
                self.assertIn(f"forbidden pattern matched ({label})", joined)
                self.assertNotIn("super-secret-value", joined)

    def test_impossible_date_that_matches_the_pattern(self) -> None:
        for stamp in ("2026-02-31T00:00:00Z", "2026-02-29T00:00:00Z", "2026-11-18T24:00:00Z"):
            with self.subTest(stamp=stamp):
                document = catalog()
                document["updatedAt"] = stamp
                errors = check(document)
                self.assertEqual(schema_errors(errors), [])
                self.assertTrue(any("not a real date" in error for error in errors))

    def test_catalog_larger_than_one_mib(self) -> None:
        raw = b"{" + b" " * MAX_CATALOG_BYTES
        self.assertGreater(len(raw), MAX_CATALOG_BYTES)
        errors = validate_bytes(raw, role="production", schema=SCHEMA, repo_root=REPO)
        self.assertTrue(any("larger than 1 MiB" in error for error in errors))
        self.assertTrue(any("not JSON" in error for error in errors))

    def test_script_tag_in_title_summary_and_alt(self) -> None:
        document = catalog(
            release(
                title="Hello </script> secret-title-tail",
                summary="Hello </SCRIPT> secret-summary-tail",
                presentation="stored-only",
                artwork={
                    "path": "./music/forged-not-born.jpg",
                    "alt": "Hello < /script secret-alt-tail",
                },
                tracks=[
                    track(
                        title="Hello </script> secret-track-tail",
                        playback=playback(),
                    )
                ],
            )
        )
        errors = check(document)
        joined = "\n".join(errors)
        self.assertEqual(schema_errors(errors), [], joined)
        self.assertGreaterEqual(joined.count("closing script tag"), 4)
        self.assertNotIn("secret-title-tail", joined)
        self.assertNotIn("secret-summary-tail", joined)
        self.assertNotIn("secret-alt-tail", joined)
        self.assertNotIn("secret-track-tail", joined)

    def test_script_tag_in_filename(self) -> None:
        document = catalog(
            release(
                presentation="stored-only",
                tracks=[track(playback=playback(originalFilename="song</script>.mp3"))],
            )
        )
        errors = check(document)
        self.assertTrue(
            any(
                "originalFilename" in error and "closing script tag" in error
                for error in errors
            )
        )

    def test_path_safety_does_not_echo_the_value(self) -> None:
        samples = (
            ("see ../secret-folder/tape", ".."),
            ("kept-at C:\\secret-folder\\tape", "backslash"),
            ("see file://secret-host/music", "file://"),
            ("kept-at D:/secret-folder/tape", "drive-letter"),
        )
        for summary, label in samples:
            with self.subTest(label=label):
                errors = check(catalog(release(summary=summary)))
                joined = "\n".join(errors)
                self.assertEqual(schema_errors(errors), [], joined)
                self.assertTrue(policy_errors(errors))
                self.assertNotIn("secret-folder", joined)
                self.assertNotIn("secret-host", joined)

    def test_suno_url_is_not_a_drive_letter_path(self) -> None:
        self.assertEqual(check(catalog()), [])

    def test_production_role_rejects_a_schema_valid_example(self) -> None:
        errors = check(copy.deepcopy(DESIGN_EXAMPLE), role="production")
        self.assertEqual(schema_errors(errors), [])
        joined = "\n".join(errors)
        self.assertIn("requires example to be false", joined)
        self.assertIn("containing EXAMPLE", joined)
        self.assertIn("track example to be false", joined)

    def test_example_role_rejects_a_production_document(self) -> None:
        errors = check(catalog(), role="example")
        self.assertEqual(schema_errors(errors), [])
        self.assertTrue(any("requires example to be true" in error for error in errors))

    def test_missing_artwork_file_in_production(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            errors = check(catalog(), repo_root=Path(tmp))
        self.assertEqual(schema_errors(errors), [])
        self.assertTrue(any("not an existing file" in error for error in errors))

    def test_release_title_example_is_policy(self) -> None:
        document = catalog(release(title="EXAMPLE album title"))
        errors = check(document)
        self.assertEqual(schema_errors(errors), [], errors)
        self.assertTrue(any("containing EXAMPLE" in error for error in errors))

    def test_every_failure_is_reported(self) -> None:
        document = catalog(
            release(
                sunoShareId="DifferentId1",
                tracks=[
                    track(trackNumber=2),
                    track(id="track-two", title="Track Two", trackNumber=1),
                ],
            )
        )
        errors = check(document)
        self.assertEqual(schema_errors(errors), [])
        self.assertTrue(any("sunoShareId" in error for error in errors))
        self.assertTrue(any("not strictly ascending" in error for error in errors))


class CliTests(unittest.TestCase):
    def test_production_catalog_command(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.chdir(REPO):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["--catalog", "music/catalog.json", "--role", "production"])
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertIn("music catalog OK (production)", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_cli_prints_each_error_and_exits_1(self) -> None:
        document = catalog(release(summary="token=super-secret-value", sunoShareId="DifferentId1"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.chdir(REPO):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = main(["--catalog", str(path), "--role", "production"])
        text = stderr.getvalue()
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("forbidden pattern matched (token=)", text)
        self.assertIn("sunoShareId must equal", text)
        self.assertNotIn("super-secret-value", text)

    def test_example_file_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "example.json"
            path.write_text(json.dumps(DESIGN_EXAMPLE), encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(
                    ["--catalog", str(path), "--role", "example", "--schema", str(SCHEMA_PATH)]
                )
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertIn("music catalog OK (example)", stdout.getvalue())


class RepositoryTests(unittest.TestCase):
    def test_package_does_not_import_network_clients(self) -> None:
        banned = ("urllib.request", "http.client", "httpx", "requests", "aiohttp", "socket")
        root = Path(__file__).resolve().parent
        for path in root.glob("*.py"):
            if path.name.startswith("test_"):
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not (stripped.startswith("import ") or stripped.startswith("from ")):
                    continue
                for token in banned:
                    self.assertNotIn(token, stripped, f"{path.name}: {stripped}")

    def test_committed_catalog_shape(self) -> None:
        document = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            document,
            {
                "schemaVersion": 1,
                "example": False,
                "updatedAt": "2026-11-19T09:20:00Z",
                "releases": [
                    {
                        "id": "forged-not-born",
                        "type": "music-release",
                        "title": "Forged, Not Born",
                        "releaseKind": "album",
                        "status": "published",
                        "presentation": "link-out",
                        "summary": "",
                        "publishedAt": None,
                        "externalUrl": SUNO_URL,
                        "sunoShareId": SHARE_ID,
                        "artwork": {
                            "path": "./music/forged-not-born.jpg",
                            "alt": "Forged, Not Born album cover by FerrousLion",
                        },
                        "tracks": [
                            {
                                "id": "from-the-first-drop",
                                "title": "From the First Drop",
                                "trackNumber": 1,
                                "durationSeconds": 220,
                                "example": False,
                            },
                            {
                                "id": "five-stars-flashing",
                                "title": "Five Stars Flashing",
                                "trackNumber": 2,
                                "durationSeconds": 186,
                                "example": False,
                            },
                            {
                                "id": "forged-not-born",
                                "title": "Forged, Not Born",
                                "trackNumber": 3,
                                "durationSeconds": 182,
                                "example": False,
                            },
                        ],
                    }
                ],
            },
        )
        text = CATALOG_PATH.read_text(encoding="utf-8").casefold()
        for needle in ("r2.dev", "cloudflarestorage", "drive.google.com", "file://", "akia"):
            self.assertNotIn(needle, text)
        errors = validate_path(
            CATALOG_PATH,
            role="production",
            schema_path=SCHEMA_PATH,
            repo_root=REPO,
        )
        self.assertEqual(errors, [])

    def test_workflow_is_read_only(self) -> None:
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("pull_request:", text)
        self.assertIn("push:", text)
        self.assertIn("contents: read", text)
        self.assertIn("actions/checkout@v4", text)
        self.assertIn("actions/setup-python@v5", text)
        self.assertIn('python-version: "3.12"', text)
        self.assertEqual(text.count("uses:"), 2)
        self.assertNotIn("secrets:", text)
        folded = text.casefold()
        for needle in ("r2.dev", "cloudflarestorage", "drive.google.com"):
            self.assertNotIn(needle, folded)


if __name__ == "__main__":
    unittest.main()
