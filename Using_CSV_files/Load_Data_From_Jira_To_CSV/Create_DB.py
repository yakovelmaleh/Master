import os
import pandas as pd
import Using_CSV_files.Load_Data_From_Jira_To_CSV.TableColumns as TableColumns
import argparse
import Using_CSV_files.FilesActivity as FilesActivity


def create_DB(path, production=True):
    # Validate Path is valid

    if os.path.join("Using_CSV_files", "Data") not in path:
        raise Exception(f"path contains Using_CSV_files folder: {path}")

    if production and os.path.exists(path):
        print(f"DB creator: Path {path} already exist")

    if not os.path.exists(path):
        os.makedirs(path)

    for table in FilesActivity.filesNames.keys():
        save_table(table, path)


def save_table(class_type, path):
    df = pd.DataFrame(columns=TableColumns.get_properties(class_type))
    df.to_csv(os.path.join(path, FilesActivity.filesNames[class_type]), index=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--jiraName', help='Jira repo Name')
    parser.add_argument('--path', type=str, help='path')
    args = parser.parse_args()

    print(args.jiraName)
    print(args.path)
    """
    test_path = os.getcwd()
    path = "Using_CSV_files/Data/Using_CSV_files"
    create_DB(test_path, "test")
    """
