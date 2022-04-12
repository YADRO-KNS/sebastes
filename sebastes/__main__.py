import argparse
import os

from sebastes.logger import log
from sebastes.processor import FileProcessor
from sebastes.scanner import Scanner


def dir_path(value: str) -> str:
    """

    :param value:
    :return:
    """
    if os.path.isdir(value):
        return value
    else:
        os.makedirs(value, exist_ok=True)
        return value


parser = argparse.ArgumentParser(description='Pydantic library code generator for Redfish targets')
parser.add_argument(
    '-a',
    action='store',
    dest='hostname',
    type=str,
    required=True,
    help='DNS name or IP address of Redfish target'
)
parser.add_argument(
    '-u',
    action='store',
    dest='username',
    type=str,
    required=True,
    help='Target username'
)
parser.add_argument(
    '-p',
    action='store',
    dest='password',
    type=str,
    required=True,
    help='Target password'
)
parser.add_argument(
    '-o',
    action='store',
    dest='output',
    type=dir_path,
    required=True,
    help='Output directory'
)
parser.add_argument(
    '-e',
    action='store',
    nargs='?',
    dest='entry_point',
    type=str,
    default='/redfish/v1/',
    help="Redfish entry point | optional default is '/redfish/v1/'"
)
parser.add_argument(
    '-m',
    action='store',
    nargs='?',
    dest='max_models',
    type=int,
    default=500,
    help='Max Models to scan | optional default is 500'
)
parser.add_argument(
    '-c',
    action='store',
    nargs='?',
    dest='max_collection',
    type=int,
    default=50,
    help='Max Collection elements to sample from | optional default is 50')

args = parser.parse_args()


def main() -> None:
    """
    Le main function
    """
    addr = args.hostname
    username = args.username
    password = args.password
    output = args.output
    entry_point = args.entry_point
    max_models = args.max_models
    max_collection = args.max_collection

    log.info(f'Scanning Redfish API for {addr}')
    scanner = Scanner(
        hostname=addr,
        username=username,
        password=password,
        max_models=max_models,
        max_collection=max_collection
    )
    scanner.scan_models(entry_point=entry_point)

    if len(scanner.problems) != 0:
        log.warning(f'Detected {len(scanner.problems)} problem during scan:')
        for index, problem in enumerate(scanner.problems, start=1):
            log.warning(f'{index} - {problem}')

    log.info(f'Detected {len(scanner.redfish_datas)} unique Redfish models:')
    for index, _model in enumerate(scanner.redfish_datas, start=1):
        log.info(f'{index}. {_model}')

    processor = FileProcessor(scanner.redfish_datas, output)
    processor.generate_lib()

    if len(processor.problems) != 0:
        log.warning(f'Detected {len(processor.problems)} problem during processing:')
        for index, problem in enumerate(processor.problems, start=1):
            log.warning(f'{index} - {problem}')

    log.success(f'Done! Check output data in: {output}')


if __name__ == '__main__':
    main()
