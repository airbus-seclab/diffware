import sys
import pathlib
import argparse
import argcomplete
import multiprocessing
from configparser import ConfigParser

from logger import Logger

from helperFunctions.program_setup import merge_options
from helperFunctions.config import read_list_from_config


def default_config_path():
    current_dir = pathlib.Path(__file__).parent.absolute()
    return current_dir / "fact.cfg"


class Config(ConfigParser):
    """
    ConfigParser subclass to handle arguments and default values
    """
    # Dict of default values
    __sections = {
        "diff": {
            "data_file": "-",
            "debug": False,
            "config_file": default_config_path(),
            "log_level": "INFO",
            "jobs": multiprocessing.cpu_count(),
            "exclude_mime": [],
            "fuzzy_threshold": 80,
            "max_depth": 5,
            "extract": True,
            "specialize": True,
            "compute_distance": True,
            "sort_order": "none",
            "min_dist": -1,
            "statistics": False,
            "profile": False,
            "FILE_PATH_1": None,
            "FILE_PATH_2": None
        },
        "unpack": {
            "blacklist": [],
            "exclude": [],
            "data_folder_1": "/tmp/extractor1",
            "data_folder_2": "/tmp/extractor2",
            "data_folder": "/tmp/extractor"
        },
        "ExpertSettings": {
            "statistics": False,
            "unpack_threshold": 0.8,
            "header_overhead": 256,
            "compressed_file_types": []
        }
    }

    def __init__(self, arguments):
        super().__init__(self)
        self.read(arguments.config_file)
        self._merge(arguments)

    def _merge(self, arguments):
        """
        Merge options passed through arguments and in config file
        """
        args = vars(arguments)
        for section, values in self.__sections.items():
            for key in values.keys():
                arg_value = args.get(key, None)
                config_value = self.get(section, key, fallback=None)
                default_value = self.__sections[section][key]
                self._merge_values(section, key, arg_value, config_value, default_value)

    def _merge_values(self, section, key, arg_value, config_value, default_value):
        """
        Given a value for the config, either combine the argument, config and
        default values given if it's a list, or use one argument, with the given
        order of priority:
        1. Value passed through CLI (arg_value)
        2. Value set in config (config_value)
        3. Default value (default_value)
        """
        if isinstance(default_value, list):
            value = default_value
            value += (arg_value or [])
            value += (read_list_from_config(self, section, key) or [])
        elif arg_value is not None:
            value = arg_value
        elif config_value is not None:
            value = config_value
        else:
            value = default_value

        self._set(section, key, value)

    def _set(self, section, key, value):
        # Values from the "diff" section are also stored as arguments
        # for convenience
        if section == "diff":
            setattr(self, key, value)

        # Values stored in the config must be strings
        if isinstance(value, list):
            value = ", ".join(value)
        else:
            value = str(value)

        self[section][key] = value

    def update(self, key, value):
        for section, config in self.__sections.items():
            for attribute in config.keys():
                if attribute == key:
                    self._set(section, key, value)
                    return

        raise ValueError("Unkown key {}".format(key))


def setup():
    arguments = setup_argparser("difftool", "Shallow firmware diffing tool", sys.argv)
    config = Config(arguments)
    Logger.setup_logging(debug=config.debug, log_level=config.log_level, output_file=config.data_file)

    if config.sort_order.lower() == "distance" and not config.compute_distance:
        raise ValueError("Order set to distance, but computing distance is disabled")

    if config.min_dist >= 0 and not config.compute_distance:
        raise ValueError("min_dist set, but computing distance is disabled")

    if config.jobs is not None and config.jobs <= 0:
        raise ValueError("Number of jobs must be > 0")

    return config


def setup_argparser(name, description, command_line_options):
    parser = argparse.ArgumentParser(description="{} - {}".format(name, description))
    parser.add_argument("-o", "--output", dest="data_file", help="Path to file in which to write the list of files (- for stdout)", default="-")
    parser.add_argument("-L", "--log_level", help="Define the log level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default=None)
    parser.add_argument("-d", "--debug", action="store_true", help="Print debug messages", default=False)
    parser.add_argument("-C", "--config_file", help="Set path to config File", default=default_config_path())
    parser.add_argument("-j", "--jobs", help="Number of job to run in parallel (default to number of cpus)", type=int, default=None)
    parser.add_argument("--exclude", metavar="GLOB_PATTERN", action="append", help="Exclude files paths that match %(metavar)s.", default=["error/*", "inode/chardevice"])
    parser.add_argument("--exclude-mime", dest="exclude_mime", metavar="GLOB_PATTERN", action="append", help="Exclude files with mime types that match %(metavar)s.", default=[])
    parser.add_argument("--blacklist", metavar="MIME_TYPE", action="append", help="Exclude files with %(metavar)s.", default=[])
    parser.add_argument("--fuzzy-threshold", dest="fuzzy_threshold", help="Threshold for fuzzy-matching to detect moved files (<= 0 to disable, default is 80)", type=int, default=None)
    parser.add_argument("--max_depth", help="Maximum depth for recursive unpacking (< 0 for no limit)", type=int, default=None)
    parser.add_argument("--no-extract", action="store_false", dest="extract", help="Consider all files are already extracted, and only compare them", default=None)
    parser.add_argument("--no-specialize", action="store_false", dest="specialize", help="Do not use specific content comparison for known file types, but use simple binary data comparison", default=None)
    parser.add_argument("--no-distance", action="store_false", dest="compute_distance", help="Compute the distance between two modified files using TLSH", default=None)
    parser.add_argument("--order-by", dest="sort_order", help="Define the sort order for the output. Note: setting this to anything other than \"none\" will disable progressive output", choices=["none", "path", "distance"], default=None)
    parser.add_argument("--min_dist", help="Ignore files with a difference lower than the one given (< 0 for no limit)", type=int, default=None)
    parser.add_argument("--enable-statistics", action="store_true", dest="statistics", help="Compute statistics or check for unpack data loss", default=None)
    parser.add_argument("--profile", action="store_true", help="Measure the number of calls and time spent in different methods", default=False)

    parser.add_argument("FILE_PATH_1", type=str, help="Path to first file")
    parser.add_argument("FILE_PATH_2", type=str, help="Path to second file")

    argcomplete.autocomplete(parser)
    return parser.parse_args(command_line_options[1:])
