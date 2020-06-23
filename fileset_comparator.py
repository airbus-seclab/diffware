import random
import operator
import multiprocessing
from functools import cached_property

import files
from logger import Logger
from profiler import Profiler
from utils import get_file_type, compute_distance


class FilesetComparator(object):
    """
    Class comparing lists of files to identify new files, removed files,
    renamed files...
    """
    @Profiler.profilable
    def __init__(self, files1, files2, config):
        # Converting to set triggers the call to the generators
        self.file_set1 = set(files1)
        self.file_set2 = set(files2)
        self.config = config

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

        common_count = len(self._common_files)
        Logger.debug("{} files in common".format(
            common_count,
        ))

        new_count = len(self._new_files)
        Logger.debug("{} new files".format(
            new_count,
        ))

        missing_count = len(self._missing_files)
        Logger.debug("{} missing files".format(
            missing_count,
        ))

        moved_count = len(self.moved_file_pairs)
        Logger.debug("Found {} files in common, {} moved files, {} new files and {} missing files\n".format(
            common_count,
            moved_count,
            new_count - moved_count,
            missing_count - moved_count
        ))
        return self._get_matching_pairs()

    @cached_property
    def removed_files(self):
        """
        Returns a list of removed files than were not found to be moved
        """
        # Get only the original files (aka from file1) that were moved
        moved = map(lambda pair: pair[0], self.moved_file_pairs)
        return self._missing_files - set(moved)

    @cached_property
    def added_files(self):
        """
        Returns a list of new files than were not found to be similar to an
        older removed files
        """
        # Get only the target files (aka from file2) that were moved
        moved = map(lambda pair: pair[1], self.moved_file_pairs)
        return self._new_files - set(moved)

    @cached_property
    @Profiler.profilable
    def moved_file_pairs(self):
        """
        Use files' fuzzy hash to identify those that were moved
        """
        if self.config.fuzzy_threshold <= 0:
            return []

        moved = []
        files = list(self._missing_files)

        with multiprocessing.Pool(self.config.jobs) as pool:
            matched = pool.map(self._match_file, files)

        for i in range(len(matched)):
            if matched[i] is not None:
                file = files[i]
                moved.append((file, matched[i]))

        return moved

    ### Accessible methods

    @staticmethod
    @Profiler.profilable
    def compute_distance(file1, file2):
        return compute_distance(file1, file2)

    ### Internal methods

    def _get_matching_pairs(self):
        """
        Returns a list of pair of files to be compared
        """
        def generator():
            for file in self._common_files:
                # The matched file may not have been specialized yet
                file2 = self._specialize_file(file._match)
                yield (file, file2)

            yield from self.moved_file_pairs

        return generator()

    @cached_property
    @Profiler.profilable
    def _common_files(self):
        """
        Return files with the same paths in both sets
        """
        Logger.progress("Finding files in common...")
        # Do this in 2 steps (rather than using .intersection) to make
        # sure the elements we get are from file_set1
        diff = self.file_set1 - self.file_set2
        return self._specialize(self.file_set1 - diff)

    @cached_property
    @Profiler.profilable
    def _missing_files(self):
        """
        Return files which exist in the first set but not the second
        """
        Logger.progress("Finding missing files...")
        return self._specialize(self.file_set1 - self._common_files)

    @cached_property
    @Profiler.profilable
    def _new_files(self):
        """
        Return files which exist in the second set but not the first
        """
        Logger.progress("Finding new files...")
        return self._specialize(self.file_set2 - self._common_files)

    def _match_file(self, file, file_set=None):
        """
        Match the given file with another file from the given set, if they
        are similar enough
        """
        Logger.progress("Looking for moved {}...".format(file.path))

        if file.fuzzy_hash is None:
            return None

        if file_set is None:
            file_set = list(self._new_files)

        # Randomize the order in which the files are iterated so multithreading
        # doesn't compute the fuzzy_hash of the same file multiple times
        # in parallel, rendering the cache useless
        random.shuffle(file_set)

        comparisons = []
        for f in file_set:
            if not f.fuzzy_hash:
                continue

            score = type(self).compute_distance(file, f)
            comparisons.append((score, f))

        if not comparisons:
            return None

        comparisons.sort(key=operator.itemgetter(0))
        best_score, closest_file = comparisons[0]
        if best_score < self.config.fuzzy_threshold:
            return closest_file

        return None

    def _specialize(self, file_set):
        """
        Specializes all the files in the given set
        """
        if not self.config.specialize:
            return file_set

        specialized_set = set()
        for file in file_set:
            Logger.progress("Specializing {}...".format(file.path))
            specialized_set.add(self._specialize_file(file))

        return specialized_set

    def _specialize_file(self, file):
        """
        Finds the best class to represent the given file and casts the instance
        """
        if not self.config.specialize:
            return file

        for file_class in files.FILE_TYPES:
            if file_class.recognizes(file.type):
                file.__class__ = file_class
                break

        return file
