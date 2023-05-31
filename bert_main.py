import json

import Utils.CombineResults as CombineResults
import BERT.Classic_BERT_32 as Classic_BERT_32
import BERT.Classic_BERT_64 as Classic_BERT_64
import BERT_Balance_Data.Classic_BERT as Classic_BERT
import BERT_Balance_Data.SetFit as SetFit

if __name__ == '__main__':
    """
    run_setfit_bert.start('Apache', 'Master/')
    run_test_setfit_bert.start('Apache', 'Master/')
    Classic_BERT.start('Apache', 'Master/')
    """
    print('Start Classic BERT')
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START ALL')
    for jira_name, jira_obj in jira_data_sources.items():
        print("start: ", jira_name)
        SetFit.start(jira_name, 'Master/')
    print('FINISH ALL')
