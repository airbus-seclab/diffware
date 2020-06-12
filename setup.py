import sys
import pathlib
import argparse
import argcomplete
from logger import Logger
from configparser import ConfigParser

from helperFunctions.program_setup import merge_options


def setup():
    arguments = setup_argparser("difftool", "Shallow firmware diffing tool", sys.argv)
    Logger.setup_logging(debug=arguments.debug, log_level=arguments.log_level, output_file=arguments.data_file)

    if arguments.sort_order.lower() == "distance" and not arguments.compute_distance:
        raise ValueError("Order set to distance, but computing distance is disabled")

    if arguments.min_dist >= 0 and not arguments.compute_distance:
        raise ValueError("min_dist set, but computing distance is disabled")

    return arguments


def default_config_path():
    current_dir = pathlib.Path(__file__).parent.absolute()
    return current_dir / "fact.cfg"


def setup_argparser(name, description, command_line_options):
    parser = argparse.ArgumentParser(description="{} - {}".format(name, description))
    parser.add_argument("-o", "--output", dest="data_file", help="Path to file in which to write the list of files (- for stdout)", default="-")
    parser.add_argument("-L", "--log_level", help="Define the log level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    parser.add_argument("-d", "--debug", action="store_true", help="Print debug messages", default=False)
    parser.add_argument("-C", "--config_file", help="set path to config File", default=default_config_path())
    parser.add_argument("--exclude", metavar="GLOB_PATTERN", action="append", help="Exclude files paths that match %(metavar)s.", default=["error/*", "inode/chardevice"])
    parser.add_argument("--exclude-mime", dest="exclude_mime", metavar="GLOB_PATTERN", action="append", help="Exclude files with mime types that match %(metavar)s.", default=[])
    parser.add_argument("--blacklist", metavar="MIME_TYPE", action="append", help="Exclude files with %(metavar)s.", default=[])
    parser.add_argument("--max_depth", help="Maximum depth for recursive unpacking (< 0 for no limit)", type=int, default=5)
    parser.add_argument("--no-extract", action="store_false", dest="extract", help="Consider all files are already extracted, and only compare them", default=True)
    parser.add_argument("--no-specialize", action="store_false", dest="specialize", help="Do not use specific content comparison for known file types, but use simple binary data comparison", default=True)
    parser.add_argument("--no-distance", action="store_false", dest="compute_distance", help="Compute the distance between two modified files using TLSH", default=True)
    parser.add_argument("--order-by", dest="sort_order", help="Define the sort order for the output. Note: setting this to anything other than \"none\" will disable progressive output", choices=["none", "path", "distance"], default="none")
    parser.add_argument("--min_dist", help="Ignore files with a difference lower than the one given (< 0 for no limit)", type=int, default=-1)
    parser.add_argument("--enable-statistics", action="store_true", dest="statistics", help="Compute statistics or check for unpack data loss", default=None)
    parser.add_argument("--profile", action="store_true", help="Measure the number of calls and time spent in different methods", default=False)

    parser.add_argument("FILE_PATH_1", type=str, help="Path to first file")
    parser.add_argument("FILE_PATH_2", type=str, help="Path to second file")

    argcomplete.autocomplete(parser)
    return parser.parse_args(command_line_options[1:])


def get_config(arguments, data_folder_key, data_folder_fallback):
    config = ConfigParser()
    config.read(arguments.config_file)
    arguments.data_folder = config.get("unpack", data_folder_key, fallback=data_folder_fallback)
    config = merge_options(arguments, config)
    return config
