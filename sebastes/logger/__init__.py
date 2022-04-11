__all__ = [
    'log',
    'SUCCESS',
    'INFO',
    'WARNING',
    'ERROR',
    'DEBUG',
    'CRITICAL',
    'FATAL',
]

from logging import INFO, ERROR, DEBUG, CRITICAL, WARNING, FATAL

from .logger import CustomLogger
from .logger import SUCCESS

log = CustomLogger('RMG')
