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
