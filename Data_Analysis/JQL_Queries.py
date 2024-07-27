

def filter_by_resolution(project_name):
    return f'resolution in {resolution[project_name]}'


def filter_by_status(project_name):
    return f'status in {status[project_name]}'


def filter_by_noBugs():
    return 'type != Bug'


def filter_by_resolutionDate():
    return 'resolutiondate is not EMPTY'


def filter_by_NotEmptySprint():
    return 'Sprint is not EMPTY'


def filter_byOptionalPR(project_name):
    return changes[project_name]


resolution = {
    'Apache': '("Auto Closed",Delivered,Done,Duplicate,Fixed,"Feedback Received",Implemented,"Pending Closed",'
              ' Resolved)',
    'Hyperledger': '(Done)',
    'IntelDAOS': '(Done,Fixed,Fixed-Verified)',
    'JFrog': '(Done)',
    'Jira': '(Done,Fixed)',
    'JiraEcosystem': '(Answered,"Answered - commit","Answered - not commit",'
                     'Approved,"Answered - unsure","Accepted - First Choice","Accepted - Second Choice")',
    'MariaDB': '(Done,Fixed)',
    'Mojang': '(Done,Fixed)',
    'MongoDB': '(Done,Fixed)',
    'Qt': '(Done,Fixed)',
    'RedHat': '(Done,Fixed,Done-Errata)',
    'Sakai': '(Done,Fixed)',
    'SecondLife': '(Done,Fixed)',
    'Sonatype': '(Done,Fixed)',
    'Spring': '(Complete,Done,Fixed)',
}

status = {
    'Apache': '(Accepted,"Auto Closed","Changes Suggested",Closed,Completed,Continued,Done,FixedInBranch,'
              ' Fixed,"Fix Released/Published",Passed,"Pull Request Available","Pull Request Merged",Ported,'
              '"Patch Reviewed",Resolved,"Ready to Commit",Verified, Duplicate)',
    'Hyperledger': '(Closed,Done,Complete, Resolved,Complete)',
    'IntelDAOS': '(Approved,"Awaiting approval","Awaiting Verification"'
                 ',Closed,Completed,Closed, Implemented, Resolved,Completed)',
    'JFrog': '(Closed,Done,"Pending QA",Resolved, RESOLVED, Closed, Resolved)',
    'Jira': ' (Done, Completed, Closed, RESOLVED, "Resolved - pending deploy", Committed, Completed)',
    'JiraEcosystem': '(Accepted,"Awaiting Merge","Awaiting Release",Completed, Done, "Done/Resolved", Resolved, '
                     'Closed, "Commit")',
    'MariaDB': '(Done, Closed, Approved, Fixed)',
    'Mojang': '(Done,Closed,Resolved)',
    'MongoDB': '(Approved,Accepted,"Accepted for Development","Acceptance Testing", Done, "Done, Pending Release", '
               '"Done, Released to Production", Resolved, "Fix Issued",Closed, Completed)',
    'Qt': '(Done, Resolved, Closed, Implemented)',
    'RedHat': '(Done, Committed, Completed, Closed, Resolved)',
    'Sakai': '(Done, Resolved, Closed, Approved, "Completed for review")',
    'SecondLife': '(Done, Resolved, Closed)',
    'Sonatype': '(Done, Resolved, Closed,Approved,Closed)',
    'Spring': '(Done, Closed, Resolved)',
}


changes = {
    'Apache': '(labels in (pull-request-available,pull-requests-available,pull_request_available) '
              'OR comment ~ "https://github.com")',
    'Hyperledger': 'comment ~ "https://github.com"',
    'IntelDAOS': 'comment ~ "https://github.com"',
    'JFrog': 'comment ~ "https://github.com" ',
    'Jira': ' comment ~ "https://github.com"',
    'JiraEcosystem': 'comment ~ "https://github.com"',
    'MariaDB': 'comment ~ "https://github.com"',
    'Mojang': 'comment ~ "https://github.com"',
    'MongoDB': 'comment ~ "https://github.com"',
    'Qt': 'comment ~ "https://github.com"',
    'RedHat': 'comment ~ "https://github.com"',
    'Sakai': 'comment ~ "https://github.com"',
    'SecondLife': 'comment ~ "https://github.com"',
    'Sonatype': 'comment ~ "https://github.com"',
    'Spring': 'comment ~ "https://github.com"',
}