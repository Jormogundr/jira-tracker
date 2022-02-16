"""

This program uses the Jira API to calculate the total autonomy availability uptime for the Ann Arbor May fleet. 

Uptime is defined as having no more than one Lexus in a non-auto ready state (manual only or grounded) as determined by Jira tickets. This means that any time the GEM goes out of a Monitor status, downtime is accruing. 

100% auto readiness therefore is limited to two cases: where the whole fleet is auto ready, or where only one Lexus is NOT auto ready.


TODO: 
    - Identify those tickets which most severely impact auto-readiness.
    - Exclude non-operating hours from uptime calculations.
    - Break up the main loop into different functions -- it's much too large. He's some ideas
    - Verify functionality - does it actually do what it's supposed to, i.e. compute and add downtime when appropriate (at same point in time, more than 1 lexus vehicle down OR )
    - What about if/when a vehicle is non-auto ready for the WHOLE quarter...?

"""
# ./bin/python3.8

from copy import copy
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
def checkAutoReadyStatusDown(fleetStatus):
    lexusStatus = copy(fleetStatus)
    lexusStatus.pop(config.WAMs)
    if sum(lexusStatus.values()) >= 2 or fleetStatus[config.WAMs]:
        return True
    else:
        return False

def createDatetimeObject(date):
    return to_datetime(date).tz_localize(None)


"""
INPUT: 
    - relatedIssues: A list of jira ticket obkects
    - jira: a jira server instance
    - dateTimeRange: two element list containing pandas datetime objects - the closed interval for the date range of interest
OUTPUT:
    - A dict of intervals - where each interval is a list in the form [initialDatetime, finalDatetime]. initialDatetime, finalDatetime are themselves pandas datetime objects. The key is the vehicle name, and the values are the intervals associated with the vehicle. These intervals are filtered out from the list of Jira tickets for the given dateTimeRange. The interval itself indicates the time period where the vehicle was NOT auto ready. 
"""
def generateDowntimeIntervals(relatedIssues, jira, dateTimeRange):
    startDatetime, endDatetime = dateTimeRange[0], dateTimeRange[1]
    fleetStatus = dict((key,[]) for key in config.fleet) # for each vehicle (key), False if auto-ready. True otherwise

    for issue in relatedIssues:

        # fetch the history for a particular issue using the issue key (ex. 'AA-598'). The slicing ensures the history is in ascending datetime order
        changelog = jira.issue(id=issue.id, expand='changelog').changelog.histories[::-1]
        initialCondition = True # used to track if ticket was created in non-auto ready state
        initialDate = createDatetimeObject(issue.fields.created)

        for i, change in enumerate(changelog):
            vehicleImpact = changelog[i].items[0]
            changeDate = createDatetimeObject(change.created)
            vehicle = issue.fields.customfield_10068[0].capitalize()

            # if history item changes Vehicle State Impact and change was made within period of interest
            if vehicleImpact.field == 'Vehicle State Impact' and changeDate > startDatetime and changeDate < endDatetime:

                # if ticket was created in non-auto ready state -- vehicle impact only changed to monitor from grounded or manual only. The inequality conditions check that we are only adding downtime for non-auto changes within the period of interest.
                if vehicleImpact.toString == 'Monitor' and initialCondition == True:
                    initialCondition = False

                    # if ticket was created in non-auto state but vehicle impact was updated within period of interest
                    if initialDate < startDatetime:
                        initialDate = startDatetime
    
                    fleetStatus[vehicle].append([initialDate, changeDate])
                    continue

                # catch when cars are made non-auto ready in ticket history when the change occurs after the start of the period of interest
                if (vehicleImpact.toString == 'Manual Only' or vehicleImpact.toString == 'Grounded'):
                    initialCondition = False
                    downDate = changeDate
                
                # mark the transition from non-auto ready to auto-ready, compute instance downtime and add to total downtime
                if (vehicleImpact.toString == 'Monitor'):
                    fleetStatus[vehicle].append([downDate, changeDate])

    return fleetStatus

"""
Given a list of intervals compute in seconds the amount of overlap between intervals for two or more lexus vehicles, and the amount of time in the interval if is the WAMs. Each interval is a two-elem list in the form [initialDatetime, finalDatetime] where each elem is a numpy datetime object). Return the total downtime. 
"""
def computeDowntime(intervals):
    for vehicle, interval in intervals:
        print()
        pass

def main():
    jira = createServerInstance()
    relatedIssues = jira.search_issues(jql_str=config.query)[::-1]
    dateTimeRange =  [createDatetimeObject(config.quarterStart), createDatetimeObject(config.quarterEnd)]
    intervals = generateDowntimeIntervals(relatedIssues, jira, dateTimeRange)
    computeDowntime(intervals)
    

if __name__ == '__main__':
    main()
    print('End program')