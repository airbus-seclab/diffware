"""
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
import re
import tlsh
from functools import cached_property

from helpers.profiler import Profiler
from helpers.file_comparator import FileComparator
from helpers.utils import (
    get_file_type,
    get_file_size,
    read_timeout,
    compute_fuzzy_hash
)


class UnpackedFile:
    # Regex describing the filemagic to match for this class
    recognize_regex = re.compile(r".*")

    def __init__(self, path, config, data_folder="/"):
        self.path = path
        self.config = config
        self._data_folder = data_folder
        self._match = None

    @cached_property
    @Profiler.profilable
    def type(self):
        return get_file_type(self.path)

    @cached_property
    def relative_path(self):
        return self.path.relative_to(self._data_folder)

    def __repr__(self):
        return "{} {}".format(self.__class__, self.path)

    def __eq__(self, other):
        # Consider that extracted files match if they have the same path
        # Their content is checked later using the contents of _comparable_path
        result = (self.relative_path == other.relative_path)
        if result:
            # Store which other file this one matches so it can be easily
            # accessed later on
            self._match = other
            other._match = self
        return result

    def __hash__(self):
        return hash(self.relative_path)

    @classmethod
    @Profiler.profilable
    def recognizes(cls, file_type: dict):
        """
        Whether this class can be used to analyze files with the given type
        """
        return cls.recognize_regex.match(file_type["full"])

    def has_same_content_as(self, other):
        """
        Check whether this file as the same content as another file
        """
        return FileComparator._compare_files(
            self, self._comparable_path,
            other, other._comparable_path
        )

    @cached_property
    @Profiler.profilable
    def _comparable_path(self):
        """
        Path to the file which can be read by the cmp process (used to compare
        large files)
        This can be overriden for files (like ELFs) where only part of the
        content should be compared
        """
        return self.path

    @Profiler.profilable
    def _read(self, path=None):
        """
        Read the content of this file
        Setting path will override the default behavior of computing a
        comparable path and then using it to read the contents of the file
        """
        path = path or self._comparable_path

        def generator():
            try:
                with open(path, "rb") as f:
                    for buf in iter(lambda: read_timeout(f, 32768, 5), b""):
                        yield buf
            except TimeoutError:
                pass

        return generator()

    @cached_property
    def fuzzy_hash(self):
        return compute_fuzzy_hash(self, self._comparable_path)
