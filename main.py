"""

This program uses the Jira API to calculate the total autonomy availability uptime for the Ann Arbor May fleet. 

Uptime is defined as having no more than one Lexus in a non-auto ready state (manual only or grounded) as determined by Jira tickets. This means that any time the GEM goes out of a Monitor status, downtime is accruing. 

100% auto readiness therefore is limited to two cases: where the whole fleet is auto ready, or where only one Lexus is NOT auto ready.

TODO: 
    - Identify those tickets which most severely impact auto-readiness.
    - Exclude non-operating hours from uptime calculations.

"""

from jira import JIRA
from pandas import date_range, to_datetime, DatetimeIndex
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
def timeDelta(noAutoDate, autoDate):

    # convert date times to the same pandas date time format, and strip the timezone data from the collected Jira dates
    checkStart, checkEnd = to_datetime(config.quarterStart), to_datetime(config.quarterEnd)
    noAutoDate, autoDate = to_datetime(noAutoDate).tz_localize(None), to_datetime(autoDate).tz_localize(None)
    
    # if the start of the downtime is less then the interval we are interested in, set downtime to start of interval
    # this avoids considering downtime outside of the time interval we are interesed in 
    if noAutoDate < checkStart:
        noAutoDate = checkStart

    if autoDate > checkEnd:
        autoDate = checkEnd

    ret = (abs(autoDate - noAutoDate) / timedelta64(1,'s'))

    return ret

# Given a dictionary containing keys (vehicles) and values (0 if auto ready, 1 if not), determine if the site is 100% auto-ready
def checkAutoReadyStatusDown(fleetDownStatus):
    if sum(fleetDownStatus.values()) >= 2 or fleetDownStatus[config.WAMs]:
        return True
    else:
        return False

def main():
    jira = createServerInstance()
    startDate, endDate = config.quarterStart, config.quarterEnd
    query = 'project IN ("{0}") AND updatedDate >= "{1}" AND updatedDate <= "{2}" AND statusCategory in ("New", "In Progress", "Complete") AND type IN ("Fix On Site","Preventative Maintenance","Support Request") ORDER BY created DESC'.format(config.site, startDate, endDate)
    fleetDownStatus = dict((key,False) for key in config.fleet) # for each vehicle (key), False if auto-ready. True otherwise

    # main loop
    totalDowntime = 0
    for issue in jira.search_issues(jql_str=query):

        # fetch the history for a particular issue using the issue key (ex. 'AA-598'). The slicing ensures the history is in ascending datetime order
        issueHistory = jira.issue(id=issue.id, expand='changelog').changelog.histories[::-1]

        # for a given single issue, loop through the history items and compute downtime using vehicle impact field changes
        vehicleDown = False
        initialCondition = True # this is used to account for cases where ticket is initially created in non-auto ready state, since parsing ticket history skips these cases
        initialDate = issue.fields.created

        for i, change in enumerate(issueHistory):
            vehicleImpact = issueHistory[i].items[0]

            # if history item changes Vehicle State Impact, else ignore
            if vehicleImpact.field == 'Vehicle State Impact':

                # if ticket was created in non-auto ready state -- vehicle impact only changed to monitor from grounded or manual only
                if vehicleImpact.toString == 'Monitor' and initialCondition == True:
                    initialCondition = False
                    fleetDownStatus[issue.fields.customfield_10068[0]] = True # that index is the vehicle for issue. Yeah. 
                    downTime = timeDelta(initialDate, change.created)
                    print("Issue: {0} Downtime: {1} Date-range: {2} - {3}".format(issue.key, downTime, initialDate, change.created))
                    
                    # Lastly, if the site's definition of 100% auto availability is violated, then add downtime
                    if checkAutoReadyStatusDown(fleetDownStatus):
                        totalDowntime += downTime
                        
                    continue

                # catch when cars are made non-auto ready in ticket history
                if (vehicleImpact.toString == 'Manual Only' or vehicleImpact.toString == 'Grounded') and vehicleDown == False:
                    vehicleDown = True
                    initialCondition = False
                    downDate = change.created
                    fleetDownStatus[issue.fields.customfield_10068[0]] = True 
                
                # mark the transition from non-auto ready to auto-ready, compute instance downtime and add to total downtime
                if (vehicleImpact.toString == 'Monitor'):
                    vehicleDown = False
                    fleetDownStatus[issue.fields.customfield_10068[0]] = False
                    upDate = change.created
                    downTime = timeDelta(downDate, upDate)
                    print("Issue: {0} Downtime: {1} Date-range: {2} - {3}".format(issue.key, downTime, downDate, upDate))

                    # if site is not 100% auto ready, compute and add downtime
                    if checkAutoReadyStatusDown(fleetDownStatus):
                        totalDowntime += downTime
                        
                    

    totTime = totalTime(date_range(startDate,endDate,freq='d'))
    autoReadinessPercent = abs((totTime - totalDowntime) / totTime) * 100
    print(autoReadinessPercent, "'%' auto ready")

if __name__ == '__main__':
    main()
    print('End program')