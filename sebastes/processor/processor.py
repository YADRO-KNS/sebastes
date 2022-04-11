import dataclasses
import os
import typing

from datamodel_code_generator.parser.base import Imports, Import

from sebastes.logger import log
from sebastes.parser import Parser, Result
from sebastes.scanner import RedfishData, RedfishCategory, Problem


@dataclasses.dataclass
class _ProcessedData:
    redfish_data: RedfishData
    result: Result


# noinspection PyBroadException
class FileProcessor:
    """
    File processor class responsible for lib creation
    """

    def __init__(self, redfish_datas: typing.List[RedfishData], base_dir: str):
        self._redfish_datas = redfish_datas
        self._base_dir = base_dir
        self._problems: typing.List[Problem] = []

    @property
    def problems(self) -> typing.List[Problem]:
        """
        List of processing problems
        """
        return self._problems

    @property
    def base_dir(self) -> str:
        """
        New library base directory
        """
        return self._base_dir

    @property
    def model_dir(self) -> str:
        """
        Model files sub-dir
        """
        return f'{self.base_dir}/models'

    def _prepare_folders(self) -> None:

        log.info(f'Preparing file structure for output in: {self.base_dir}')

        if os.path.isdir(self.model_dir):
            os.popen(f'rm -fr {self.model_dir}').read()
        os.mkdir(self.model_dir)
        common_script = f'{os.path.join(os.path.dirname(__file__))}/common.py'
        os.popen(f'cp {common_script} {self.model_dir}/common.py')

    def _process_data(self,
                      redfish_data: RedfishData,
                      child_data: typing.Optional[RedfishData] = None
                      ) -> typing.Optional[_ProcessedData]:
        log.info(f'Processing: {redfish_data}')
        try:
            parser = Parser(redfish_data, child_data)
            result = parser.results
            return _ProcessedData(redfish_data=redfish_data, result=result)
        except Exception as error:
            self._problems.append(
                Problem(
                    url=redfish_data.uri,
                    description=f'Unable process {redfish_data} - {redfish_data.data}: \n {error}'
                )
            )

    def _save_module(self, data: typing.List[str], imports: Imports, file_name: str) -> None:
        file_name = f'{self.model_dir}/{file_name}.py'
        total_data = "\n\n".join(data)
        with open(file_name, 'w') as file:
            file.write(f'{str(imports)}\n\n\n{total_data}')
            file.flush()

    def generate_lib(self) -> None:
        """
        Processes passed data and creates Redfish library
        """
        self._prepare_folders()

        log.info('Processing and saving Redfish data.')

        processed_data: typing.List[RedfishData] = []
        init_data: typing.List[typing.Tuple[str, typing.List[str]]] = []

        for data in self._redfish_datas:
            if data.category == RedfishCategory.ELEMENT:
                if data not in processed_data and data.parent not in processed_data:
                    processed_data.append(data)
                    processed_data.append(data.parent)
                    element = self._process_data(data)
                    collection = self._process_data(data.parent, data)
                    if element is None or collection is None:
                        log.warning(f'Skipping Collection processing: {data.parent} - {data}')
                        continue
                    imports = element.result.imports
                    for from_, targets in collection.result.imports.items():
                        for target in targets:
                            imports.append(Import(from_=from_, import_=target, alias=None))
                    file_name = collection.redfish_data.file_name
                    self._save_module([element.result.body, collection.result.body], imports, file_name)
                    init_data.append((file_name, [collection.redfish_data.full_name, element.redfish_data.full_name]))

        for data in self._redfish_datas:
            if data not in processed_data:
                processed_data.append(data)
                entry = self._process_data(data)
                if entry is None:
                    log.warning(f'Skipping Model processing: {data}')
                    continue
                body = entry.result.body
                imports = entry.result.imports
                file_name = entry.redfish_data.file_name
                self._save_module([body], imports, file_name)
                init_data.append((file_name, [entry.redfish_data.full_name]))

        init_data.append(('common', ['DataManager']))

        self._prepare_init_file(init_data)

    def _prepare_init_file(self, data: typing.List[typing.Tuple[str, typing.List[str]]]) -> None:
        log.info('Preparing init file.')

        data.sort()
        result = '__all__ = [\n'
        classes: typing.List[str] = []

        for _, classes_ in data:
            classes += classes_

        line = '\t'
        for c in classes:
            if (len(line) + len(c)) > 120:
                result += f'{line}\n'
                line = '\t'
            else:
                line += f'"{c}", '

        if line != '\t':
            result += f'{line}\n'
        result += ']\n\n'

        for file, classes_ in data:
            result += f'from .{file} import {", ".join(classes_)}\n'

        file_name = f'{self.model_dir}/__init__.py'

        with open(file_name, 'w') as f:
            f.write(result)
