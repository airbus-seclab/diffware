#!/usr/bin/env python3
"""
Compare the contents of two files or directories
"""
import os
import sys
import shutil
import logging
import pathlib
import fnmatch
import operator
import itertools
from copy import deepcopy
from functools import lru_cache

try:
    # Try to import fact_extractor if possible, otherwise
    # disable unpacking
    sys.path.append("../fact_extractor/fact_extractor")
    from unpacker.unpack import Unpacker
    FACT_FOUND = True
except ModuleNotFoundError:
    FACT_FOUND = False

import files
from config import make_config
from logger import Logger
from profiler import Profiler
from file_comparator import FileComparator
from fileset_comparator import FilesetComparator
from utils import get_file_type, read_list_from_config


@lru_cache(maxsize=128, typed=False)
def _is_mime_excluded(mime_type):
    for pattern in EXCLUDED_MIMES:
        if fnmatch.fnmatchcase(mime_type, pattern):
            return True


def is_excluded(path):
    for pattern in EXCLUDED:
        if fnmatch.fnmatchcase(str(path), pattern):
            Logger.debug("Ignoring file {}".format(path))
            return True

    # Don't find mime type if there is no rule to exclude it
    if EXCLUDED_MIMES:
        mime_type = get_file_type(path)["mime"]
        if _is_mime_excluded(mime_type):
            Logger.debug("Ignoring file {} with mime-type {}".format(path, mime_type))
            return True

    return False


def _copy_if_necessary(file_path, source_folder, destination_folder):
    """
    Copy the given file to the output folder, if it's not already there
    """
    try:
        # Get the relative path for this file from the source folder
        relative_path = file_path.relative_to(source_folder)

        # Keep the same relative path, but from the destination folder
        target_path = pathlib.Path(destination_folder, relative_path)
        os.makedirs(target_path.parent, exist_ok=True)

        if file_path.is_symlink():
            # Add ".symlink" so it's clear to the user what this is supposed
            # to be
            target_path = pathlib.Path(str(target_path) + ".symlink")
            with open(target_path, "w") as f:
                f.write("Target: {}".format(os.readlink(file_path)))
            return target_path
        else:
            return shutil.copy(file_path, target_path)
    except ValueError:
        # relative_to will fail for files which are not located in the
        # source_folder (so they must be in the destination_folder)
        return file_path
    except shutil.SameFileError:
        # Copy may fail if the file is already in the right location
        return file_path


def _delete_if_necessary(file_path, source_folder):
    """
    Delete the given file, if it's not in the source_folder
    """
    if pathlib.Path(source_folder) in file_path.parents:
        return

    os.remove(file_path)


def _extract(file_path, unpacker, config, depth=0):
    """
    Assume file_path is not a directory, and either recursively extract its
    content, or return the plain file if there is nothing to extract
    """
    # Ignore unwanted files
    if is_excluded(file_path):
        return

    # Make sure recursion max depth isn't exceeded
    should_skip = False
    if config.max_depth >= 0 and depth > config.max_depth:
        Logger.warn("Max recursion depth reached, skipping {}".format(file_path))
        should_skip = True
    else:
        Logger.progress("Unpacking {}...".format(file_path))

    # Symlinks shouln't be followed
    if file_path.is_symlink():
        should_skip = True

    # Update the "_file_folder" value from the unpacker so fact_extractor
    # doesn't extract in the root output folder, making everything
    # messy and breaking the original hierachy
    try:
        relative_path = file_path.relative_to(config.data_folder)
        extract_folder = pathlib.Path(config.data_folder, str(relative_path) + "_extracted")
    except ValueError:
        # This file is still in the source_folder, so no need to bother
        extract_folder = config.data_folder

    unpacker._file_folder = extract_folder

    # Attempt to extract file, if necessary
    extracted_count = 0
    if not should_skip:
        for path in unpacker.unpack(file_path, EXCLUDED):
            # unpack already does the walk for us, so we can just call _extract
            # again
            extracted_count += 1
            yield from _extract(path, unpacker, config, depth=depth + 1)

    if extracted_count == 0:
        # If no files were extracted, at least return this file
        # _copy_if_necessary takes care of handling symlinks
        path = _copy_if_necessary(file_path, config.source_folder, config.data_folder)
        yield files.generic.UnpackedFile(path, config.data_folder)
    else:
        # Since the content was extracted, we can delete this file
        _delete_if_necessary(file_path, config.source_folder)


def _walk(file_path, config):
    """
    Generator to walk the files included in a directory
    """
    for root, _, files in os.walk(file_path):
        for name in files:
            file = pathlib.Path(root, name)

            Logger.progress("Walking {}...".format(file))
            if not is_excluded(file):
                yield file


