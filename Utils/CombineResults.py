import pandas as pd


def combineResults(jira_name, main_path):
    result_5 = pd.read_csv(f'{main_path}/results_groups_{jira_name}_is_change_text_num_words_5.csv')
    result_10 = pd.read_csv(f'{main_path}/results_groups_{jira_name}_is_change_text_num_words_10.csv')
    result_15 = pd.read_csv(f'{main_path}/results_groups_{jira_name}_is_change_text_num_words_15.csv')
    result_20 = pd.read_csv(f'{main_path}/results_groups_{jira_name}_is_change_text_num_words_20.csv')

    algorithms = ['Rnd', 'RF', 'NN', 'XG']
    columns = ['k_unstable']
    AUC_PRC = [f'AUC_PRC_{x}' for x in algorithms]
    AUC_ROC = [f'AUC_ROC_{x}' for x in algorithms]
    Acc = [f'Acc_{x}' for x in algorithms]
    columns.extend(AUC_PRC)
    columns.extend(AUC_ROC)
    columns.extend(Acc)
    output = pd.DataFrame(columns=columns)
    output = pd.concat([output, new_raw(result_5, 5), new_raw(result_10, 10), new_raw(result_15, 15),
                        new_raw(result_20, 20)], ignore_index=True)
    output.to_csv(f'{main_path}/combineResults.csv')

def new_raw(data, k_unstable):
    return {
        'k_unstable': k_unstable,
        'AUC_PRC_Rnd': data['area_under_pre_recall_curve'][5],
        'AUC_PRC_RF': data['area_under_pre_recall_curve'][0],
        'AUC_PRC_NN': data['area_under_pre_recall_curve'][2],
        'AUC_PRC_XG': data['area_under_pre_recall_curve'][1],
        'AUC_ROC_Rnd': data['area_under_roc_curve'][5],
        'AUC_ROC_RF': data['area_under_roc_curve'][0],
        'AUC_ROC_NN': data['area_under_roc_curve'][2],
        'AUC_ROC_XG': data['area_under_roc_curve'][1],
        'Acc_Rnd': data['accuracy'][5],
        'Acc_RF': data['accuracy'][0],
        'Acc_NN': data['accuracy'][2],
        'Acc_XG': data['accuracy'][1],
    }






