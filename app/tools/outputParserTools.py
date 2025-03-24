from pydantic import BaseModel, Field
from typing import Type, Dict, Any, List, get_origin, get_args
from sqlalchemy.orm import Session
from extensions import db
from model.output_parser import OutputParser
import logging
from datetime import date


def process_type(field_type):
    """
    Procesa un tipo de dato para manejar correctamente las listas y modelos Pydantic.
    
    :param field_type: El tipo de dato a procesar
    :return: El tipo procesado
    """
    # Si es una lista, procesamos su contenido
    if get_origin(field_type) is list:
        inner_type = get_args(field_type)[0]
        # Verificamos si el tipo interno hereda de BaseModel
        if isinstance(inner_type, type) and issubclass(inner_type, BaseModel):
            return List[inner_type]
        return List[inner_type]
    
    # Si es un modelo Pydantic (hereda de BaseModel)
    if isinstance(field_type, type) and issubclass(field_type, BaseModel):
        return field_type
        
    return field_type

def build_fields_dict(field_names: list[str], field_types: list[type], field_descriptions: list[str]) -> Dict[str, tuple[type, str]]:
    """
    Construye un diccionario de campos a partir de listas paralelas.
    
    :param field_names: Lista con los nombres de los campos
    :param field_types: Lista con los tipos de datos de los campos
    :param field_descriptions: Lista con las descripciones de los campos
    :return: Diccionario con la estructura requerida para crear el modelo
    """
    if not (len(field_names) == len(field_types) == len(field_descriptions)):
        raise ValueError("Todas las listas deben tener la misma longitud")
    
    fields_dict = {
        field_name: (process_type(field_type), field_desc)
        for field_name, field_type, field_desc in zip(field_names, field_types, field_descriptions)
    }
    print("fields_dict", fields_dict)
    return fields_dict

def create_dynamic_pydantic_model(model_name: str,
    field_names: list[str],
    field_types: list[type],
    field_descriptions: list[str]
) -> Type[BaseModel]:
    """
    Crea un modelo Pydantic dinámicamente.
    
    :param model_name: Nombre de la clase del modelo
    :param field_names: Lista con los nombres de los campos
    :param field_types: Lista con los tipos de datos de los campos
    :param field_descriptions: Lista con las descripciones de los campos
    :return: Una nueva clase que hereda de BaseModel con los campos especificados
    """
    fields = build_fields_dict(field_names, field_types, field_descriptions)
    model_fields = {
        field_name: (field_type, Field(description=field_desc))
        for field_name, (field_type, field_desc) in fields.items()
    }
    print("model_fields", model_fields)
    return type(model_name, (BaseModel,), {
        "__annotations__": {field_key: field_val[0] for field_key, field_val in model_fields.items()},
        **{field_key: field_val[1] for field_key, field_val in model_fields.items()}
    })

def get_type_from_string(type_str: str, list_item_type: str = None, list_item_parser_id: int = None, parser_id: int = None):
    """
    Convierte una cadena de tipo en su equivalente Python/Pydantic.
    
    :param type_str: String que representa el tipo ('str', 'int', 'list', etc.)
    :param list_item_type: Tipo de los elementos de la lista si type_str es 'list'
    :param list_item_parser_id: ID del parser si list_item_type es 'parser'
    :param parser_id: ID del parser si type_str es 'parser'
    :return: El tipo Python correspondiente
    """
    basic_types = {
        'str': str,
        'int': int,
        'float': float,
        'bool': bool,
        'date': date
    }
    
    if type_str == 'parser':
        if parser_id is None:
            raise ValueError("Se requiere parser_id para campos de tipo parser")
        return get_parser_model_by_id(parser_id)
    elif type_str == 'list':
        if list_item_type == 'parser':
            if list_item_parser_id is None:
                raise ValueError("Se requiere list_item_parser_id para listas de tipo parser")
            parser_model = get_parser_model_by_id(list_item_parser_id)
            return List[parser_model]
        return List[basic_types.get(list_item_type, str)]
    
    return basic_types.get(type_str, str)

def create_model_from_json_schema(schema_data: List[Dict[str, Any]], model_name: str) -> Type[BaseModel]:
    """
    Crea un modelo Pydantic a partir de un esquema JSON.
    """
    logging.info(f"Creando modelo '{model_name}' a partir del schema")
    
    field_names = []
    field_types = []
    field_descriptions = []
    
    for field in schema_data:
        field_names.append(field['name'])
        
        try:
            # Si el campo es de tipo parser o ya es una clase, usarlo directamente
            if isinstance(field['type'], type):
                tipo = field['type']
            # Si es una lista y list_item_type es una clase, usarla directamente
            elif field['type'] == 'list' and isinstance(field.get('list_item_type'), type):
                tipo = List[field['list_item_type']]
            else:
                tipo = get_type_from_string(
                    field['type'],
                    field.get('list_item_type'),
                    field.get('list_item_parser_id'),
                    int(field.get('parser_id')) if field.get('parser_id') else None
                )
            field_types.append(tipo)
            field_descriptions.append(field['description'])
            logging.info(f"Campo procesado: nombre='{field['name']}', tipo='{tipo}', descripción='{field['description']}'")
        except Exception as e:
            logging.error(f"Error procesando campo {field['name']}: {str(e)}")
            raise
    
    modelo = create_dynamic_pydantic_model(
        model_name,
        field_names,
        field_types,
        field_descriptions
    )
    logging.info(f"Modelo Pydantic creado: {model_name}")
    
    return modelo

def get_parser_model_by_id(parser_id: int, processed_parsers: set = None) -> Type[BaseModel]:
    """
    Obtiene y construye el modelo Pydantic correspondiente a un ID de parser.
    """
    logging.info(f"Iniciando construcción del modelo Pydantic para parser_id: {parser_id}")
    
    if processed_parsers is None:
        processed_parsers = set()
    
    if parser_id in processed_parsers:
        logging.error(f"Dependencia circular detectada para el parser {parser_id}")
        raise ValueError(f"Dependencia circular detectada para el parser {parser_id}")
    
    processed_parsers.add(parser_id)
    logging.info(f"Parsers procesados hasta ahora: {processed_parsers}")
    
    parser = db.session.query(OutputParser).filter(OutputParser.parser_id == parser_id).first()
    if not parser:
        raise ValueError(f"No se encontró el parser con ID {parser_id}")
    
    schema_data = parser.fields
    logging.info(f"Schema obtenido de la base de datos: {schema_data}")
    
    for field in schema_data:
        if field['type'] == 'parser':
            logging.info(f"Procesando campo tipo parser: {field['name']}")
            referenced_model = get_parser_model_by_id(int(field['parser_id']), processed_parsers)
            field['type'] = referenced_model
        elif field['type'] == 'list' and field.get('list_item_type') == 'parser':
            logging.info(f"Procesando campo tipo lista de parser: {field['name']}")
            referenced_model = get_parser_model_by_id(int(field['list_item_parser_id']), processed_parsers)
            field['type'] = 'list'
            field['list_item_type'] = referenced_model
    
    return create_model_from_json_schema(schema_data, parser.name)