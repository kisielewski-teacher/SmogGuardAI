import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _tuple(v):
    return tuple(int(x) for x in v.split("."))


def _changelog_versions():
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    return re.findall(r"^## \[(\d+\.\d+\.\d+)\]", text, flags=re.M)


def test_version_file_is_semver_and_matches_latest_changelog_entry():
    version = (REPO / "VERSION").read_text(encoding="utf-8").strip()
    assert SEMVER.match(version), f"VERSION '{version}' nie ma postaci X.Y.Z"
    versions = _changelog_versions()
    assert versions, "CHANGELOG.md nie ma zadnego wpisu '## [X.Y.Z]'"
    assert versions[0] == version, f"najnowszy wpis w CHANGELOG.md ({versions[0]}) rozni sie od VERSION ({version})"


def test_changelog_versions_are_unique_and_descending():
    versions = _changelog_versions()
    assert len(set(versions)) == len(versions)
    assert [_tuple(v) for v in versions] == sorted((_tuple(v) for v in versions), reverse=True)
