import json
import Balance_only_Train.Classic_BERT as Classic_BERT

if __name__ == '__main__':
    """
    run_setfit_bert.start('Apache', 'Master/')
    run_test_setfit_bert.start('Apache', 'Master/')
    Classic_BERT.start('Apache', 'Master/')
    
    """
    print('Start Classic BERT')
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START ALL Classic_BERT')
    for jira_name, jira_obj in jira_data_sources.items():
        print("start: ", jira_name)
        Classic_BERT.start(jira_name, 'Master/')
    print('FINISH ALL')

