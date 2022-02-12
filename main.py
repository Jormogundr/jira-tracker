"""

This program uses the Jira API to calculate the total autonomy availability uptime for the Ann Arbor May fleet. 

Uptime is defined as having no more than one Lexus in a non-auto ready state (manual only or grounded) as determined by Jira tickets. This means that any time the GEM goes out of a Monitor status, downtime is accruing. 

TODO: 
    - Include WAMS in calculating of downtime. 
    - Only accrue downtime if # of non-auto ready cars >= 2
    - Identify those tickets which most severely impact auto-readiness.
"""

from jira import JIRA
from pandas import date_range, to_datetime
from numpy import timedelta64
import config

def createServerInstance():
    serverOptions = {'server': config.serverName}
    jiraServer = JIRA(options=serverOptions, basic_auth=(config.email, config.jiraToken))
    return jiraServer

# given the date range of interest, compute and return total time in seconds
def totalTime(days):
    return len(days) * 86400

# given the date/time of a vehicle state impact change that took a vehicle out of auto ready and the date/time of when it was taken out, compute and return the time in seconds between the two dates/times
def nonAutoReadyTimeDelta(noAutoDate, autoDate):
    return (abs(to_datetime(autoDate) - to_datetime(noAutoDate)) / timedelta64(1,'s'))


def main():
    jira = createServerInstance()
    assignee = config.username
    starteDate = '2022-02-09'
    endOfQuarter = '2022-04-01'
    endDate = to_datetime("{0}".format(endOfQuarter)).strftime('%Y-%m-%d')  #'2022-04-01' # is the end of the quarter, can use to_datetime("today").strftime('%Y-%m-%d') to get current day, TODO may need to resolve this to seconds
    query = 'project IN ("AA") AND updatedDate >= "{0}" AND updatedDate <= "{1}" AND statusCategory in ("New", "In Progress", "Complete") AND type IN ("Fix On Site","Preventative Maintenance","Support Request") ORDER BY created DESC'.format(starteDate, endDate)
    
    # main loop
    totalDowntime = 0
    for issue in jira.search_issues(jql_str=query):

        # fetch the history for a particular issue using the issue key (ex. 'AA-598'). The slicing ensures the list is in ascending datetime order
        issueHistory = jira.issue(id=issue.id, expand='changelog').changelog.histories[::-1]

        # for a given single issue, loop through the history items and compute downtime using vehicle impact field changes
        vehicleDown = False
        initialCondition = True # this is used to account for cases where ticket is initially created in non-auto ready state, since parsing ticket history skips these cases
        initialDate = issue.fields.created
        siteAutoState = 0 # this is used for calculating a sum of down vehicles. When siteAutoState >= 2, then site is not reaching auto uptime condition
        for i, change in enumerate(issueHistory):
            vehicleImpact = issueHistory[i].items[0]

            # if history item changes Vehicle State Impact, else ignore
            if vehicleImpact.field == 'Vehicle State Impact':

                # if ticket was created in non-auto ready state -- vehicle impact only changed to monitor from grounded or manual only
                if vehicleImpact.toString == 'Monitor' and initialCondition == True and siteAutoState >= 2:
                    initialCondition = False
                    downTime = nonAutoReadyTimeDelta(initialDate, change.created)
                    totalDowntime += downTime
                    siteAutoState += 1
                    continue

                # catch when cars are made non-auto ready in ticket history
                if (vehicleImpact.toString == 'Manual Only' or vehicleImpact.toString == 'Grounded') and vehicleDown == False:
                    vehicleDown = True
                    initialCondition = False
                    downDate = change.created
                    siteAutoState += 1
                    continue
                
                # mark the transition from non-auto ready to auto-ready, compute instance downtime and add to total downtime
                if (vehicleImpact.toString == 'Monitor'):
                    vehicleDown = False
                    upDate = change.created
                    downTime = nonAutoReadyTimeDelta(downDate, upDate)
                    totalDowntime += downTime
                    continue

        print(issue.key, totalDowntime)

    totTime = totalTime(date_range(starteDate,endDate,freq='d'))
    autoReadinessPercent = ((totTime - totalDowntime) / totTime) * 100
    print(autoReadinessPercent, "'%' auto ready")

if __name__ == '__main__':
    main()
    print('End program')