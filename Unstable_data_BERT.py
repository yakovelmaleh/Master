import json

import BERT_With_Cleaning.Classic_BERT_with_clean as Classic_BERT_with_clean
import BERT_With_Cleaning.run_fit_setfit_bert_clean_data as run_fit_setfit_bert_clean_data
import BERT_With_Cleaning.run_test_setfit_bert_clean_data as run_test_setfit_bert_clean_data
import BERT_Unbalance_Data.Classic_BERT_Unbalance as Classic_BERT_Unbalance
import BERT_Unbalance_Data.ALBERT as ALBERT

if __name__ == '__main__':

    print(f"start: Qt  Classic clean")
    try:
        Classic_BERT_with_clean.start('Qt', 'Master/')
    except Exception as e:
        print(f"*****************************ERROR*****************************")
        print(e)
    print(f"start: Qt SetFit clean")
    try:
        run_fit_setfit_bert_clean_data.start('Qt', 'Master/')
        run_test_setfit_bert_clean_data.start('Qt', 'Master/')
    except Exception as e:
        print(f"*****************************ERROR*****************************")
        print(e)
    print(f'finish Qt')

    print('Start BERT Unbalanced')
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START ALL')
    for jira_name, jira_obj in jira_data_sources.items():
        print(f"start: {jira_name} Classic")
        try:
            Classic_BERT_Unbalance.start(jira_name, 'Master/')
        except Exception as e:
            print(f"*****************************ERROR*****************************")
            print(e)
        print(f"start: {jira_name} ALBERT")
        try:
            ALBERT.start(jira_name, 'Master/')
        except Exception as e:
            print(f"*****************************ERROR*****************************")
            print(e)
        print(f'finish {jira_name}')
    print('FINISH ALL')