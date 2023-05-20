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
    d = {
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

    return pd.DataFrame([d.values()], columns=d.keys())


def combineResultsBert(jira_name, main_path):

    result_classic_5 = pd.read_csv(f'{main_path}BERT/Results/{jira_name}/Classic_result_5.csv')
    result_classic_10 = pd.read_csv(f'{main_path}BERT/Results/{jira_name}/Classic_result_10.csv')
    result_classic_15 = pd.read_csv(f'{main_path}BERT/Results/{jira_name}/Classic_result_15.csv')
    result_classic_20 = pd.read_csv(f'{main_path}BERT/Results/{jira_name}/Classic_result_20.csv')
    result_set_fit = pd.read_csv(f'{main_path}BERT/Results/{jira_name}/SetFit_result.csv')

    output = pd.DataFrame(columns=['k_unstable', 'Classic_BERT_PRC', 'SetFit_PRC', 'Classic_BERT_ROC', 'SetFit_ROC',
                                   'Classic_BERT_Acc', 'SetFit_Acc'])

    output = pd.concat([output, add_new_bert_raw(5, result_classic_5, result_set_fit, 0)], ignore_index=True)

    output = pd.concat([output, add_new_bert_raw(10, result_classic_10, result_set_fit, 1)], ignore_index=True)

    output = pd.concat([output, add_new_bert_raw(15, result_classic_15, result_set_fit, 2)], ignore_index=True)

    output = pd.concat([output, add_new_bert_raw(20, result_classic_20, result_set_fit, 3)], ignore_index=True)

    output.to_csv(f'{main_path}BERT/Results/{jira_name}/combineResultsBert.csv')


def add_new_bert_raw(k_unstable, classic_bert, set_fit, num):
    d = {
        'k_unstable': k_unstable,
        'Classic_BERT_PRC': classic_bert['area_under_pre_recall_curve'][4],
        'Classic_BERT_ROC': classic_bert['area_under_roc_curve'][4],
        'Classic_BERT_Acc': classic_bert['accuracy'][4],
        'SetFit_PRC': set_fit['area_under_pre_recall_curve'][num],
        'SetFit_ROC': set_fit['area_under_roc_curve'][num],
        'SetFit_Acc': set_fit['accuracy'][num],
    }
    return pd.DataFrame([d.values()], columns=d.keys())



