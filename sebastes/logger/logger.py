import logging
import sys
import typing

SUCCESS = 25


class CustomFormatter(logging.Formatter):
    """Logging Formatter to add colors and count warning / errors"""

    light_grey = '\037[40m'
    grey = '\033[90m'
    yellow = '\033[93m'
    white = '\33[97m'
    red = '\033[91m'
    green = '\033[92m'
    bold_red = '\033[91m\033[1m'
    blue = '\033[34m'
    cyan = '\033[46m'
    reset = '\033[0m'

    colorless = ''

    custom_format_short = "%(asctime)s - %(name)s - %(message)s"

    FORMATS = {
        logging.DEBUG: light_grey,
        logging.INFO: white,
        SUCCESS: green,
        logging.WARNING: yellow,
        logging.ERROR: red,
        logging.CRITICAL: bold_red
    }

    def __init__(self) -> None:
        super().__init__(fmt=self.custom_format_short, datefmt='%Y-%m-%d %H:%M:%S')

    def format(self, record: logging.LogRecord) -> str:
        """
        Formats passed record.
        """
        if record.exc_info is not None:
            return f'\n{self.red}{super(CustomFormatter, self).format(record)}{self.reset}\n'
        else:
            return f'{self.FORMATS.get(record.levelno)}{super(CustomFormatter, self).format(record)}{self.reset}'


class CustomLogger(logging.Logger):
    """
    Custom logger class with colorful output :3
    """

    def __init__(self, name: str, level: int = logging.DEBUG):
        super().__init__(name)
        self.setLevel(level=self.level)
        self._primary_handler = logging.StreamHandler(stream=sys.stdout)
        self._primary_handler.setLevel(level=level)
        self._primary_handler.setFormatter(CustomFormatter())
        self.addHandler(self._primary_handler)
        logging.addLevelName(SUCCESS, 'SUCCESS')

    def progress_bar(self,  # type: ignore
                     iteration: int,
                     total: int,
                     level: int = logging.INFO,
                     prefix: str = '',
                     suffix: str = '',
                     decimals: int = 1,
                     length: int = 80,
                     show_percent: bool = True,
                     *args, **kwargs) -> None:
        """
        Call in a loop to create terminal progress bar
        @params:
            iteration   - Required  : current iteration (Int)
            total       - Required  : total iterations (Int)
            level       - Optional  : logging level (Int)
            prefix      - Optional  : prefix string (Str)
            suffix      - Optional  : suffix string (Str)
            decimals    - Optional  : positive number of decimals in percent complete (Int)
            length      - Optional  : character length of bar (Int)
        """
        fill: str = '█'
        progress = 100 * (iteration / float(total))
        if progress > 100:
            progress = 100
        if show_percent:
            percent = ("{0:." + str(decimals) + "f}%").format(progress)
        else:
            percent = ""
        filled_length = int(length * iteration // total)
        if filled_length > length:
            filled_length = length
        bar = fill * filled_length + '-' * (length - filled_length)
        self._primary_handler.terminator = '\n' if iteration >= total else '\r'
        self._log(level, f'\r{prefix} |{bar}| {percent} {suffix}', args, **kwargs)
        self._primary_handler.flush()
        self._primary_handler.terminator = '\n'

    def success(self, msg, *args, **kwargs):  # type: ignore
        """
        Log 'msg % args' with severity 'SUCCESS'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        logger.success("Houston, we have a %s", "major success", exc_info=1)
        """
        if self.isEnabledFor(SUCCESS):
            self._log(SUCCESS, msg, args, **kwargs)

    def direct(self, msg: str, end: typing.Optional[str] = None) -> None:
        """
        Directly wrights message into stdout without formatting and level validation.
        For passing out machine-readable output.
        :param msg - message string
        :param end - optional custom terminator
        """
        if not end:
            self._primary_handler.stream.write(f'{msg}{self._primary_handler.terminator}')
        else:
            self._primary_handler.stream.write(f'{msg}{end}')

        self._primary_handler.flush()
