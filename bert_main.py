import json
import Cross_Projects.Classic_BERT_without_valid as Classic_BERT_without_valid

if __name__ == '__main__':
    """
    run_setfit_bert.start('Apache', 'Master/')
    run_test_setfit_bert.start('Apache', 'Master/')
    Classic_BERT.start('Apache', 'Master/')
    
    
    print('Start Classic BERT')
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START ALL SetFit')
    for jira_name, jira_obj in jira_data_sources.items():
        print("start: ", jira_name)
        SetFit.start(jira_name, 'Master/')
    print('FINISH ALL')
    """
    Classic_BERT_without_valid.start()

