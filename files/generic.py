import os
import re
import tlsh
from functools import cached_property

from profiler import Profiler
from utils import get_file_type, get_file_size, read_timeout


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
    def recognizes(self, file_type: dict):
        """
        Whether this class can be used to analyze files with the given type
        """
        return self.recognize_regex.match(file_type["full"])

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
    def _read(self):
        def generator():
            try:
                with open(self._comparable_path, "rb") as f:
                    for buf in iter(lambda: read_timeout(f, 32768, 5), b""):
                        yield buf
            except TimeoutError:
                pass

        return generator()

    @cached_property
    def fuzzy_hash(self):
        """
        cf diffoscope/comparators/utils/file.py
        """
        # tlsh is not meaningful with files smaller than 512 bytes
        if get_file_size(self._comparable_path) >= 512:
            h = tlsh.Tlsh()
            for buf in self._read():
                h.update(buf)
            h.final()
            try:
                return h.hexdigest()
            except ValueError:
                # File must contain a certain amount of randomness.
                pass

        return None
