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

sys.path.append("../fact_extractor/fact_extractor")
from unpacker.unpack import Unpacker
from helperFunctions.config import read_list_from_config

import files
from profiler import Profiler
from fileset_comparator import FilesetComparator
from file_comparator import FileComparator
from logger import Logger
from utils import get_file_type
from setup import setup


def is_excluded(file, exclude, exclude_mime):
    for pattern in exclude:
        if fnmatch.fnmatchcase(str(file), pattern):
            Logger.debug("Ignoring file {}".format(file))
            return True

    mime_type = get_file_type(file)["mime"]
    for pattern in exclude_mime:
        if fnmatch.fnmatchcase(mime_type, pattern):
            Logger.debug("Ignoring file {} with mime-type {}".format(file, mime_type))
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


def _extract(file_path, unpacker, source_folder, data_folder, exclude, exclude_mime, max_depth, depth=0):
    """
    Assume file_path is not a directory, and either recursively extract its
    content, or return the plain file if there is nothing to extract
    """
    # Ignore unwanted files
    if is_excluded(file_path, exclude, exclude_mime):
        return

    if max_depth >= 0 and depth > max_depth:
        Logger.info("Not unpacking {} because max recursion depth has been reached".format(file_path))
        return
    else:
        Logger.progress("Unpacking {}".format(file_path))

    extracted_count = 0

    # Symlinks should be copied as text files containing their target
    if not file_path.is_symlink():
        for path in unpacker.unpack(file_path, exclude):
            # unpack already does the walk for us, so we can just call _extract
            # again
            extracted_count += 1
            yield from _extract(path, unpacker, source_folder, data_folder, exclude, exclude_mime, max_depth, depth=depth + 1)

    # If no files were extracted, at least return this file
    if extracted_count == 0:
        path = _copy_if_necessary(file_path, source_folder, data_folder)
        yield files.generic.UnpackedFile(path, unpacker, data_folder)


def _walk(file_path, exclude, exclude_mime):
    """
    Generator to walk the files included in a directory
    """
    for root, _, files in os.walk(file_path):
        for name in files:
            file = pathlib.Path(root, name)

            if not is_excluded(file, exclude, exclude_mime):
                Logger.progress("Walking {}".format(file))
                yield file


def extract(file_path, unpacker, config):
    """
    Recursively extract the content of a file or folder
    """
    data_folder = config.get("unpack", "data_folder")
    exclude = read_list_from_config(config, "unpack", "exclude") or []
    exclude_mime = config.exclude_mime
    max_depth = config.max_depth

    # Resolve symlinks and get absolute paths once so we don't run into
    # issues later on by attempting to resolve broken symlinks that were
    # extracted
    data_folder = pathlib.Path(data_folder, "files").resolve()

    if file_path.is_dir():
        # Walk through folders and extract only the files they contain
        source_folder = file_path
        for path in _walk(file_path, exclude, exclude_mime):
            yield from _extract(path, unpacker, source_folder, data_folder, exclude, exclude_mime, max_depth)
    else:
        # Regular files can just be extracted
        source_folder = file_path.parent
        yield from _extract(file_path, unpacker, source_folder, data_folder, exclude, exclude_mime, max_depth)


def list_files(file_path, unpacker, config):
    """
    List all the files at the given path
    """
    exclude = read_list_from_config(config, "unpack", "exclude") or []
    blacklist = read_list_from_config(config, "unpack", "blacklist") or []
    exclude_mime = config.exclude_mime

    if is_excluded(file_path, exclude, exclude_mime):
        return

    if file_path.is_dir():
        data_folder = file_path
        for path in _walk(file_path, exclude, exclude_mime):
            yield files.generic.UnpackedFile(path, unpacker, data_folder)
    else:
        data_folder = file_path.parent
        yield files.generic.UnpackedFile(file_path, unpacker, data_folder)


def get_extracted_files(file_path1, file_path2, config):
    file_path1 = pathlib.Path(file_path1).resolve()
    file_path2 = pathlib.Path(file_path2).resolve()

    config1 = deepcopy(config)
    config1.update("data_folder", config.get("unpack", "data_folder_1"))
    unpacker1 = Unpacker(config=config1, exclude=config1.exclude)

    config2 = deepcopy(config)
    config2.update("data_folder", config.get("unpack", "data_folder_2"))
    unpacker2 = Unpacker(config=config2, exclude=config2.exclude)

    if config.extract:
        files1 = extract(file_path1, unpacker1, config1)
        files2 = extract(file_path2, unpacker2, config2)

        data_folder_1 = "/tmp/extractor1"
        data_folder_2 = "/tmp/extractor2"
    else:
        files1 = list_files(file_path1, unpacker1, config1)
        files2 = list_files(file_path2, unpacker2, config2)

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
    comparator = FilesetComparator(files1, files2, config.specialize, config.jobs)
    pairs = comparator.get_files_to_compare()

    # When sorting , every value has to be computed before starting printing
    delay_output = False
    if config.sort_order.lower() == "distance":
        delay_output = True
    elif config.sort_order.lower() == "path":
        delay_output = True

    # Print info about the files that were modified
    Logger.progress("Computing distances for modified files...")

    edits = []
    for file1, file2 in pairs:
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
    if config.sort_order.lower() == "distance":
        edits.sort(key=operator.itemgetter(2), reverse=True)
    elif config.sort_order.lower() == "path":
        edits.sort(key=operator.itemgetter(0), reverse=True)

    if delay_output:
        for edit in edits:
            output_change(edit, config)

    # Print info about the added and removed files
    added_count = 0
    for added in comparator.get_added_files():
        added_count += 1
        Logger.output("\nAdded: {}".format(added.path))

    removed_count = 0
    for removed in comparator.get_removed_files():
        removed_count += 1
        Logger.output("\nRemoved: {}".format(removed.path))

    # Print overall statistics
    Logger.info("Found {} added files, {} removed files and {} changed files".format(
        added_count,
        removed_count,
        len(edits)
    ))


if __name__ == "__main__":
    config = setup()
    Profiler.PROFILING_ENABLED = config.profile

    file1 = config.FILE_PATH_1
    file2 = config.FILE_PATH_2
    files1, files2 = get_extracted_files(file1, file2, config)
    compare_files(files1, files2, config)

    FileComparator.cleanup()
    Profiler.print()
