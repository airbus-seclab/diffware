#!/usr/bin/env python3
"""
Parse the output of the script and feed it to diffoscope

Copyright (C) 2020 Jean-Romain Garnier <github@jean-romain.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import os
import sys
import shutil
import pathlib
import argparse
import tempfile
import subprocess


DIFFOSCOPE_PATH = "diffoscope"


def _get_file_output_path(file, dir, prefix=""):
    # Remove the prefix from the path to build the target output
    file_path = file.relative_to(prefix)
    return pathlib.Path(dir.name, file_path)


def _hardlink_file(file, dir, prefix=""):
    dst = _get_file_output_path(file, dir, prefix)

    # Copy the file to the matching place in the tmp dir so hierachy is kept
    try:
        os.makedirs(dst.parent, exist_ok=True)
        os.link(file, dst)
    except FileExistsError:
        # This file was already copied, don't do it again
        pass


def _copy_file(file, dir, prefix=""):
    dst = _get_file_output_path(file, dir, prefix)

    # Copy the file to the matching place in the tmp dir so hierachy is kept
    try:
        os.makedirs(dst.parent, exist_ok=True)
        shutil.copy(file, dst)
    except shutil.SameFileError:
        # This file was already copied, don't do it again
        pass


def _get_path(line):
    # Path is always preceded by a word and a space
    path = " ".join(line.strip().split(" ")[1:])
    return pathlib.Path(path)


def _get_pair(lines):
    line = lines[0]
    file1 = _get_path(line)
    if line.startswith("Added:"):
        return (None, file1)
    elif line.startswith("Removed:"):
        return (file1, None)
    else:
        file2 = _get_path(lines[1])
        return (file1, file2)


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
    tmp1 = tempfile.TemporaryDirectory(prefix="diffware_")
    tmp2 = tempfile.TemporaryDirectory(prefix="diffware_")
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
            try:
                _hardlink_file(file1, tmp1, prefix=dir1)
            except:
                # Links may not be available depending on filesystem
                _copy_file(file1, tmp1, prefix=dir1)

        if file2 is not None:
            file_count += 1
            try:
                _hardlink_file(file2, tmp2, prefix=dir2)
            except:
                _copy_file(file2, tmp2, prefix=dir2)

    print("Copied", file_count, "files")


def call_diffoscope(dir1, dir2, args):
    # We can't prevent diffoscope from extracting files, as
    # --max-container-depth also impacts analysis of ELFs (among others)
    cmd = [DIFFOSCOPE_PATH, dir1.name, dir2.name, *args]
    subprocess.run(cmd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wrapper to run diffoscope on the output of diffware")
    parser.add_argument("diffware_args", nargs="*")
    parser.add_argument("FILE_PATH", type=str, help="Path to file created by running diffware")

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
