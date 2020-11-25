#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

"""
Compare the contents of two files or directories

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
import logging
import operator
import multiprocessing
from copy import deepcopy
from functools import lru_cache, partial

from helpers.runner import Runner
from helpers.logger import Logger
from helpers.profiler import Profiler
from helpers.config import make_config
from helpers.file_comparator import FileComparator
from helpers.fileset_comparator import FilesetComparator


def output_change(edit, config):
    global lock
    file1, file2, distance = edit

    path1, path2 = file1.path, file2.path
    mime1, mime2 = file1.type, file2.type

    if mime1 == mime2:
        mime = "{} ({})".format(mime1["full"], mime1["mime"])
    else:
        mime = "{} ({}) / {} ({})".format(
            mime1["full"],
            mime1["mime"],
            mime2["full"],
            mime2["mime"]
        )

    lock.acquire()

    if config.compute_distance:
        Logger.output("\nFile1: {}\nFile2: {}\nMime: {}\nDistance: {}".format(
            path1,
            path2,
            mime,
            distance
        ))
    else:
        Logger.output("\nFile1: {}\nFile2: {}\nMime: {}".format(
            path1,
            path2,
            mime
        ))

    Logger.flush_output()
    lock.release()


def _compare(config, delay_output, pair):
    """
    Compare a pair of files and return either None if they are equal
    or too similar, or a tuple of (path1, path2, distance) otherwise
    """
    file1, file2 = pair
    Logger.progress("Comparing {} and {}...".format(file1.relative_path, file2.relative_path))

    if FileComparator.are_equal(file1, file2):
        return

    if config.compute_distance:
        distance = FilesetComparator.compute_distance(file1, file2)
    else:
        distance = None

    if distance is not None and distance < config.min_dist:
        # Ignore files that are too similar
        return

    edit = (file1, file2, distance)

    # Start printing files if we can, so user doesn't have to wait too long
    if not delay_output:
        output_change(edit, config)

    return edit


def _init_process(shared_lock):
    global lock
    lock = shared_lock


def compare_files(file_set1, file_set2, data_folder_1, data_folder_2, config):
    # Print info about the compared files
    Logger.output("Directory1: {}\nDirectory2: {}".format(
        data_folder_1,
        data_folder_2
    ))

    # Make sure this is flushed before multiprocessing starts, otherwise
    # it may be written multiple times
    # Passing "flush=True" is not enough if the output target is a file
    Logger.flush_output()

    comparator = FilesetComparator(files1, files2, config)
    pairs = comparator.get_files_to_compare()

    # When sorting , every value has to be computed before starting printing
    delay_output = False
    if config.sort_order.lower() == "distance":
        delay_output = True
    elif config.sort_order.lower() == "path":
        delay_output = True

    # Build a partial func by passing config and delay output, so the result
    # can be used by pool.map
    func = partial(_compare, config, delay_output)

    # Use lock so lines aren't mixed up in output
    lock = multiprocessing.Lock()

    with multiprocessing.Pool(config.jobs, initializer=_init_process, initargs=(lock,)) as pool:
        edits = pool.map(func, pairs)
        edits = [edit for edit in edits if edit is not None]

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
        mime = "{} ({})".format(added.type["full"], added.type["mime"])
        Logger.output("\nAdded: {}\nMime: {}".format(
            added.path,
            mime
        ))

    removed_count = 0
    for removed in comparator.removed_files:
        removed_count += 1
        mime = "{} ({})".format(removed.type["full"], removed.type["mime"])
        Logger.output("\nRemoved: {}\nMime: {}".format(
            removed.path,
            mime
        ))

    # Print overall statistics
    Logger.info("\nFound {} added files, {} removed files and {} changed files ({} files in total)".format(
        added_count,
        removed_count,
        len(edits),
        added_count + removed_count + len(edits)
    ))


if __name__ == "__main__":
    config = make_config()
    Profiler.PROFILING_ENABLED = config.profile

    try:
        file1 = config.FILE_PATH_1
        file2 = config.FILE_PATH_2
        runner = Runner(config)
        files1, files2, data_folder_1, data_folder_2 = runner.get_extracted_files(file1, file2)
        compare_files(files1, files2, data_folder_1, data_folder_2, config)
        Profiler.print()
    finally:
        FileComparator.cleanup()
        Logger.cleanup()
