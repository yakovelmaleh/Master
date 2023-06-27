import Utils.NLP_Models.run_Model as run_Model
import Utils.NLP_Models.RoBERTa as RoBERTa
import Utils.GetNLPData as GetData
from sklearn.utils import resample
import pandas as pd
import os


def run_over_sampling(jira_name, main_path='Master/'):
    model_name = 'Over_Sampling'
    main_path = f'{main_path}NLP_Models_Current/{model_name}'
    if not os.path.exists(main_path):
        os.mkdir(f'{main_path}')
        open(f'{main_path}/file.txt', 'x')

    data_train_list = get_train_data_list(jira_name)
    data_test_list = get_test_data_list(jira_name)
    model_to_run = lambda path_to_save: RoBERTa.start(jira_name=jira_name, model_name=model_name,
                                                      train_data_list=data_train_list, test_data_list=data_test_list,
                                                      path_to_save=path_to_save)

    run_Model.run_NLP_Model(main_path=main_path, jira_name=jira_name, model_to_run=model_to_run)


def get_test_data_list(project_name, main_path='Master/'):
    output = dict()
    for k_unstable in [5, 10, 15, 20]:
        output[f'{k_unstable}'] = \
            GetData.get_test_data(project_name, main_path, k_unstable)

    return output


def over_sample(data):
    minority_class = data[data['label'] == 1]
    majority_class = data[data['label'] == 0]
    oversampled_minority = resample(minority_class, replace=True, n_samples=len(majority_class), random_state=42)
    oversampled_train_data = pd.concat([majority_class, oversampled_minority])
    oversampled_train_data = oversampled_train_data.sample(frac=1, random_state=42)

    return oversampled_train_data


def get_train_data_list(project_name, main_path='Master/'):
    output = dict()
    for k_unstable in [5, 10, 15, 20]:
        temp = GetData.get_data_train(project_name, main_path, k_unstable)
        output[f'{k_unstable}'] = over_sample(temp)

    return output
