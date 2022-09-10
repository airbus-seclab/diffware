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
import re
from functools import cached_property

from .generic import UnpackedFile

from helpers.file_comparator import FileComparator


class SymlinkFile(UnpackedFile):
    recognize_regex = re.compile(r"symbolic link")

    @cached_property
    def _comparable_path(self):
        tmp_file_path = FileComparator.tmp_file_path()

        with open(tmp_file_path, "w") as f:
            f.write("Target: {}".format(os.readlink(self.path)))

        return tmp_file_path
