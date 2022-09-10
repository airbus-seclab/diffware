"""
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
import os
import sys
import logging

try:
    from helperFunctions.program_setup import setup_logging as fact_setup_logging
    FACT_FOUND = True
except ModuleNotFoundError:
    FACT_FOUND = False


class CustomFormatter(logging.Formatter):
    gray = "\033[37m"
    yellow = "\033[33m"
    red = "\033[91m"
    bold_red = "\033[1m"
    reset = "\033[0m"
    format = "%(message)s"

    FORMATS = {
        logging.DEBUG: gray + "[DEBUG] %(message)s" + reset,
        logging.INFO: "%(message)s",
        logging.WARNING: yellow + "[WARNING] %(message)s" + reset,
        logging.ERROR: red + "[ERROR] %(message)s" + reset,
        logging.CRITICAL: bold_red + "[CRITICAL] %(message)s" + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


class Logger():
    DEBUG = False
    LOGGING_LEVEL = logging.INFO
    OUTPUT_FILE = None
    SHOW_PROGRESS = True

    @staticmethod
    def setup_logging(debug=False, progress=True, log_level=logging.WARNING, output_file="-"):
        Logger.DEBUG = debug
        Logger.SHOW_PROGRESS = progress
        Logger.LOGGING_LEVEL = logging.DEBUG if debug else log_level
        if output_file != "-":
            Logger.OUTPUT_FILE = open(output_file, "w")

        if debug and FACT_FOUND:
            fact_setup_logging(debug, log_level=logging.DEBUG)
        else:
            # Hide info from FACT
            logger = logging.getLogger("")
            logger.setLevel(logging.WARNING)

            # Setup a simple formatter
            console_log = logging.StreamHandler()
            console_log.setFormatter(CustomFormatter())
            logger.addHandler(console_log)

    @staticmethod
    def cleanup():
        if Logger.OUTPUT_FILE:
            Logger.OUTPUT_FILE.close()

    @staticmethod
    def flush_output():
        if Logger.OUTPUT_FILE:
            Logger.OUTPUT_FILE.flush()
        else:
            sys.stdout.flush()

    # Define custom logging methods so as not to conflict with FACT's logging

    def _logger(func):
        def wrapper(*args, **kwargs):
            logger = logging.getLogger("")
            logger.setLevel(Logger.LOGGING_LEVEL)
            func(*args, **kwargs)
            if not Logger.DEBUG:
                logger.setLevel(logging.WARNING)

        return wrapper

    @staticmethod
    @_logger
    def error(*args, **kwargs):
        logging.error(*args, **kwargs)

    @staticmethod
    @_logger
    def warn(*args, **kwargs):
        logging.warn(*args, **kwargs)

    @staticmethod
    @_logger
    def info(*args, **kwargs):
        logging.info(*args, **kwargs)

    @staticmethod
    @_logger
    def debug(*args, **kwargs):
        logging.debug(*args, **kwargs)

    @staticmethod
    def output(*args, **kwargs):
        if Logger.OUTPUT_FILE is None:
            # Make sure the line is empty of any progress before printing
            print("\033[K", end="")
            print(*args, **kwargs)
        else:
            print(*args, **kwargs, file=Logger.OUTPUT_FILE)

    @staticmethod
    def progress(string):
        if not Logger.SHOW_PROGRESS:
            return

        # Make string take up exactly full width
        try:
            max_size = os.get_terminal_size()[0]
        except OSError:
            # Probably redirecting output to file or process
            max_size = 128

        format = "\033[2m{:<" + str(max_size) + "." + str(max_size) + "}\033[0m"
        print(format.format(string), end="\r")
