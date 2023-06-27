import os


def run_NLP_Model(main_path, model_to_run, jira_name=None):
    if not os.path.exists(f'{main_path}/Results'):
        os.mkdir(f'{main_path}/Results')
        open(f'{main_path}/Results/file.txt', 'x')

    path_to_save = f'{main_path}/Results'

    if jira_name is not None:
        path = f'{main_path}/Results/{jira_name}'
        if not os.path.exists(path):
            os.mkdir(path)
            open(f'{path}/file.txt', 'x')
        path_to_save = f'{path_to_save}/{jira_name}'

    model_to_run(path_to_save)


