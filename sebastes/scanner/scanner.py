import dataclasses
import enum
import functools
import json
import random
import re
import typing

import genson
import requests
import urllib3

from sebastes.logger import log

urllib3.disable_warnings()


class RedfishCategory(enum.Enum):
    """
    Redfish scan category
    """

    RESOURCE = 'Resource'
    COLLECTION = 'Collection'
    ELEMENT = 'Element'
    UNKNOWN = '???'


@dataclasses.dataclass
class Problem:
    """
    Problem dataclass
    """

    url: str
    description: str

    def __str__(self) -> str:
        return f'{self.url} - {self.description}'


class RedfishData:
    """
    Scanned Redfish data class
    """

    def __init__(self, name: str, data: dict, uri: str, parent: typing.Optional['RedfishData']):
        self._name = name
        self._data = data
        self._uri = uri
        self._parent = parent

    @property
    def uri(self) -> str:
        """
        Data URI
        """
        return self._uri

    @property
    def data(self) -> dict:
        """
        Raw JSON data
        """
        return self._data

    @property
    def schema(self) -> str:
        """
        Data's JSON schema
        """
        builder = genson.SchemaBuilder()
        builder.add_object(self.data)
        return json.dumps(builder.to_schema())

    @property
    def category(self) -> RedfishCategory:
        """
        Redfish model Category
        """
        if 'collection' in self._name.lower():
            return RedfishCategory.COLLECTION
        elif self.parent is not None and \
                self.parent.category == RedfishCategory.COLLECTION and \
                self.name in self.parent.name:
            return RedfishCategory.ELEMENT
        else:
            return RedfishCategory.RESOURCE

    @property
    def parent(self) -> typing.Optional['RedfishData']:
        """
        Model parent
        """
        return self._parent

    @property
    def name(self) -> str:
        """
        Redfish model name
        """
        return self._name

    @property
    def full_name(self) -> str:
        """
        Model full name, created from own and parents names
        """
        if self.parent is not None:
            return f'{self._parent.name}{self.name}'
        else:
            return self.name

    @functools.cached_property
    def file_name(self) -> str:
        """
        Snake case form of model name, for files
        """
        file_name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', self.full_name)
        file_name = re.sub('__([A-Z])', r'_\1', file_name)
        file_name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', file_name)
        return file_name.lower()

    @functools.cached_property
    def collection_uris(self) -> typing.List[str]:
        """
        All child URIs in data
        """
        result: typing.List[str] = []
        for key, _ in self._data.items():
            if key == 'Members':
                for entry in self._data['Members']:
                    if type(entry) is dict:
                        uri = entry.get('@odata.id', None)
                        if uri is not None:
                            result.append(uri)
        return result

    @functools.cached_property
    def description(self) -> typing.Optional[str]:
        """
        Possible OData description from Name and Description fields
        """
        result = None
        if self._data.get('Name', None):
            result = self._data.get('Name', None)
        if self._data.get('Description', None):
            if result is None:
                result = self._data.get('Description', None)
            else:
                result = f'{result}: {self._data.get("Description", None)}'
        return result

    def __str__(self) -> str:
        return f'{self.category.value} - {self.full_name}'

    def __eq__(self, other: typing.Any) -> bool:
        if isinstance(other, self.__class__):
            return other.full_name == self.full_name
        else:
            return False


# noinspection PyBroadException
class Scanner:
    """
    Redfish scanner nuff said
    """

    def __init__(self, hostname: str, username: str, password: str, max_models: int = 1000, max_collection: int = 50):
        self._hostname = hostname
        self._username = username
        self._password = password
        self._max_models = max_models
        self._max_collection = max_collection
        self._redfish: typing.List[RedfishData] = []
        self._scanned_uris: typing.List[str] = []
        self._problems: typing.List[Problem] = []

    @property
    def problems(self) -> typing.List[Problem]:
        """
        Problems detected during scan
        """
        return self._problems

    @property
    def redfish_datas(self) -> typing.List[RedfishData]:
        """
        List of collected RedfishDatas
        """
        return self._redfish

    @staticmethod
    def _get_model_name(data: dict) -> typing.Optional[str]:
        odata_type = data.get('@odata.type', None)
        if odata_type is not None:
            value = odata_type.split('.')[-1]
            value = value.replace('collection', 'Collection')
            value = value.replace('entry', 'Entry')
            value = value[0].upper() + value[1:]
            return value

    def _get_uris(self, data: dict) -> typing.List[str]:
        result: typing.List[str] = []
        for key, value in data.items():
            if key == '@odata.id' and value not in result:
                result.append(value)
            if key == 'Members':
                if len(data['Members']) > self._max_collection:
                    for _entry in random.sample(data['Members'], self._max_collection):
                        result += self._get_uris(_entry)
                else:
                    for _entry in data['Members']:
                        result += self._get_uris(_entry)
            if isinstance(value, dict):
                result += self._get_uris(value)
        return result

    def _get_json(self, url: str) -> dict:
        headers = {'content-type': 'application/json'}
        base_url = f"https://{self._hostname}"
        url = f'{base_url}{url}'
        response = requests.get(
            url=url,
            headers=headers,
            verify=False,
            auth=(
                self._username,
                self._password
            )
        )
        if response.ok:
            return response.json()
        else:
            raise Exception(response.content.decode())

    def scan_models(self, entry_point: str = "/redfish/v1/", parent: typing.Optional[RedfishData] = None) -> None:
        """
        Scan target endpoint and all it's children.
        :param entry_point: scan start point
        :param parent: possible scan parent RedfishData
        """
        if len(self._redfish) < self._max_models:
            if entry_point not in self._scanned_uris and 'jsonschemas' not in entry_point.lower():
                self._scanned_uris.append(entry_point)
                model: typing.Optional[RedfishData] = None
                if parent is not None:
                    log.info(f'[{len(self._redfish)}] Scanning: {entry_point} parent is {parent}')
                else:
                    log.info(f'[{len(self._redfish)}] Scanning: {entry_point}')

                try:
                    data = self._get_json(entry_point)
                    name = self._get_model_name(data)

                    if (parent is None or parent.name != name) and name is not None:
                        model = RedfishData(name=name, data=data, uri=entry_point, parent=parent)
                        if model not in self._redfish:
                            self._redfish.append(model)

                    for uri in self._get_uris(data):
                        if uri not in self._scanned_uris:
                            self.scan_models(entry_point=uri, parent=model)
                except Exception as error:
                    self._problems.append(Problem(url=entry_point, description=str(error)))
        else:
            log.info(f'Models limit was reached - {self._max_models}')
