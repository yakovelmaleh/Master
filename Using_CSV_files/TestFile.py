import FilesActivity
import Using_CSV_files.Load_Data_From_Jira_To_CSV.TableColumns as TableColumns
import typing
from datetime import datetime
from typing import get_origin, get_args, Union
import inspect
import json
import fastavro

"""
def convert_value_by_table(classType, property, value):
    date_format = "%Y-%m-%d %H:%M:%S"
    propertyType = classType.__init__.__annotations__.get(property, None)
    defaultType = inspect.signature(classType.__init__).parameters[property].default

    if value is None and defaultType is None:
        return None

    if get_origin(propertyType) is Union:
        if get_args(propertyType)[0] is datetime:
            return datetime.strptime(value, date_format)

        return get_args(propertyType)[0](value)

    elif value is None:
        raise Exception(f" {classType} class has {property} which should be from  {defaultType} type!!!")

    else:
        return propertyType(value)


if __name__ == '__main__':
    ##a = convert_value_by_table(TableColumns.AllChangesOS, "created", None)
    #print(a)

    # Path to your Avro file
    avro_file_path = 'C:\\Users\\t-yelmaleh\\Downloads\\28.avro'

    # Open the Avro file and read the schema
    # Open the Avro file and read the records
    with open(avro_file_path, 'rb') as f:
        reader = fastavro.reader(f)

        # Print the schema
        schema = reader.schema
        print("Schema:", json.dumps(schema, indent=2))

        # Iterate over records and print each one in a readable format
        for record in reader:
            print(json.dumps(record, indent=1))
"""

    """
    path = 'C:\\Users\\t-yelmaleh\\OneDrive - Microsoft\\Desktop\\Yakov\\Master\\Master\\Using_CSV_files'
    path_to_load = f"{path}\\test"
    path_to_save = f'{path}\\Data\\Simple_Data'
    FilesActivity.copy_files_with_black_list(path_to_load, path_to_save, [TableColumns.MainTableOS])
    """
