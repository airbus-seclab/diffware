import pytest

from .utils import get_files, make_config
from helpers.config import Config


@pytest.fixture
def path1():
    return "tests/data/test1.7z"


@pytest.fixture
def path2():
    return "tests/data/test2.7z"


@pytest.fixture
def config():
    return make_config()


def test_extraction(config, path1, path2):
    files1, files2 = get_files(config, path1, path2)
    assert len(files1) == 2
    assert len(files2) == 2


def test_extraction_exclude(config, path1, path2):
    config.update("exclude", ["*/broken*"])
    files1, files2 = get_files(config, path1, path2)
    assert len(files1) == 1
    assert len(files2) == 1


def test_extraction_exclude_mime(config, path1, path2):
    config.update("exclude", ["*/broken*"])
    files1, files2 = get_files(config, path1, path2)
    assert len(files1) == 1
    assert len(files2) == 1
