
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
    'IntelDAOS': '(Done,Fixed,Fixed-Verified, "Won\'t Do", "Won\'t Fix", Declined, Duplicate, "Cannot Reproduce")',
    'JFrog': '(Done)',
    'Jira': '("Won\'t Fix","Won\'t Do","Resolved Locally",Answered,Deployed,Done,Duplicate,Fixed,"Handled by Support",'
            '"Cannot Reproduce")',
    'JiraEcosystem': '("Won\'t Do","Won\'t Fix",wontfix,Resolved,"Resolved Locally","Timed out",Answered, '
                     '"Answered - commit","Answered - not commit",Approved,Declined,Done,Duplicate,Fixed,closed)',
    'MariaDB': '("Won\'t Fix","Won\'t Do",Done,Duplicate,Fixed,"Cannot Reproduce")',
    'Mojang': '("Won\'t Do","Won\'t Fix","Awaiting Response",Done,Duplicate,Fixed,"Cannot Reproduce")',
    'MongoDB': '("Won\'t Do","Won\'t Fix",Done,Duplicate,Declined,Fixed,"Gone away","Cannot Reproduce", '
               '"Community Answered")',
    'Qt': '("Won\'t Do",Done,Duplicate,Fixed,"Cannot Reproduce")',
    'RedHat': '("Won\'t Do","Test Pending",Done,Done-Errata,Duplicate,"Cannot Reproduce","Can\'t Do")',
    'Sakai': '("Won\'t Do","Won\'t Fix",Done,Duplicate,Fixed,"Cannot Reproduce")',
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
    'Jira': ' (Accepted,"Awaiting Development","Awaiting Merge","Awaiting Quality Review","Awaiting Release",'
            '"Awaiting Review",Cancelled,Closed,Committed,Completed,Deployed,Deploy,"Deployed to Cloud",Done,Duplicate,'
            '"Ernie Approved",Implemented,"In Development","In PR","In Repository","In Review",Merged,'
            '"Mitigated / Resolved","Mitigation In Progress","More Work Required","Pull Requested",Published,'
            '"Quality Review","Ready for Development","Ready for Release","Ready for Review",'
            '"Ready for Review by Dev Team","Ready for Review by Ernie","Ready for Review by Jon",'
            '"Ready for Review by Sales","Ready for Web Release","Ready to Commit","Released to Cloud",'
            '"Released to Server","Selected for Development",Verified,"Verified by Dev","Waiting for Release",'
            '"Waiting for Atlassian",WontFix)',
    'JiraEcosystem': '("Waiting for Dev Spt","Waiting for Release",Ready,"Ready for development","Ready for Review",'
                     'Resolved,"Under Review","Under Quality Review","Under peer review","Under Additional Review",'
                     '"In Development","In Review",Approved,Aligned,"Awaiting Deployment","Awaiting release",'
                     '"Awaiting Resubmission","Awaiting triage",Staged,Done,"Done / Mitigated / Accepted",Closed,'
                     'Completed,Verified,"Needs Verification","Mitigation / Monitoring")',
    'MariaDB': ' ("Won\'t Fix","Release done",Approved,"Selected for Development",Done,'
               'Duplicate, Fixed,CANCELED,Cancelled,Closed,Confirmed,Verified)',
    'Mojang': ' ("QA Review","Waiting for approval",Escalated,Resolved,"Awaiting Response",Done,Closed)',
    'MongoDB': ' ("QA approved","Waiting for Approval","Waiting for Approver","Waiting For Deployment",'
               '"Waiting for Development",Ready,"Ready for Approval","Ready for Deployment","Ready for Development",'
               '"Ready for Production","Ready for QA","Ready for Publish / Social","Test / Approval","Testing/QA",'
               '"Testing/Approval","Under Review","In Development","Pending Approval","Pending Approval 1",'
               '"Pending Approval 2","Pending Approval 3",Accepted,"Additional Approval Required","Sandbox Approved",'
               'Deployed,Done,"Done, Pending Release","Done, Released to Production", "Fix Issued","Fix Validated",'
               '"Fix Needed","Fix Validated","Fix Validation Request",Closed,Validated,Verifying,'
               '"Verify Production Env will Match Sandbox Env","Needs Approval","Needs Development","Needs Merge",'
               '"Needs PD Approval","Manager Approval",Merged,"Manager Approval/Speaker Approval") ',
    'Qt': '  (Resolved,"Ready for Development",Testing,"In Development",Implemented,Published,Done,Closed,'
          'Verified,"Needs Review")',
    'RedHat': ' (QA,"QA VERIFIED","QE Verification","QE Review","Waiting for Review","Won\'t Fix / Duplicate",'
              '"Won\'t Fix / Obsolete","Won\'t Do","WON\'T FIX","Wont Fix",Ready,"Ready for Build","Ready for Dev",'
              '"Ready for Implementation","Ready For Merge","Ready for QA","Ready for QE","Ready For Release",'
              '"Ready for Review","Ready for Test","Ready For Verification","Ready To Demo","Ready to pull",Testing,'
              '"Testing (QE)","Under Review","Under Coalfire Review","Under StackArmor Review","Under Test",'
              'Implementation,Implemented,"In Dev","In Development","On Dev",ON_DEV,ON_QA,"On Review",'
              '"Pending Acceptance","Pending Approval","Pending Deployment",Acceptance,Accepted,Approved,'
              '"Approved/Ready",Archived,Deployed,Done, "Fix Internally DevOps","Fix Internally QE",'
              ' "Feature Complete",Closed,Closing,"Closed by Eng",CLOSED:WONTFIX,"Code Review",Committed,Completed,'
              '"Validate","Validation Backlog","Validation Failed",Verification,Verified,"Verified QA",'
              '"Verified Stage","NAB Review","Needs Review","Needs Peer Review",Merged)',
    'Sakai': ' (Resolved,"In QA","Awaiting Review","Selected for Development",Done,Closed,Verified)',
    'SecondLife': ' (Done, Resolved, Closed)',
    'Sonatype': ' (Done, Resolved, Closed,Approved,Closed)',
    'Spring': ' (Done, Closed, Resolved)',
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
