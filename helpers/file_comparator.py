"""
Copyright (C) 2020 Airbus

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
import tempfile
import subprocess

from .profiler import Profiler
from .utils import get_file_size


class FileComparator:
    """
    Class comparing two given files, and handling temporary file paths generated
    for this comparison
    """
    TMP_DIR = tempfile.TemporaryDirectory(prefix="diffware_")

    @staticmethod
    def are_equal(file1, file2):
        # Specialized files may have custom implementations of compare, so
        # let them to their stuff
        return file1.has_same_content_as(file2)

    @staticmethod
    def _compare_files(file1, path1, file2, path2):
        """
        Compare the contents of the given files at the given path
        Inspired by has_same_content_as in diffoscope/comparators/utils/file.py
        """
        file1_size = get_file_size(path1, default=-1)
        file2_size = get_file_size(path2, default=-1)

        # Files not readable (e.g. broken symlinks) or something else,
        # just assume they are different
        if file1_size < 0 or file2_size < 0:
            return False

        if file1_size != file2_size:
            return False

        if file1_size == file2_size and file2_size <= 65536:
            # Compare small files directly
            file1_content = b"".join(file1._read(path1))
            file2_content = b"".join(file2._read(path2))
            return file1_content == file2_content

        # Call an external diff otherwise
        return subprocess.call(
            ("cmp", "-s", path1, path2),
            shell=False,
            close_fds=True,
        ) == 0

    @classmethod
    def tmp_file_path(cls):
        """
        Used to create a temporary file that should be cleaned up after the
        script is done (remember to call cleanup)
        """
        return tempfile.mktemp(dir=cls.TMP_DIR.name)

    @classmethod
    def cleanup(cls):
        cls.TMP_DIR.cleanup()
