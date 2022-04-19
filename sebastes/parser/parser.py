import dataclasses
import enum
import functools
import itertools
import pathlib
import typing

from datamodel_code_generator.format import PythonVersion
from datamodel_code_generator.model.pydantic import (
    BaseModel,
    DataModelField
)
from datamodel_code_generator.parser.base import (
    sort_data_models,
    Reference,
    ModelResolver,
    Imports,
    Import,
    BaseClassDataType,
    relative,
    dump_templates,
    CodeFormatter,
    DataType
)
from datamodel_code_generator.parser.jsonschema import JsonSchemaParser

from sebastes.scanner import RedfishData


@dataclasses.dataclass
class Result:
    """
    Parsing result data class
    """

    body: str
    imports: Imports
    model_names: typing.List[str]


class DataModelCategory(enum.Enum):
    """
    Redfish parse category
    """

    ACTION = 'Action'
    LINK = 'Link'
    RESOURCE = 'Resource'
    COLLECTION = 'Collection'
    UNKNOWN = '???'


category_fields: typing.Dict[DataModelCategory, typing.List[str]] = {
    DataModelCategory.LINK: ['odata_id'],
    DataModelCategory.ACTION: ['target'],
    DataModelCategory.RESOURCE: ['odata_id', 'odata_type'],
    DataModelCategory.COLLECTION: ['odata_id', 'odata_type', 'members_odata_count', 'members']
}

optional_fields: typing.Dict[DataModelCategory, typing.List[str]] = {
    DataModelCategory.LINK: [],
    DataModelCategory.ACTION: ['redfish_action_info'],
    DataModelCategory.RESOURCE: ['id', 'odata_context', 'description', 'name'],
    DataModelCategory.COLLECTION: ['id', 'odata_context', 'description', 'name', 'members_odata_next_link'],
}


class CustomDataModel(BaseModel):
    """
    Custom model class for Redfish parsing
    """

    _replace_words = [
        ('_odata_id', 'odata_id'),
        ('_odata_context', 'odata_context'),
        ('_odata_type', 'odata_type'),
        ('__redfish__action_info', 'redfish_action_info'),
        ('__', '_')
    ]

    def __init__(self,
                 *,
                 reference: Reference,
                 fields: typing.List[DataModelField],
                 decorators: typing.Optional[typing.List[str]] = None,
                 base_classes: typing.Optional[typing.List[Reference]] = None,
                 custom_base_class: typing.Optional[str] = None,
                 custom_template_dir: typing.Optional[pathlib.Path] = None,
                 extra_template_data: typing.Optional[typing.DefaultDict[str, typing.Any]] = None,
                 path: typing.Optional[pathlib.Path] = None,
                 description: typing.Optional[str] = None):

        super().__init__(
            reference=reference,
            fields=self.process_fields(fields),
            decorators=decorators,
            base_classes=base_classes,
            custom_base_class=custom_base_class,
            custom_template_dir=custom_template_dir,
            extra_template_data=extra_template_data,
            path=path,
            description=description,
        )
        self._url: typing.Optional[str] = None

    def process_fields(self, fields: typing.List[DataModelField]) -> typing.List[DataModelField]:
        """Replaces field names according to specific dictionary"""
        result: typing.List[DataModelField] = []
        for field in fields:
            for old, new in self._replace_words:
                field.name = field.name.replace(old, new)
            result.append(field)
        return result

    def _fields_are_present(self, names: typing.List[str]) -> bool:
        field_names = [field.name for field in self.fields]
        for name in names:
            if name not in field_names:
                return False
        return True

    @property
    def category(self) -> DataModelCategory:
        """
        Processed Redfish model category
        """
        category = DataModelCategory.UNKNOWN
        for _cat, fields in category_fields.items():
            if self._fields_are_present(fields):
                category = _cat
        return category

    def __repr__(self) -> str:
        return f'{self.category.value} - {self.name}'


