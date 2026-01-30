"""Archive extraction (tar/zip)."""

import pathlib
import tarfile
import zipfile

import beartype

import ghrel.errors


@beartype.beartype
def extract_archive(
    archive_fpath: pathlib.Path, dest_dpath: pathlib.Path
) -> tuple[pathlib.Path, tuple[pathlib.Path, ...]]:
    """Extract a tar or zip archive to dest_dpath safely."""
    if tarfile.is_tarfile(archive_fpath):
        return _extract_tar(archive_fpath, dest_dpath)
    if zipfile.is_zipfile(archive_fpath):
        return _extract_zip(archive_fpath, dest_dpath)
    raise ghrel.errors.ArchiveError(
        message=f"Unsupported archive format: {archive_fpath}",
        hint="Only .tar.* and .zip archives are supported.",
    )


@beartype.beartype
def list_archive_entries(archive_fpath: pathlib.Path) -> tuple[str, ...]:
    """List archive entries for error reporting."""
    if tarfile.is_tarfile(archive_fpath):
        with tarfile.open(archive_fpath, "r:*") as tar:
            return tuple(member.name for member in tar.getmembers())
    if zipfile.is_zipfile(archive_fpath):
        with zipfile.ZipFile(archive_fpath, "r") as zf:
            return tuple(zf.namelist())
    return ()


@beartype.beartype
def _extract_tar(
    archive_fpath: pathlib.Path, dest_dpath: pathlib.Path
) -> tuple[pathlib.Path, tuple[pathlib.Path, ...]]:
    """Extract tar archive after validating paths."""
    dest_dpath.mkdir(parents=True, exist_ok=True)
    dest_root = dest_dpath.resolve(strict=False)
    extracted = []

    with tarfile.open(archive_fpath, "r:*") as tar:
        members = tar.getmembers()
        for member in members:
            if member.issym() or member.islnk():
                raise ghrel.errors.ArchiveError(
                    message=f"Unsafe link in archive: {member.name}",
                    hint="Archive contains symlink or hardlink entries.",
                )
            member_path = pathlib.PurePosixPath(member.name)
            if member_path.is_absolute():
                raise ghrel.errors.ArchiveError(
                    message=f"Unsafe path in archive: {member.name}",
                    hint="Archive contains absolute paths.",
                )
            target_fpath = (dest_dpath / member.name).resolve(strict=False)
            if not _is_within_directory(dest_root, target_fpath):
                raise ghrel.errors.ArchiveError(
                    message=f"Unsafe path in archive: {member.name}",
                    hint="Archive contains path traversal entries.",
                )

        tar.extractall(dest_dpath)

    for extracted_fpath in dest_dpath.rglob("*"):
        extracted.append(extracted_fpath)

    return dest_dpath, tuple(extracted)


@beartype.beartype
def _extract_zip(
    archive_fpath: pathlib.Path, dest_dpath: pathlib.Path
) -> tuple[pathlib.Path, tuple[pathlib.Path, ...]]:
    """Extract zip archive after validating paths."""
    dest_dpath.mkdir(parents=True, exist_ok=True)
    dest_root = dest_dpath.resolve(strict=False)
    extracted = []

    with zipfile.ZipFile(archive_fpath, "r") as zf:
        for name in zf.namelist():
            member_path = pathlib.PurePosixPath(name)
            if member_path.is_absolute():
                raise ghrel.errors.ArchiveError(
                    message=f"Unsafe path in archive: {name}",
                    hint="Archive contains absolute paths.",
                )
            target_fpath = (dest_dpath / name).resolve(strict=False)
            if not _is_within_directory(dest_root, target_fpath):
                raise ghrel.errors.ArchiveError(
                    message=f"Unsafe path in archive: {name}",
                    hint="Archive contains path traversal entries.",
                )

        zf.extractall(dest_dpath)

    for extracted_fpath in dest_dpath.rglob("*"):
        extracted.append(extracted_fpath)

    return dest_dpath, tuple(extracted)


@beartype.beartype
def _is_within_directory(base_dpath: pathlib.Path, target_fpath: pathlib.Path) -> bool:
    """Return True if target_fpath is within base_dpath."""
    try:
        target_fpath.relative_to(base_dpath)
    except ValueError:
        return False
    return True
