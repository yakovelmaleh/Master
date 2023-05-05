import json

import Data_Analysis.JQL_Queries as JQL
import time
import requests
from jira import JIRA

auth_jira = None
name_map = None


def verifyIssueType():
    pass


def connectJira():
    global auth_jira, name_map
    with open('../Source/jira_data_sources.json') as f:
        jira_data_sources = json.load(f)
    for jira_name, jira_obj in jira_data_sources.items():
        if jira_name == 'Sonatype':
            auth_jira = JIRA(jira_obj['jira_url'])
    jira_name = 'Sonatype'
    print('Connected to Jira' + jira_name) if auth_jira is not None else print('Did not connected to Jira')
    all_fields = auth_jira.fields()
    name_map = {field['name']: field['id'] for field in all_fields}
    mappingIssueType = {}
    nullCounter = 0
    for project_name in auth_jira.projects():
        size = 100
        initial = 0
        while True:
            start = initial * size
            try:
                issues = auth_jira.search_issues(f"project={project_name} AND {JQL.filter_by_resolution(jira_name)}"
                                                 f" AND {JQL.filter_by_status(jira_name)} AND {JQL.filter_by_noBugs()} "
                                                 f" AND {JQL.filter_by_resolutionDate()} AND"
                                                 f" {JQL.filter_by_NotEmptySprint()}", start, size, expand='changelog')
            except:
                issues = auth_jira.search_issues(f"project={project_name} AND {JQL.filter_by_resolution(jira_name)}"
                                                 f" AND {JQL.filter_by_status(jira_name)} AND {JQL.filter_by_noBugs()} "
                                                 f" AND {JQL.filter_by_resolutionDate()} AND"
                                                 f" {JQL.filter_by_NotEmptySprint()}", start, size)
            if len(issues) == 0:
                break
            initial += 1
            print(start)
            """
            *************** run over all issues****************
            for each issue, extract all the data fields from the net into the sql tables, some by using the fucntion in the start
            """
            for issue in issues:
                time.sleep(1)
                try:
                    issue_type = issue.fields.issuetype.name
                    if issue_type is None:
                        nullCounter += 1
                    elif mappingIssueType.__contains__(issue_type):
                        mappingIssueType[issue_type] += 1
                    else:
                        mappingIssueType[issue_type] = 1

                except:
                    print("failed " + issue)

    print(mappingIssueType)
    print("nulls: " + nullCounter)


if __name__ == '__main__':
    connectJira()