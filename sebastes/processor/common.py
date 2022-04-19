import abc
import json
import typing

import pydantic
import requests
import urllib3

urllib3.disable_warnings()


class Action(pydantic.BaseModel):
    """
    Redfish Action model
    """

    target: str
    redfish_action_info: typing.Optional[str] = pydantic.Field(None, alias='@Redfish.ActionInfo')


class Link(pydantic.BaseModel):
    """
    Redfish Link model
    """

    odata_id: str = pydantic.Field(..., alias='@odata.id')


class Resource(Link):
    """
    Redfish Resource model
    """

    _url: str
    odata_type: str = pydantic.Field(..., alias='@odata.type')
    name: typing.Optional[str] = pydantic.Field(None, alias='Name')
    id: typing.Optional[str] = pydantic.Field(None, alias='Id')
    odata_context: typing.Optional[str] = pydantic.Field(None, alias='@odata.context')
    description: typing.Optional[str] = pydantic.Field(None, alias='Description')

    @classmethod
    def url(cls) -> str:
        """
        Resource URL
        """
        return cls._url


T = typing.TypeVar('T', bound=Resource)


class Collection(Resource):
    """
    Redfish Resource collection model
    """

    members_odata_count: int = pydantic.Field(..., alias='Members@odata.count')
    members: typing.List[Link] = pydantic.Field(..., alias='Members')
    members_odata_next_link: typing.Optional[str] = pydantic.Field(None, alias='Members@odata.nextLink')

    @classmethod
    @abc.abstractmethod
    def resource(cls) -> typing.Type[Resource]:
        """
        Linked Resource class for collection
        """
        pass


class DataManager:
    """
    Redfish connection class
    """

    def __init__(self, hostname: str, username: str, password: str):
        self._hostname = hostname
        self._username = username
        self._password = password

    def link_patch(self,
                   link: Link,
                   payload: typing.Optional[dict] = None,
                   pass_etag: bool = True
                   ) -> dict:
        """
        Call Patch request on specific link model
        :param link: Model to patch
        :param payload: Patch data
        :param pass_etag: boolean flag, is set as true, will attempt to
        use resource ETag value in PATCH request.
        :return: JSON response data
        """
        if payload is None:
            payload = {}
        headers = {'content-type': 'application/json'}
        base_url = f"https://{self._hostname}"
        url = f'{base_url}{link.odata_id}'

        if pass_etag is True:
            get_response = requests.get(
                url=url,
                headers=headers,
                verify=False,
                auth=(
                    self._username,
                    self._password
                )
            )
            if get_response.ok:
                etag = get_response.headers.get('etag')
                if etag is not None:
                    headers['If-Match'] = etag
            else:
                raise Exception(get_response.content.decode())

        response = requests.patch(
            url=url,
            headers=headers,
            verify=False,
            auth=(
                self._username,
                self._password
            ),
            data=json.dumps(payload)
        )
        if response.ok:
            return response.json()
        else:
            raise Exception(response.content.decode())

    def action_post(self, action: Action, payload: typing.Optional[dict] = None) -> dict:
        """
        Call action request for specific model.
        :param action: Model to call
        :param payload: Calls data.
        :return: JSON response data
        """
        if payload is None:
            payload = {}
        headers = {'content-type': 'application/json'}
        base_url = f"https://{self._hostname}"
        url = f'{base_url}{action.target}'

        response = requests.post(
            url=url,
            headers=headers,
            verify=False,
            auth=(
                self._username,
                self._password
            ),
            data=json.dumps(payload)
        )
        if response.ok:
            return response.json()
        else:
            raise Exception(response.content.decode())

    def get_json(self, url: str) -> dict:
        """
        Get JSON data from endpoint
        :param url: endpoint URL
        :return: JSON response data
        """
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

    def get_resource(self, resource: typing.Type[T], url: typing.Optional[str] = None) -> T:
        """
        Gets resource data from passed model class.
        :param resource: Model to get data for.
        :param url: Resource URL | optional
        :return: resource object
        """
        if url is None:
            url = resource.url()
        return resource(**self.get_json(url))

    def get_collection(self,
                       collection: typing.Type[Collection],
                       resource: typing.Type[T],
                       url: typing.Optional[str] = None
                       ) -> typing.List[T]:
        """
        Gets collection data from endpoint and returns list of all member resources
        :param collection: Collection class
        :param resource: Target resource to map data
        :param url: collection URL | optional
        :return: list of resource objects
        """
        if url is None:
            url = collection.url()

        result = []
        collection_data = self.get_resource(collection, url)

        for member in collection_data.members:
            member_data = self.get_resource(resource, member.odata_id)
            result.append(member_data)

        return result
