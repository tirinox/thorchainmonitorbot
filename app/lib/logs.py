import logging
import sys

from colorama import init, Fore
from pythonjsonlogger.json import JsonFormatter

from lib.config import Config

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
    logger = logging.getLogger(prefix + self.__class__.__name__)
    return logger


def setup_logs(log_level, is_std_out=True, style='colorful'):
    global g_log_level
    g_log_level = logging.getLevelName(log_level)

    stream = sys.stdout if is_std_out else sys.stderr
    handler = logging.StreamHandler(stream)

    if style == 'json':
        formatter = JsonFormatter(
            "{levelname}{message}{asctime}{exc_info}",
            style='{',
            json_ensure_ascii=False,
        )
    else:
        if style == 'colorful':
            handler.setLevel(logging.DEBUG)
            formatter_factory = ColorFormatter
        elif style == 'normal':
            formatter_factory = logging.Formatter
        else:
            print("Unknown log style:", style)
            sys.exit(-2)
        formatter = formatter_factory(
            '[%(levelname)s] | %(asctime)s | %(name)s | %(funcName)s | "%(message)s"',
            datefmt='%Y-%m-%d %H:%M:%S',
        )

    handler.setFormatter(formatter)
    logging.basicConfig(
        level=g_log_level,
        handlers=[handler],
        force=True
    )


def setup_logs_from_config(cfg: Config, log_level=None):
    log_level = log_level or cfg.get_pure('logs.level', logging.INFO)
    log_level = log_level.upper().strip()

    log_style = cfg.as_str('logs.style', 'colorful')
    setup_logs(log_level, style=log_style)
    return log_level
