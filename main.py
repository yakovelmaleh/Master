import time

from jira import JIRA
# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
import requests
import json
import io



def print_hi(name):
    # Use a breakpoint in the code line below to debug your script.
    print(f'Hi, {name}')  # Press Ctrl+F8 to toggle the breakpoint.
    url = "https://jira.mariadb.org/rest/api/3/search"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    query = {
        'jql': 'project = TTS'
    }

    response = requests.get(url, headers=headers, params=query, auth=("", ""))
    data = response.json()
    issues = data["issues"]
    for issue in issues:
        print(issue["key"])


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    #print_hi('PyCharm')
    auth_jira = JIRA('https://jira.sakaiproject.org')
    #auth_jira.attachment()
    #(auth_jira.projects())
    all_fields = auth_jira.fields()
    name_map = {field['name']: field['id'] for field in all_fields}
    print(name_map)
    issues = auth_jira.search_issues("project=Sakai", 0, 100, expand='changelog')
    for issue in issues:
        time.sleep(1)
        #print(issue.fields)
        num_worklog = len(auth_jira.worklogs(issue))
        project_key = issue.fields.project.key
        status_name = issue.fields.status.name
        comments = auth_jira.comments(issue.id)
        #print(len(comments))
        if getattr(issue.fields, name_map['Epic Link']) is not None:
            print(getattr(issue.fields, name_map['Epic Link']))

