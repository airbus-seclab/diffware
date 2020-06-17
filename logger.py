import os
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
        logging.DEBUG: gray + format + reset,
        logging.INFO: format,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset
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

        format = "\33[90m{:<" + str(max_size) + "." + str(max_size) + "}\033[0m"
        print(format.format(string), end="\r")
