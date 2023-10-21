import logging
import sys

from colorama import init, Fore, Back

init(autoreset=True)
g_log_level = logging.INFO


class WithLogger:
    @property
    def logger_prefix(self):
        return ''

    def __init__(self):
        super(WithLogger, self).__init__()
        self.logger = class_logger(self, self.logger_prefix)


class ColorFormatter(logging.Formatter):
    # Change this dictionary to suit your coloring needs!
    COLORS = {
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "DEBUG": Fore.BLUE,
        "INFO": Fore.GREEN,
        "CRITICAL": Fore.RED
    }

    def format(self, record):
        color = self.COLORS.get(record.levelname, "")
        message = logging.Formatter.format(self, record)
        if color:
            message = color + message + Fore.RESET
        return message


def class_logger(self, prefix=''):
    # global g_log_level
    # return logging.getLogger()

    logger = logging.getLogger(prefix + self.__class__.__name__)
    # logger.setLevel(g_log_level)
    return logger


def setup_logs(log_level, is_std_out=True, colorful=True):
    global g_log_level
    g_log_level = logging.getLevelName(log_level)

    stream = sys.stdout if is_std_out else sys.stderr
    handler = logging.StreamHandler(stream)
    formatter = ColorFormatter if colorful else logging.Formatter
    handler.setFormatter(formatter(
        '[%(levelname)s] | %(asctime)s | %(name)s | %(funcName)s | "%(message)s"',
        datefmt='%Y-%m-%d %H:%M:%S',
    ))

    logging.basicConfig(
        level=g_log_level,
        handlers=[handler],
        force=True
    )
