"""Tests for archive extraction."""

import pathlib
import tarfile
import zipfile

import pytest

import ghrel.archive
import ghrel.errors


def _write_tar_path(archive_fpath: pathlib.Path, name: str) -> None:
    """Write a tar archive containing a single path entry."""
    with tarfile.open(archive_fpath, "w") as tar:
        info = tarfile.TarInfo(name)
        info.size = 0
        tar.addfile(info)


def _write_tar_link(
    archive_fpath: pathlib.Path,
    name: str,
    linkname: str,
    link_type: bytes,
) -> None:
    """Write a tar archive containing a single link entry."""
    with tarfile.open(archive_fpath, "w") as tar:
        info = tarfile.TarInfo(name)
        info.type = link_type
        info.linkname = linkname
        tar.addfile(info)


@pytest.mark.parametrize("link_type", [tarfile.SYMTYPE, tarfile.LNKTYPE])
def test_extract_tar_rejects_links(tmp_path: pathlib.Path, link_type: bytes) -> None:
    """extract_archive rejects symlink and hardlink entries."""
    archive_fpath = tmp_path / "evil.tar"
    _write_tar_link(archive_fpath, "evil", "../etc", link_type)
    dest_dpath = tmp_path / "out"

    with pytest.raises(ghrel.errors.ArchiveError, match="link"):
        ghrel.archive.extract_archive(archive_fpath, dest_dpath)


def test_extract_archive_rejects_unsupported_format(tmp_path: pathlib.Path) -> None:
    """extract_archive rejects non-tar/zip files."""
    archive_fpath = tmp_path / "not-archive.bin"
    archive_fpath.write_bytes(b"not an archive")
    dest_dpath = tmp_path / "out"

    with pytest.raises(ghrel.errors.ArchiveError, match="Unsupported archive format"):
        ghrel.archive.extract_archive(archive_fpath, dest_dpath)


def test_extract_tar_rejects_absolute_paths(tmp_path: pathlib.Path) -> None:
    """extract_archive rejects absolute paths in tar."""
    archive_fpath = tmp_path / "abs.tar"
    _write_tar_path(archive_fpath, "/etc/passwd")
    dest_dpath = tmp_path / "out"

    with pytest.raises(ghrel.errors.ArchiveError, match="absolute paths"):
        ghrel.archive.extract_archive(archive_fpath, dest_dpath)


def test_extract_tar_rejects_path_traversal(tmp_path: pathlib.Path) -> None:
    """extract_archive rejects path traversal in tar."""
    archive_fpath = tmp_path / "traversal.tar"
    _write_tar_path(archive_fpath, "../escape")
    dest_dpath = tmp_path / "out"

    with pytest.raises(ghrel.errors.ArchiveError, match="path traversal"):
        ghrel.archive.extract_archive(archive_fpath, dest_dpath)


def test_extract_zip_rejects_absolute_paths(tmp_path: pathlib.Path) -> None:
    """extract_archive rejects absolute paths in zip."""
    archive_fpath = tmp_path / "abs.zip"
    with zipfile.ZipFile(archive_fpath, "w") as zf:
        zf.writestr("/etc/passwd", "")
    dest_dpath = tmp_path / "out"

    with pytest.raises(ghrel.errors.ArchiveError, match="absolute paths"):
        ghrel.archive.extract_archive(archive_fpath, dest_dpath)


def test_extract_zip_rejects_path_traversal(tmp_path: pathlib.Path) -> None:
    """extract_archive rejects path traversal in zip."""
    archive_fpath = tmp_path / "traversal.zip"
    with zipfile.ZipFile(archive_fpath, "w") as zf:
        zf.writestr("../escape", "")
    dest_dpath = tmp_path / "out"

    with pytest.raises(ghrel.errors.ArchiveError, match="path traversal"):
        ghrel.archive.extract_archive(archive_fpath, dest_dpath)
