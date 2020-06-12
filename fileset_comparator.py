import tlsh
from logger import Logger
import operator

from fact_helper_file import get_file_type_from_path

import files
from utils import cached_property
from profiler import Profiler


class FilesetComparator(object):
    """
    Class comparing lists of files to identify new files, removed files,
    renamed files...
    """
    @Profiler.profilable
    def __init__(self, files1, files2, specialize_enabled=True):
        # Converting to set triggers the call to the generators
        self.file_set1 = set(files1)
        self.file_set2 = set(files2)
        self.specialize_enabled = specialize_enabled

    ### Accessible properties

    def get_files_to_compare(self):
        """
        Return a list of UnpackedFile tuples, each containing 2 files that are
        relevant to compare together
        """
        Logger.debug("Comparing {} files in file1 with {} files in file2".format(
            len(self.file_set1),
            len(self.file_set2)
        ))
        common_count = len(self._get_common_files())
        new_count = len(self._get_new_files())
        missing_count = len(self._get_missing_files())
        moved_count = len(self.get_moved_file_pairs())
        Logger.debug("Found {} files in common, {} moved files, {} new files and {} missing files\n".format(
            common_count,
            moved_count,
            new_count - moved_count,
            missing_count - moved_count
        ))
        return self._get_matching_pairs()

    @cached_property
    def get_removed_files(self):
        """
        Returns a list of removed files than were not found to be moved
        """
        # Get only the original files (aka from file1) that were moved
        moved = map(lambda pair: pair[0], self.get_moved_file_pairs())
        return self._get_missing_files() - set(moved)

    @cached_property
    def get_added_files(self):
        """
        Returns a list of new files than were not found to be similar to an
        older removed files
        """
        # Get only the target files (aka from file2) that were moved
        moved = map(lambda pair: pair[1], self.get_moved_file_pairs())
        return self._get_new_files() - set(moved)

    @cached_property
    @Profiler.profilable
    def get_moved_file_pairs(self):
        """
        Use files' fuzzy hash to identify those that were moved
        """
        moved = []

        for file in self._get_missing_files():
            matched = self._match_file(file, self._get_new_files())
            if matched is not None:
                moved.append((file, matched))

        return moved

    ### Accessible methods

    @staticmethod
    @Profiler.profilable
    def compute_distance(file1, file2):
        """
        Use tlsh to compute the distance between 2 files
        """
        try:
            return tlsh.diff(file1.fuzzy_hash(), file2.fuzzy_hash())
        except TypeError:
            return None

    ### Internal methods

    def _get_matching_pairs(self):
        """
        Returns a list of pair of files to be compared
        """
        def generator():
            for file in self._get_common_files():
                file1 = self._specialize_file(file)
                file2 = self._specialize_file(file._match)
                yield (file1, file2)

            for pair in self.get_moved_file_pairs():
                file1 = self._specialize_file(pair[0])
                file2 = self._specialize_file(pair[1])
                yield (file1, file2)

        return generator()

    @cached_property
    @Profiler.profilable
    def _get_common_files(self):
        """
        Return files with the same paths in both sets
        """
        # Order is important: this will return objects from file_set1
        return set.intersection(
            self.file_set2,
            self.file_set1
        )

    @cached_property
    @Profiler.profilable
    def _get_missing_files(self):
        """
        Return files which exist in the first set but not the second
        """
        return self.file_set1 - self._get_common_files()

    @cached_property
    @Profiler.profilable
    def _get_new_files(self):
        """
        Return files which exist in the second set but not the first
        """
        return self.file_set2 - self._get_common_files()

    def _match_file(self, file, file_set):
        """
        Match the given file with another file from the given set, if they
        are similar enough
        """
        if file.fuzzy_hash() is None:
            return None

        comparisons = []
        for f in file_set:
            if not f.fuzzy_hash():
                continue

            score = type(self).compute_distance(file, f)
            comparisons.append((score, f))

        if not comparisons:
            return None

        comparisons.sort(key=operator.itemgetter(0))
        best_score, closest_file = comparisons[0]
        if best_score < 70:
            return closest_file

        return None

    def _specialize_file(self, file):
        """
        Finds the best class to represent the given file and casts the instance
        """
        if not self.specialize_enabled:
            return file

        file_type = get_file_type_from_path(file.path)

        for file_class in files.FILE_TYPES:
            if file_class.recognizes(file_type):
                file.__class__ = file_class
                break

        return file