def extract(file_path, unpacker, config):
    """
    Recursively extract the content of a file or folder
    """
    data_folder = config.get("unpack", "data_folder")
    max_depth = config.max_depth

    # Resolve symlinks and get absolute paths once so we don't run into
    # issues later on by attempting to resolve broken symlinks that were
    # extracted
    data_folder = pathlib.Path(data_folder, "files").resolve()

    if file_path.is_dir():
        # Walk through folders and extract only the files they contain
        config.source_folder = file_path
        config.data_folder = data_folder
        for path in _walk(file_path, config):
            yield from _extract(path, unpacker, config)
    else:
        # Regular files can just be extracted
        config.source_folder = file_path.parent
        config.data_folder = data_folder
        yield from _extract(file_path, unpacker, config)


def list_files(file_path, config):
    """
    List all the files at the given path
    """

    if is_excluded(file_path):
        return

    if file_path.is_dir():
        data_folder = file_path
        for path in _walk(file_path, config):
            yield files.generic.UnpackedFile(path, data_folder)
    else:
        data_folder = file_path.parent
        yield files.generic.UnpackedFile(file_path, data_folder)


def get_extracted_files(file_path1, file_path2, config):
    file_path1 = pathlib.Path(file_path1).resolve()
    file_path2 = pathlib.Path(file_path2).resolve()

    config1 = deepcopy(config)
    config1.update("data_folder", config.get("unpack", "data_folder_1"))

    config2 = deepcopy(config)
    config2.update("data_folder", config.get("unpack", "data_folder_2"))

    if config.extract:
        unpacker1 = Unpacker(config=config1, exclude=EXCLUDED)
        unpacker2 = Unpacker(config=config2, exclude=EXCLUDED)

        files1 = extract(file_path1, unpacker1, config1)
        files2 = extract(file_path2, unpacker2, config2)

        data_folder_1 = "/tmp/extractor1"
        data_folder_2 = "/tmp/extractor2"
    else:
        files1 = list_files(file_path1, config1)
        files2 = list_files(file_path2, config2)

        data_folder_1 = file_path1 if file_path1.is_dir() else file_path1.parent
        data_folder_2 = file_path2 if file_path2.is_dir() else file_path2.parent

    # Print info about the compared files
    Logger.output("Directory1: {}\nDirectory2: {}".format(
        data_folder_1,
        data_folder_2
    ))

    return files1, files2


def output_change(edit, config):
    path1, path2, distance = edit

    if config.compute_distance:
        Logger.output("\nFile1: {}\nFile2: {}\nDistance: {}".format(
            path1,
            path2,
            distance
        ))
    else:
        Logger.output("\nFile1: {}\nFile2: {}".format(
            path1,
            path2
        ))


def compare_files(file_set1, file_set2, config):
    comparator = FilesetComparator(files1, files2, config)
    pairs = comparator.get_files_to_compare()

    # When sorting , every value has to be computed before starting printing
    delay_output = False
    if config.sort_order.lower() == "distance":
        delay_output = True
    elif config.sort_order.lower() == "path":
        delay_output = True

    # Print info about the files that were modified
    edits = []
    for file1, file2 in pairs:
        Logger.progress("Comparing {} and {}...".format(file1.relative_path, file2.relative_path))

        if FileComparator.are_equal(file1, file2):
            continue

        if config.compute_distance:
            distance = FilesetComparator.compute_distance(file1, file2)
        else:
            distance = None

        if distance is not None and distance < config.min_dist:
            # Ignore files that are too similar
            continue

        edits.append((file1.path, file2.path, distance))

        # Start printing files if we can, so user doesn't have to wait too long
        if not delay_output:
            output_change(edits[-1], config)

    # If necessary, sort and then output the result
    Logger.progress("Generating output...")
    if config.sort_order.lower() == "distance":
        edits.sort(key=operator.itemgetter(2), reverse=True)
    elif config.sort_order.lower() == "path":
        edits.sort(key=operator.itemgetter(0), reverse=True)

    if delay_output:
        for edit in edits:
            output_change(edit, config)

    # Print info about the added and removed files
    added_count = 0
    for added in comparator.added_files:
        added_count += 1
        Logger.output("\nAdded: {}".format(added.path))

    removed_count = 0
    for removed in comparator.removed_files:
        removed_count += 1
        Logger.output("\nRemoved: {}".format(removed.path))

    # Print overall statistics
    Logger.info("Found {} added files, {} removed files and {} changed files".format(
        added_count,
        removed_count,
        len(edits)
    ))


if __name__ == "__main__":
    config = make_config()
    Profiler.PROFILING_ENABLED = config.profile

    if config.extract and not FACT_FOUND:
        raise ModuleNotFoundError("fact_extractor not found on your system, please use the --no-extract option or see the install instructions")

    # Use global variables so it doesn't break lru_cache
    global EXCLUDED, EXCLUDED_MIMES
    EXCLUDED = read_list_from_config(config, "unpack", "exclude") or []
    EXCLUDED_MIMES = config.exclude_mime

    try:
        file1 = config.FILE_PATH_1
        file2 = config.FILE_PATH_2
        files1, files2 = get_extracted_files(file1, file2, config)
        compare_files(files1, files2, config)
        Profiler.print()
    finally:
        FileComparator.cleanup()
        Logger.cleanup()
