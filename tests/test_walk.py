import pytest

from .utils import get_files, make_config
from helpers.config import Config


@pytest.fixture
def path1():
    return "tests/data/test1"


@pytest.fixture
def path2():
    return "tests/data/test2"


@pytest.fixture
def config():
    config = make_config()
    config.update("extract", False)
    return config


def test_walk(config, path1, path2):
    files1, files2 = get_files(config, path1, path2)
    assert len(files1) == 2
    assert len(files2) == 2


def test_walk_exclude(config, path1, path2):
    config.update("exclude", ["*/broken*"])
    files1, files2 = get_files(config, path1, path2)
    assert len(files1) == 1
    assert len(files2) == 1


def test_walk_exclude_mime(config, path1, path2):
    config.update("exclude_mime", ["text/*"])
    files1, files2 = get_files(config, path1, path2)
    assert len(files1) == 1
    assert len(files2) == 1
