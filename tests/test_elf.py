import pytest

from .utils import get_files, make_config
from helpers.file_comparator import FileComparator
from helpers.fileset_comparator import FilesetComparator
from files.elf import ElfFile


@pytest.fixture
def path1():
    return "tests/data/test1.o"


@pytest.fixture
def path2():
    return "tests/data/test2.o"


@pytest.fixture
def config():
    config = make_config()
    config.update("extract", False)
    return config


def make_comparator(config, path1, path2):
    files1, files2 = get_files(config, path1, path2)
    return FilesetComparator(files1, files2, config)


def test_specialize(config, path1, path2):
    comparator = make_comparator(config, path1, path2)
    pairs = comparator.get_files_to_compare()
    file1, file2 = next(pairs)

    assert isinstance(file1, ElfFile)
    assert isinstance(file2, ElfFile)


def test_equal(config, path1):
    comparator = make_comparator(config, path1, path1)
    pairs = comparator.get_files_to_compare()
    file1, file2 = next(pairs)

    assert FileComparator.are_equal(file1, file2)


def test_different(config, path1, path2):
    comparator = make_comparator(config, path1, path2)
    pairs = comparator.get_files_to_compare()
    file1, file2 = next(pairs)

    assert not FileComparator.are_equal(file1, file2)
