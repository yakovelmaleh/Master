import json
import os

import pandas as pd
import RunModels.create_train_val_tes as create_train_val_tes
import Robert_Course.Week_Month_Year.previous_labels_and_dummies_and_WMY_model as Previous_model


def createFolders(jira_name):
    os.mkdir(f'Data/{jira_name}')

    os.mkdir(f'Models/chi_square/{jira_name}')
    open(f'Models/chi_square/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/coherence_values/{jira_name}')
    open(f'Models/coherence_values/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/feature_selection/{jira_name}')
    open(f'Models/feature_selection/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/final_doc2vec_models/{jira_name}')
    open(f'Models/final_doc2vec_models/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/lda_models/{jira_name}')
    open(f'Models/lda_models/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/optimization_results/{jira_name}')
    open(f'Models/optimization_results/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/results_best_para/{jira_name}')
    open(f'Models/results_best_para/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/topic_model/{jira_name}')
    open(f'Models/topic_model/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/train_test/{jira_name}')
    open(f'Models/train_test/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/train_test_after_all_but/{jira_name}')
    open(f'Models/train_test_after_all_but/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/train_test_after_chi/{jira_name}')
    open(f'Models/train_test_after_chi/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/train_val/{jira_name}')
    open(f'Models/train_val/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/train_val_after_all_but/{jira_name}')
    open(f'Models/train_val_after_all_but/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/train_val_after_chi/{jira_name}')
    open(f'Models/train_val_after_chi/{jira_name}/file.txt', 'x')

    os.mkdir(f'Models/word_vector/{jira_name}')
    open(f'Models/word_vector/{jira_name}/file.txt', 'x')

    os.mkdir(f'BERT/Results/{jira_name}')
    open(f'BERT/Results/{jira_name}/file.txt', 'x')

    os.mkdir(f'BERT_With_Cleaning/Results/{jira_name}')
    open(f'BERT_With_Cleaning/Results/{jira_name}/file.txt', 'x')

    os.mkdir(f'Instability_With_BERT/Results/{jira_name}')
    open(f'Instability_With_BERT/Results/{jira_name}/file.txt', 'x')

    os.mkdir(f'Instability_With_BERT/Data/{jira_name}')
    open(f'Instability_With_BERT/Data/{jira_name}/file.txt', 'x')

    os.mkdir(f'Normal_instability/Results/{jira_name}')
    open(f'Normal_instability/Results/{jira_name}/file.txt', 'x')

    os.mkdir(f'Instability_With_BERT/Parameters/{jira_name}')
    open(f'Instability_With_BERT/Parameters/{jira_name}/file.txt', 'x')

    os.mkdir(f'BERT_Balance_Data/Results/{jira_name}')
    open(f'BERT_Balance_Data/Results/{jira_name}/file.txt', 'x')

    os.mkdir(f'Normal_instability/Parameters/{jira_name}')
    open(f'Normal_instability/Parameters/{jira_name}/file.txt', 'x')

    os.mkdir(f'Instability_sample_weight/Results/{jira_name}')
    open(f'Instability_sample_weight/Results/{jira_name}/file.txt', 'x')

    os.mkdir(f'Instability_sample_weight/Parameters/{jira_name}')
    open(f'Instability_sample_weight/Parameters/{jira_name}/file.txt', 'x')

    os.mkdir(f'Data_60_20/Results/{jira_name}')
    open(f'Data_60_20/Results/{jira_name}/file.txt', 'x')

    os.mkdir(f'NLP_Models/Results/{jira_name}')
    open(f'NLP_Models/Results/{jira_name}/file.txt', 'x')

    os.mkdir(f'KNN/Results/{jira_name}')
    open(f'KNN/Results/{jira_name}/file.txt', 'x')

    os.mkdir(f'Balancing_Data/Results/{jira_name}')
    open(f'Balancing_Data/Results/{jira_name}/file.txt', 'x')

def createBalanceFile():
    result = pd.DataFrame(columns=['k_unstable', 'Half', '1', '2', '3', '4'])
    for k_unstable in [5, 10, 15, 20]:
        d = {f"k_unstable": k_unstable}
        for num in ['Half', 1, 2, 3, 4]:
            with open('Master/Source/jira_data_for_instability_cluster.json') as f:
                jira_data_sources = json.load(f)

            total = 0
            sum = 0
            for jira_name, jira_obj in jira_data_sources.items():
                try:
                    results = pd.read_csv(f'Master/BERT_Balance_Data/Results/{jira_name}/Classic_result_{k_unstable}_ratio_{num}.csv')
                    print(f'{jira_name} here')
                    print(results['size'][0])
                    size = int(results['size'][0])
                    total += size
                    print(results['area_under_pre_recall_curve'][0])
                    sum = sum + (size * float(results['area_under_pre_recall_curve'][0]))
                except:
                    print(jira_name)
                    print(f'Master/BERT_Balance_Data/Results/{jira_name}/Classic_result_5_ratio_{num}.csv')

            d[f'{num}'] = sum / float(total)
        result = pd.concat([result, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)
    result.to_csv('BERT_Balance_Results.csv')


def createBERTsize():
    result = pd.DataFrame(columns=['k_unstable', '32', '64', '128', '256', '512'])
    for k_unstable in [5, 10, 15, 20]:
        d = {f"k_unstable": k_unstable}
        for num in [32, 64, 128, 256, 512]:
            with open('Master/Source/jira_data_for_instability_cluster.json') as f:
                jira_data_sources = json.load(f)

            total = 0
            sum = 0
            for jira_name, jira_obj in jira_data_sources.items():
                if num == 128:
                    results = pd.read_csv(f'Master/BERT/Results/{jira_name}/Classic_result_{k_unstable}.csv')
                else:
                    results = pd.read_csv(f'Master/BERT/Results/{jira_name}/Classic_{num}_result_{k_unstable}.csv')

                size = len(pd.read_csv(f'Master/Data/{jira_name}/features_labels_table_os.csv'))
                total += size
                print(results['area_under_pre_recall_curve'][0])
                sum = sum + (size * float(results['area_under_pre_recall_curve'][0]))

            d[f'{num}'] = sum / float(total)
        result = pd.concat([result, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)
    result.to_csv('BERT_Size_Results.csv')

def create_feature_csv(jira_name):
    """
    dbName = f"{DB.DB_NAME}_{jira_name.lower()}"
    mysql_con = DB.connectToSpecificDB(dbName)

    #delete Attachment
    comments_data = pd.read_sql(f'SELECT * FROM {dbName}.features_labels_table_os', con=mysql_con)
    comments_data.to_csv(f'Data/{jira_name}/features_labels_table_os.csv')
    """


if __name__ == '__main__':

    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START ALL')
    for jira_name, jira_obj in jira_data_sources.items():
        print("start: ", jira_name)
        Previous_model.run('Master/', jira_name)
