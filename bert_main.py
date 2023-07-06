import json
import NLP_Models_Current.More_Properties.Run_gtp as run_model

if __name__ == '__main__':
    """
    run_setfit_bert.start('Apache', 'Master/')
    run_test_setfit_bert.start('Apache', 'Master/')
    Classic_BERT.start('Apache', 'Master/')
    
    
    """
    print('Start Classic BERT')
    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START')
    for jira_name, jira_obj in jira_data_sources.items():
        print("start: ", jira_name)
        run_model.more_properties(jira_name)
    print('FINISH ALL')