class Parser:
    """
    Redfish data convertor into pydantic models
    """

    def __init__(self, redfish_data: RedfishData, child_data: typing.Optional[RedfishData]):
        self._redfish_data = redfish_data
        self._child_data = child_data
        self._base_class = 'pydantic.BaseModel'

    @property
    def model_names(self) -> typing.List[str]:
        """List of names of all models in Redfish data"""
        return [m.name for m in self._get_data_models()]

    @functools.cached_property
    def _parser(self) -> JsonSchemaParser:
        parser = JsonSchemaParser(
            data_model_type=CustomDataModel,
            source=self._redfish_data.schema,
            base_class=self._base_class,
            target_python_version=PythonVersion.PY_39,
            snake_case_field=True,
            class_name=self._redfish_data.full_name,
            reuse_model=True,
        )
        parser.parse_raw()
        return parser

    @staticmethod
    def _get_data_type(
            category: DataModelCategory,
            collection: typing.Optional[str] = None,
            is_optional: bool = False) -> DataType:
        data_type = DataType(
            type=category.value,
            import_=Import(
                from_='.common',
                import_=category.value,
                alias=None),
            is_optional=is_optional,
            is_dict=collection == 'Dict',
            is_list=collection == 'List',
            is_func=False,
            is_custom_type=True,
            strict=True,
            kwargs=None)
        return data_type

    def _get_code_formatter(self) -> CodeFormatter:
        return CodeFormatter(self._parser.target_python_version, None, self._parser.wrap_string_literal)

    @functools.lru_cache()  # noqa: B019
    def _get_data_models(self) -> typing.List[CustomDataModel]:
        models = self._parser.results
        models = self._update_collection_methods(models)
        models = self._clean_up_models(models, category=DataModelCategory.LINK)
        models = self._clean_up_models(models, category=DataModelCategory.ACTION)
        models = self._update_classes(models, category=DataModelCategory.RESOURCE)
        models = self._update_classes(models, category=DataModelCategory.COLLECTION)
        models = self._update_description(models)
        models = self._update_url(models)
        models = self._update_root_model_name(models)
        return models

    def _get_cleaned_models(self) -> typing.List[CustomDataModel]:  # noqa: C901
        models: typing.List[CustomDataModel] = []

        _, sorted_models, _ = sort_data_models(self._get_data_models())
        sorted_models = sorted(sorted_models.values(), key=lambda x: x.module_path, reverse=True)
        grouped_models = itertools.groupby(sorted_models, key=lambda x: x.module_path)
        for _, group in grouped_models:
            models += list(group)

        for model in models:
            if isinstance(model, self._parser.data_model_root_type):
                root_data_type = model.fields[0].data_type

                # backward compatible Remove duplicated root model
                if (
                        root_data_type.reference
                        and not root_data_type.is_dict
                        and not root_data_type.is_list
                        and root_data_type.reference.source in models
                        and root_data_type.reference.name
                        == self._parser.model_resolver.get_class_name(model.reference.original_name, unique=False)
                ):
                    # Replace referenced duplicate model to original model
                    for child in model.reference.children[:]:
                        child.replace_reference(root_data_type.reference)
                    models.remove(model)
                    continue

                #  Custom root model can't be inherited on restriction of Pydantic
                for child in model.reference.children:
                    # inheritance model
                    if isinstance(child, CustomDataModel):
                        for base_class in child.base_classes:
                            if base_class.reference == model.reference:
                                child.base_classes.remove(base_class)
                        if not child.base_classes:
                            child.set_base_class()

        scoped_model_resolver = ModelResolver(
            exclude_names={i.alias or i.import_ for m in models for i in m.imports},
            duplicate_name_suffix='Model',
        )

        for model in models:
            class_name: str = model.class_name
            generated_name: str = scoped_model_resolver.add(model.path, class_name, unique=True, class_name=True).name
            if class_name != generated_name:
                if '.' in model.reference.name:
                    model.reference.name = f"{model.reference.name.rsplit('.', 1)[0]}.{generated_name}"
                else:
                    model.reference.name = generated_name

        return models

    def _update_description(self, models: typing.List[CustomDataModel]) -> typing.List[CustomDataModel]:
        if self._redfish_data.description is not None:
            for model in models:
                if model.name == self._redfish_data.full_name:
                    model.description = self._redfish_data.description
        return models

    def _update_root_model_name(self, models: typing.List[CustomDataModel]) -> typing.List[CustomDataModel]:
        for model in models:
            if model.name.lower() == self._redfish_data.full_name.lower():
                model.reference.name = self._redfish_data.full_name
        return models

    def _update_url(self, models: typing.List[CustomDataModel]) -> typing.List[CustomDataModel]:
        for model in models:
            if model.name == self._redfish_data.full_name:
                model.fields.insert(
                    0,
                    DataModelField(
                        name='_url',
                        default=self._redfish_data.uri,
                        data_type=DataType(type='str')
                    )
                )
        return models

    def _update_classes(self,
                        models: typing.List[CustomDataModel],
                        category: DataModelCategory
                        ) -> typing.List[CustomDataModel]:
        result: typing.List[CustomDataModel] = []
        targets = [m for m in models if m.category == category]
        if len(targets) != 0:
            data_type = self._get_data_type(category)
            fields_to_remove = category_fields.get(category) + optional_fields.get(category)
            for model in models:
                if model in targets:
                    new_fields = []
                    for field in model.fields:
                        if field.name not in fields_to_remove:
                            new_fields.append(field)
                    model.fields = new_fields
                    model.base_classes = [data_type]
                    for i in data_type.imports:
                        model._additional_imports.append(i)
                result.append(model)
        else:
            result = models
        return result

    def _update_collection_methods(self,
                                   models: typing.List[CustomDataModel]
                                   ) -> typing.List[CustomDataModel]:
        result: typing.List[CustomDataModel] = []
        for model in models:
            if model.category == DataModelCategory.COLLECTION \
                    and model.name == self._redfish_data.full_name \
                    and self._child_data is not None:
                method = f"""
    @classmethod
    def resource(cls) -> Type[{self._child_data.full_name}]:
        return {self._child_data.full_name}
        """
                model.methods.append(method)
                model._additional_imports.append(
                    Import(
                        from_='typing',
                        import_='Type'
                    )
                )
            result.append(model)
        else:
            result = models
        return result

    def _clean_up_models(self,
                         models: typing.List[CustomDataModel],
                         category: DataModelCategory
                         ) -> typing.List[CustomDataModel]:
        result: typing.List[CustomDataModel] = []
        targets = [m for m in models if m.category == category]
        if len(targets) != 0:
            names = [target.name for target in targets]
            list_names = [f'List[{target.name}]' for target in targets]
            dict_names = [f'Dict[{target.name}]' for target in targets]
            opti_names = [f'Optional[{target.name}]' for target in targets]
            for model in models:
                if model not in targets:
                    for field in model.fields:
                        if field.type_hint in names:
                            field.data_type = self._get_data_type(category)
                        if field.type_hint in list_names:
                            field.data_type = self._get_data_type(category, collection='List')
                        if field.type_hint in dict_names:
                            field.data_type = self._get_data_type(category, collection='Dict')
                        if field.type_hint in opti_names:
                            field.data_type = self._get_data_type(category, is_optional=True)
                    result.append(model)
        else:
            result = models
        return result

    @property
    def results(self) -> Result:
        """
        Returns parsing result object
        """
        result: typing.List[str] = []
        imports = Imports()
        scoped_model_resolver = ModelResolver()

        models = self._get_cleaned_models()

        for model in models:
            imports.append(model.imports)
            for data_type in model.all_data_types:
                # To change from/import

                if not data_type.reference or data_type.reference.source in models:
                    # No need to import non-reference model.
                    # Or, Referenced model is in the same file. we don't need to import the model
                    continue

                if isinstance(data_type, BaseClassDataType):
                    from_ = ''.join(relative(model.module_name, data_type.full_name))
                    import_ = data_type.reference.short_name
                    full_path = from_, import_
                else:
                    from_, import_ = full_path = relative(model.module_name, data_type.full_name)

                alias = scoped_model_resolver.add(full_path, import_).name

                name = data_type.reference.short_name
                if from_ and import_ and alias != name:
                    data_type.alias = f'{alias}.{name}'

                imports.append(Import(from_=from_, import_=import_, alias=alias))

        imports.append(self._parser.imports)
        code = dump_templates(models)
        result += [code]

        body = '\n'.join(result)
        body = self._get_code_formatter().format_code(body)

        return Result(body=body, imports=imports, model_names=self.model_names)
