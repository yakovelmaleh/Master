import json

import BERT.run_fit_setfit_bert as run_setfit_bert
import BERT.run_test_setfit_bert as run_test_setfit_bert
import BERT.Classic_BERT as Classic_BERT
import Utils.CombineResults as CombineResults

if __name__ == '__main__':
    """
    run_setfit_bert.start('Apache', 'Master/')
    run_test_setfit_bert.start('Apache', 'Master/')
    Classic_BERT.start('Apache', 'Master/')
    """
    print('Start Classic BERT')
    #CombineResults.combineResultsBert('Apache', 'Master/')
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START ALL')
    for jira_name, jira_obj in jira_data_sources.items():
        print("start: ", jira_name)
        try:
            CombineResults.combineResultsBert('Apache', 'Master/')
            #Classic_BERT.start(jira_name, 'Master/')
        except Exception as e:
            print(e)

