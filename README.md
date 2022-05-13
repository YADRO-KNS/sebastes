    o le  o
                  /^^^^^7
    '  '     ,oO))))))))Oo,
           ,'))))))))))))))), /{
      '  ,'o  ))))))))))))))))={
         >    )))Sebastes)))))={
         `,   ))))))\ \)))))))={
           ',))))))))\/)))))' \{
             '*O))))))))O*'

# Sebastes

![PyPI - Status](https://img.shields.io/pypi/status/sebastes.svg)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/sebastes.svg)
[![Downloads](https://pepy.tech/badge/sebastes/month)](https://pepy.tech/project/sebastes)
![PyPI](https://img.shields.io/pypi/v/sebastes.svg)
![PyPI - License](https://img.shields.io/pypi/l/sebastes.svg)
----
Hey hey people! Sebastes is simple code generator for **[Redfish](https://redfish.dmtf.org/)** compatible targets (i.e. server, storage systems, network equipment). It recursively scans target Redfish
endpoints and creates organized python modules with **[Pydantic](https://pydantic-docs.helpmanual.io/)** models. Forget about spending hours on boilerplate code, just make it within a couple of
minutes!

## Getting started

### Confirmed support

* Dell:
    * Х2-740Х
* Huawei:
    * 2288H V5
    * 2288H V5 (10GE SFP+)
* YADRO:
    * Vegman N110
* Intel:
    * S2600WFT

### Prerequisites

**sebastes** requires python 3.9 or newer versions to run. Currently, only UNIX os is supported.

### Installing

Cloning project from git repository

```bash
git clone https://github.com/YADRO-KNS/sebastes.git
```

Installing from PyPi

```bash
pip3 install sebastes
```

## Usage

The `sebastes` command:

```bash
usage: sebastes [-h] -a HOSTNAME -u USERNAME -p PASSWORD -o OUTPUT [-e [ENTRY_POINT]] [-m [MAX_MODELS]] [-c [MAX_COLLECTION]]

optional arguments:
  -h, --help           show this help message and exit
  -a HOSTNAME          DNS name or IP address of Redfish target
  -u USERNAME          Target username
  -p PASSWORD          Target password
  -o OUTPUT            Output directory
  -e [ENTRY_POINT]     Redfish entry point | optional default is '/redfish/v1/'
  -m [MAX_MODELS]      Max Models to scan | optional default is 500
  -c [MAX_COLLECTION]  Max Collection elements to sample from | optional default is 50
```

## Example

### Scanning target

```sh
# Generate library code from remote server Redfish data.
$ sebastes -a 192.168.1.3 -u admin -p le-pass -o /tmp/output/lib
```

### Generated lib structure

After scanning, Sebastes will create a python module in the output folder with the following structure:

```
.
└── models
    ├── __init__.py
    ├── common.py
    ├── service_root.py
    ├── some_other_resourse.py
    └── ...
```

## Working with generated code

Init file will be created automatically. It will contain imports from common script and root models from all of the scanned endpoints.

Redfish have a limited list of model types. Matching models will be re-inherited from respective classes defined in common script:

* **Link** - the simplest type of model containing a link to some resource.
* **Action** - similar to Link but contains URI of some possible action.
* **Resource** - main model type, contains a set of mandatory fields defined in parent class, all other fields will be created based on response data. Also for root model resources _url field will be
  filled with model location data.
* **Collection** - similar to Resource, has a couple of specific fields with links to its members. For root model collections _url field will be filled with model location data.

Regardless of what type of data you want to access in Redfish, the first thing you need to do is to create a **DataManager** instance. This class provides methods for interaction with pydantic models.

### Getting Resource

To get Resource data you need to call get_resource method of DataManager object and pass required model class to map data into. Models _url field will be used as default data location, you can
manually replace it with your own value.

```python
def get_resource(self, resource: typing.Type[T], url: typing.Optional[str] = None) -> T:
    """
    Gets resource data from passed model class.
    :param resource: Model to get data for.
    :param url: Resource URL | optional
    :return: resource object
    """
    ...
```

```python
from .models import DataManager, ServiceRoot


if __name__ == '__main__':
    manager = DataManager('192.168.1.3', 'admin', 'le-pass')
    service_root = manager.get_resource(ServiceRoot)
    print(service_root.host_name)
```

### Getting Collection members

To get a collection you need to provide not only a collection model class but also a model for collection elements. For some root models elements classes will be available via resource class method.

```python
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
    ...
```

```python
from .models import DataManager,  LogServiceEntries


if __name__ == '__main__':
    manager = DataManager('192.168.1.3', 'admin', 'le-pass')
    for log in manager.get_collection(LogServiceEntries, LogServiceEntries.resource()):
        print(log.created, log.message, log.severity)
```

And just as with Resource you can provide your own URL value to get data from. For nested collections it is the only way:

```python
from .models import DataManager, NetworkInterfaces, NetworkPorts


if __name__ == '__main__':
    manager = DataManager('192.168.1.3', 'admin', 'le-pass')
    for interface in manager.get_collection(NetworkInterfaces, NetworkInterfaces.resource()):
        url = interface.network_ports.odata_id
        for port in manager.get_collection(NetworkPorts, NetworkPorts.resource(), url=url):
            print(interface.name, port.name, port.mac)
```

### Calling Action request

When you need to activate some Redfish action all you have to do is pass an Action object. Payload is optional.

```python
def action_post(self, action: Action, payload: typing.Optional[dict] = None) -> dict:
    """
    Call action request for specific model.
    :param action: Model to call
    :param payload: Calls data.
    :return: JSON response data
    """
    ...
```

```python
from .models import DataManager, ComputerSystem


if __name__ == '__main__':
    manager = DataManager('192.168.1.3', 'admin', 'le-pass')
    computer_system = manager.get_resource(ComputerSystem)
    manager.action_post(computer_system.actions.computer_system_reset, payload={'ResetType': 'On'})
```

### Patching Resource

Some Redfish endpoints support patching. The link_patch method will call a passed link object and get it’s Etag value (if there is any) and then will perform a patch request with passed payload data.

```python
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
    ...
```

```python
from .models import DataManager, Bios


if __name__ == '__main__':
    manager = DataManager('192.168.1.3', 'admin', 'le-pass')
    bios = manager.get_resource(Bios)
    payload = {
        'Attributes': {
            'BootType': 'UEFIBoot'
        }
    }
    manager.link_patch(bios.redfish_settings.settings_object, payload)
```

## Versioning

We use [SemVer](http://semver.org/) for versioning.

## Authors

* **[Sergey Parshin](https://github.com/shooshp)**

See also the list of [contributors](https://github.com/YADRO-KNS/py-lspci/graphs/sebastes) who participated in this project.

## Acknowledgments

* sebastes inspired and based on **[datamodel-code-generator](https://github.com/koxudaxi/datamodel-code-generator)** by **[Koudai Aono](https://github.com/koxudaxi)**

## License

The code is available as open source under the terms of the [MIT License](LICENSE).
