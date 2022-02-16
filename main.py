"""

This program uses the Jira API to calculate the total autonomy availability uptime for the Ann Arbor May fleet. 

Uptime is defined as having no more than one Lexus in a non-auto ready state (manual only or grounded) as determined by Jira tickets. This means that any time the GEM goes out of a Monitor status, downtime is accruing. 

100% auto readiness therefore is limited to two cases: where the whole fleet is auto ready, or where only one Lexus is NOT auto ready.


TODO: 
    - Identify those tickets which most severely impact auto-readiness.
    - Exclude non-operating hours from uptime calculations.

"""

# ./bin/python3.8

from mimetypes import init
from jira import JIRA
from pandas import date_range, to_datetime
from numpy import timedelta64

import config
import jiraConfig

def createServerInstance():
    serverOptions = {'server': jiraConfig.serverName}
    jiraServer = JIRA(options=serverOptions, basic_auth=(jiraConfig.email, jiraConfig.jiraToken))
    return jiraServer

""" 
Given the date range of interest, compute and return total time in seconds

TODO:
    - Remove time where site is not in operation (weekends, 8 PM to 8 AM M-F)
"""
def totalTime(days):
    return len(days) * 86400

"""
Given the date/time of a vehicle state impact change that took a vehicle out of auto ready and the date/time of when it was taken out, compute and return the time in seconds between the two dates/times
"""
def timeDelta(noAutoDate, autoDate):
    # convert date times to the same pandas date time format, and strip the timezone data from the collected Jira dates
    noAutoDate, autoDate = to_datetime(noAutoDate).tz_localize(None), to_datetime(autoDate).tz_localize(None) # 
    ret = (abs(autoDate - noAutoDate) / timedelta64(1,'s'))
    return ret

""" 
Given a dictionary containing keys (vehicles) and values (0 if auto ready, 1 if not), determine if the site is 100% auto-ready
"""
def checkAutoReadyStatusDown(fleetDownStatus):
    if sum(fleetDownStatus.values()) >= 2 or fleetDownStatus[config.WAMs]:
        return True
    else:
        return False

def main():
    jira = createServerInstance()
    fleetStatus = dict((key,False) for key in config.fleet) # for each vehicle (key), False if auto-ready. True otherwise
    startDatetime, endDatetime = to_datetime(config.quarterStart).tz_localize(None), to_datetime(config.quarterEnd).tz_localize(None) # Dates in numpy datetime format, makes it easy to compare dates

    # main loop
    totalDowntime = 0
    for issue in jira.search_issues(jql_str=config.query)[::-1]:

        # fetch the history for a particular issue using the issue key (ex. 'AA-598'). The slicing ensures the history is in ascending datetime order
        issueHistory = jira.issue(id=issue.id, expand='changelog').changelog.histories[::-1]
        initialCondition = True # used to track if ticket was created in non-auto ready state
        initialDate = to_datetime(issue.fields.created).tz_localize(None)

        for i, change in enumerate(issueHistory):
            vehicleImpact = issueHistory[i].items[0]
            changeDate = to_datetime(change.created).tz_localize(None)
            vehicle = issue.fields.customfield_10068[0]

            # if history item changes Vehicle State Impact and change was made within period of interest
            if vehicleImpact.field == 'Vehicle State Impact' and changeDate > startDatetime and changeDate < endDatetime:

                # if ticket was created in non-auto ready state -- vehicle impact only changed to monitor from grounded or manual only. The inequality conditions check that we are only adding downtime for non-auto changes within the period of interest.
                if vehicleImpact.toString == 'Monitor' and initialCondition == True:
                    initialCondition = False
                    fleetStatus[vehicle] = True

                    # if ticket was created in non-auto state but vehicle impact was updated within period of interest
                    if initialDate < startDatetime:
                        initialDate = startDatetime
    
                    downTime = timeDelta(initialDate, changeDate)
                    print("Case: {0} Downtime: {1} Date-range: {2} - {3} Total Downtime: {4}".format(issue.key, downTime, initialDate, changeDate, totalDowntime))

                    # check if auto-readiness condition is violated
                    if checkAutoReadyStatusDown(fleetStatus):
                        totalDowntime += downTime

                    continue

                # catch when cars are made non-auto ready in ticket history when the change occurs after the start of the period of interest
                if (vehicleImpact.toString == 'Manual Only' or vehicleImpact.toString == 'Grounded'):
                    initialCondition = False
                    downDate = changeDate
                    fleetStatus[vehicle] = True
                
                # mark the transition from non-auto ready to auto-ready, compute instance downtime and add to total downtime
                if (vehicleImpact.toString == 'Monitor'):
                    downTime = timeDelta(downDate, changeDate)
                    print("Case: {0} Downtime: {1} Date-range: {2} - {3} Total Downtime: {4}".format(issue.key, downTime, downDate, changeDate, totalDowntime))

                    # check if auto-readiness condition is violated
                    if checkAutoReadyStatusDown(fleetStatus):
                        totalDowntime += downTime

                    # set vehicle back to auto ready
                    fleetStatus[vehicle] = False


    totTime = totalTime(date_range(config.quarterStart,config.quarterEnd,freq='d'))
    autoReadinessPercent = abs((totTime - totalDowntime) / totTime) * 100
    print(autoReadinessPercent, "'%' auto ready")

if __name__ == '__main__':
    main()
    print('End program')