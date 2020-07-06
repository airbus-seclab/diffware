from helpers.config import Config
from helpers.logger import Logger
from helpers.runner import Runner


def get_files(config, path1, path2):
    runner = Runner(config)
    files1, files2 = runner.get_extracted_files(path1, path2)
    return list(files1), list(files2)


def make_config():
    config = Config()
    Logger.setup_logging(progress=False, output_file="/dev/null")
    return config
