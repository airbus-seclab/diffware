#!/usr/bin/env python3
"""
Parse the output of the script and feed it to diffoscope
"""
import os
import sys
import shutil
import pathlib
import argparse
import tempfile
import subprocess


DIFFOSCOPE_PATH = "../diffoscope/bin/diffoscope"


def _copy_file(file, dir, prefix=""):
    # Remove the prefix from the path to build the target output
    file_path = file.relative_to(prefix)
    dst = pathlib.Path(dir.name, file_path)

    # Copy the file to the matching place in the tmp dir so hierachy is kept
    os.makedirs(dst.parent, exist_ok=True)
    shutil.copy(file, dst)


def _get_path(line):
    # Path is always preceded by a word and a space
    path = " ".join(line.strip().split(" ")[1:])
    return pathlib.Path(path)


def _get_pair(lines):
    if len(lines) > 1:
        # A file was modified
        file1 = _get_path(lines[0])
        file2 = _get_path(lines[1])
        return (file1, file2)

    # A file was added or removed
    line = lines[0]
    file = _get_path(line)
    if line.startswith("Added"):
        return (None, file)
    else:
        return (file, None)


def _parse_diff(diff):
    lines = diff.strip().split("\n")
    return _get_pair(lines)


def parse_file(file_path):
    """
    Return pairs of files that were found to be different
    For each pair, one of the elements may be None if the file was added
    or removed
    """
    with open(file_path, "r") as f:
        content = f.read()

        # An empty line is printed between each difference
        differences = content.split("\n\n")

        # Remove empty entries
        differences = filter(lambda line: len(line.strip()) > 0, differences)

        # Parse the content
        return map(_parse_diff, differences)


def create_tmp_dirs():
    tmp1 = tempfile.TemporaryDirectory(prefix="difftool_")
    tmp2 = tempfile.TemporaryDirectory(prefix="difftool_")
    return tmp1, tmp2


def cleanup_tmp_dirs(tmp1, tmp2):
    tmp1.cleanup()
    tmp2.cleanup()


def copy_files(pairs, tmp1, tmp2):
    """
    Copy files which need to be compared to a temporary directory so diffoscope
    only diffs them
    Files have to be copied (not linked) as diffoscope doesn't follow symlinks
    """
    file_count = 0

    # The first pair contains info about the root paths
    dir1, dir2 = next(pairs)

    for file1, file2 in pairs:
        if file1 is not None:
            file_count += 1
            _copy_file(file1, tmp1, prefix=dir1)

        if file2 is not None:
            file_count += 1
            _copy_file(file2, tmp2, prefix=dir2)

    print("Copied", file_count, "files")


def call_diffoscope(dir1, dir2, args):
    cmd = ["python3", DIFFOSCOPE_PATH, dir1.name, dir2.name, *args]
    subprocess.run(cmd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wrapper to run diffoscope on the output of difftool")
    parser.add_argument("difftool_args", nargs="*")
    parser.add_argument("FILE_PATH", type=str, help="Path to file created by running difftool")

    # We only parse the second argument (the first being the name of the script)
    # since the other will be used for diffoscope
    args = parser.parse_args(sys.argv[1:2])
    pairs = parse_file(args.FILE_PATH)

    # Create temporary directories to feed them to diffoscope
    tmp1, tmp2 = create_tmp_dirs()
    copy_files(pairs, tmp1, tmp2)

    # Call diffoscope and then cleanup the output
    call_diffoscope(tmp1, tmp2, sys.argv[2:])
    cleanup_tmp_dirs(tmp1, tmp2)
