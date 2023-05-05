import csv

from jira import JIRA
import json
import JQL_Queries as JQL

header = ['Name', 'Number of Issues (Article) - Total', 'Number of Issues (Actual) - Total', 'Delta',
          'No Bugs - Amount', 'No Bugs - %',
          'Resolution - Amount', 'Resolution - %',
          'Status - Amount', 'Status - %',
          'ResolutionDate - Amount', 'ResolutionDate - %',
          'Contains Sprints - Amount', 'Contains Sprints - %',
          'optional PR - Amount', 'optional PR - %',
          'full Query (without PR) - Amount', 'full Query (without PR) - %',
          'full Query without Sprints (without PR) - Amount', 'full Query without Sprints (without PR) - %',
          'full Query (with PR) - Amount', 'full Query (with PR) - %',
          'full Query without Sprints (with PR) - Amount', 'full Query without Sprints (with PR) - %',
          ]


def getData(project_name, jira_obj):
    output = [project_name, int(jira_obj['rough_issue_count'].replace(',',''))]
    auth_jira = JIRA(jira_obj['jira_url'])

    if project_name == 'MariaDB':
        total = get_all_issues(auth_jira, "project in (MCOL, CONC, CONCPP, CONJ, CONJS, ODBC, CONPY, R2DBC, MDBF, "
                                          "MXS, MDEV, TOOLS)")
    else:
        total = get_all_issues(auth_jira, "")
    output.append(total)
    output.append(total - int(jira_obj['rough_issue_count'].replace(',','')))

    output.extend(get_notBugs(total, auth_jira))
    output.extend(get_resolution(total, project_name, auth_jira))
    output.extend(get_status(total, project_name, auth_jira))
    output.extend(get_withResolutionDate(total, auth_jira))
    output.extend(get_withSprints(total, auth_jira))
    output.extend(get_PR(total, project_name, auth_jira))
    output.extend(get_fullQuery(total, project_name, auth_jira))
    output.extend(get_fullQuery_WithoutSprints(total, project_name, auth_jira))
    output.extend(get_fullQuery_withPR(total, project_name, auth_jira))
    output.extend(get_fullQuery_WithoutSprints_withPR(total, project_name, auth_jira))

    return output


def get_fullQuery_WithoutSprints_withPR(total, project_name, auth_jira):
    query = f"{JQL.filter_by_resolution(project_name)} AND {JQL.filter_by_status(project_name)}" \
            f" AND {JQL.filter_by_noBugs()} AND {JQL.filter_by_resolutionDate()}" \
            f" AND {JQL.filter_byOptionalPR(project_name)}"
    results = get_all_issues(auth_jira, query)
    return [results, float(100 * results) / total]


def get_fullQuery_withPR(total, project_name, auth_jira):
    query = f"{JQL.filter_by_resolution(project_name)} AND {JQL.filter_by_status(project_name)}" \
            f" AND {JQL.filter_by_noBugs()} AND {JQL.filter_by_resolutionDate()} AND {JQL.filter_by_NotEmptySprint()}" \
            f" AND {JQL.filter_byOptionalPR(project_name)}"
    results = get_all_issues(auth_jira, query)
    return [results, float(100 * results) / total]


def get_fullQuery_WithoutSprints(total, project_name, auth_jira):
    query = f"{JQL.filter_by_resolution(project_name)} AND {JQL.filter_by_status(project_name)}" \
            f" AND {JQL.filter_by_noBugs()} AND {JQL.filter_by_resolutionDate()}"
    results = get_all_issues(auth_jira, query)
    return [results, float(100 * results) / total]


def get_fullQuery(total, project_name, auth_jira):
    query = f"{JQL.filter_by_resolution(project_name)} AND {JQL.filter_by_status(project_name)}" \
            f" AND {JQL.filter_by_noBugs()} AND {JQL.filter_by_resolutionDate()} AND {JQL.filter_by_NotEmptySprint()}"
    results = get_all_issues(auth_jira, query)
    return [results, float(100 * results) / total]


def get_PR(total, project_name, auth_jira):
    PRs = get_all_issues(auth_jira, JQL.filter_byOptionalPR(project_name))
    return [PRs, float(100 * PRs) / total]


def get_withResolutionDate(total, auth_jira):
    resolutionDates = get_all_issues(auth_jira, JQL.filter_by_resolutionDate())
    return [resolutionDates, float(100 * resolutionDates) / total]


def get_withSprints(total, auth_jira):
    sprints = get_all_issues(auth_jira, JQL.filter_by_NotEmptySprint())
    return [sprints, float(100 * sprints) / total]


def get_status(total, project_name, auth_jira):
    resolution = get_all_issues(auth_jira, JQL.filter_by_status(project_name))
    return [resolution, float(100 * resolution) / total]


def get_notBugs(total, auth_jira):
    not_bugs = get_all_issues(auth_jira, JQL.filter_by_noBugs())
    return [not_bugs, float(100 * not_bugs) / total]


def get_resolution(total, project_name, auth_jira):
    resolution = get_all_issues(auth_jira, JQL.filter_by_resolution(project_name))
    return [resolution, float(100 * resolution) / total]


def get_all_issues(jira_client, query):
    chunk = jira_client.search_issues(query).total
    return chunk


def calculateTotal(all_lines):
    totals = ["Total"]
    for i in range(1, 4):
        count = 0
        for line in all_lines:
            count += line[i]
        totals.append(count)

    for index in range(4, len(header)):
        if index % 2 == 0:
            count = 0
            for line in all_lines:
                count += line[index]
            totals.append(count)
        else:
            totals.append(float(100*totals[index-1]) / totals[1])
    all_lines.append(totals)
    return all_lines


if __name__ == '__main__':

    with open('../Source/jira_data_sources.json') as f:
        jira_data_sources = json.load(f)
    data = []
    for jira_name, jira_obj in jira_data_sources.items():
        print(f"{jira_name} start")
        data.append(getData(jira_name, jira_obj))
        print(f"{jira_name} finish")
    data = calculateTotal(data)

    with open('Result.csv', 'w', encoding='UTF8', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(data)
