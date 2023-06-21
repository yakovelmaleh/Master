import json
import Only_Instability_Cross_Project.run_cross_project as run_cross_project
if __name__ == '__main__':
    print('Start BERT')

    with open('Master/Source/jira_data_for_instability_cluster.json') as f:
        jira_data_sources = json.load(f)

    print('START ALL')
    for jira_name, jira_obj in jira_data_sources.items():
        print(f"start: {jira_name} KNN_Model_with_dropping")
        run_cross_project.run_train_only_one_project(jira_name, 'Master/')
        print(f'finish {jira_name}')
    print('FINISH ALL KNN_Model_with_dropping')
    """
    run_cross_project.run_all(
        lambda test, valid, main_path:
        run_cross_project.run_whole_project_as_a_test(test_jira_name=test,
                                                      validation_jira_name=valid,
                                                      main_path=main_path), "Master/")


    """


