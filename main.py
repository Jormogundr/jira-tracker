"""

This program uses the Jira API to calculate the total autonomy availability uptime for the Ann Arbor May fleet. 

Uptime is defined as having no more than one Lexus in a non-auto ready state (manual only or grounded) as determined by Jira tickets. This means that any time the GEM goes out of a Monitor status, downtime is accruing. 

100% auto readiness therefore is limited to two cases: where the whole fleet is auto ready, or where only one Lexus is NOT auto ready.


TODO: 
    - Identify those tickets which most severely impact auto-readiness.
    - What about if/when a vehicle is non-auto ready for the WHOLE quarter...?
    - Add a function checkAutoReadiness() that clearly applies auto readiness condition logic so this program can be easily changed for changing definition in future. Currently all of that logic is in computeDowntime()
    - Write test cases for computeDowntime() to make sure it is working as expected.
    - Holidays? 

"""
# ./bin/python3.8

from jira import JIRA
from pandas import Timedelta, to_datetime, bdate_range, Timestamp
from numpy import busday_count

import config
import jiraConfig

"""
Returns a Jira class generated from the jira config info.
"""
def createServerInstance() -> JIRA:
    serverOptions = {'server': jiraConfig.serverName}
    jiraServer = JIRA(options=serverOptions, basic_auth=(jiraConfig.email, jiraConfig.jiraToken))
    return jiraServer

""" 
Given the date range of interest, compute and return total time in seconds that the site is open (service hours). Return type is int.
"""
def computeTotalTime() -> int:
    start = config.quarterStart
    end = config.quarterEnd
    # TODO: Why not use bdate_range() to avoid redundant imports?
    NUM_WEEKDAYS = busday_count(start, end)
    SECONDS_IN_BUSINESS_DAY = (config.close - config.open) * 3600
    return NUM_WEEKDAYS * SECONDS_IN_BUSINESS_DAY

"""
Given two pandas datetime objects with timestamps in the form ('YYYY-MM-DD HH:MM:SS.XXXXXX'), compute the downtime. Downtime only accrues for business days within the range defined by the bounds [start, end]. The start and end timestamps are generated from Jira ticket update and creation timestamps, so it must be checked that these times fall within normal site operating hours (since we only want to accrue downtime while the site is open for business), and if not, adjust them for the final computation. The sum deltaT is the accrued downtime, which is stored in a pandas Timedelta object, and is what this function returns.

The order of operations here are: 
1. find the time delta in business days and convert to seconds, then add to sum deltaT 
2. With the scope of the problem now reduced to difference in time during day, enforce condition that we are only accounting for open operating times
3. Finally, compute the timedelta based on whether we needed to adjust the interval or not. 

"""
def computeTimeDelta(start: Timestamp, end: Timestamp) -> Timedelta:
    SITE_DAILY_OPERATING_SECONDS = (config.close - config.open) * 3600
    timeCorrection = False

    # initialize the sum tracking accrued downtime to the difference in business DAYS between start and end, converted to seconds. 
    # holidays can be included as an argument to bdate_range()
    # there's no elegant way to handle bounds inclusion on bdate ranges with a difference of 0 days -- thus the weird conditional
    if abs(end - start).days > 0:
        deltaT = len(bdate_range(start, end, inclusive='right')) * SITE_DAILY_OPERATING_SECONDS
    else:
        deltaT = 0

    # check if interval open/closing times are confined to site operating hours, and re-assign hours as needed
    if start.hour < config.open or start.hour > config.close:
        start = end.replace(hour = 8, minute = 0, second = 0)
        timeCorrection = True
    if end.hour > config.close or end.hour  < config.open:
        end = start.replace(hour = 20, minute = 0, second = 0)
        timeCorrection = True

    if timeCorrection:
        deltaT += abs(end - start).total_seconds()
    
    # the passed datetime objects fall within normal operating hours for a given day
    # at this point, scope of problem is reduced to finding difference at HOUR:MIN:SEC precision
    # end and start are both datetime objects and the minus sign is overloaded so that a datetime object results from the operation
    else:
        diff = abs(end - start)
        deltaT += diff.seconds

    return Timedelta(deltaT, unit='seconds')

"""
Given a date as a string in the form 'YYYY-MM-DD', or a string in the date time format used by Jira (e.g. '2022-01-14T13:25:07.139-0500'), convert the string to a pandas datetime object and strip any possible timezone information. Return the pandas datetime object.
"""
def createDatetimeObject(date: str) -> Timestamp:
    return to_datetime(date).tz_localize(None)

"""
INPUT: 
    - relatedIssues: A list of jira ticket objects
    - jira: a jira server instance
    - dateTimeRange: two element list containing pandas datetime objects - the closed interval for the date range of interest
OUTPUT:
    - A three element list containing an interval, and the related vehicle name e.g. [initialDatetime, finalDatetime, vehicle]. initialDatetime, finalDatetime are themselves pandas datetime objects, and vehicle is a string. These intervals are filtered out from the list of Jira tickets for the given dateTimeRange. The interval itself indicates the time period where the vehicle was NOT auto ready. 
"""
def generateDowntimeIntervals(relatedIssues: list, jira: JIRA, dateTimeRange: list) -> list:
    startDatetime, endDatetime = dateTimeRange[0], dateTimeRange[1]
    fleetIntervals = []

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
    
                    fleetIntervals.append([initialDate, changeDate, vehicle])
                    print(issue.key, "\t", vehicle, "\t", initialDate, "\t", changeDate)
                    continue

                # catch when cars are made non-auto ready in ticket history when the change occurs after the start of the period of interest
                if (vehicleImpact.toString == 'Manual Only' or vehicleImpact.toString == 'Grounded'):
                    initialCondition = False
                    downDate = changeDate
                
                # mark the transition from non-auto ready to auto-ready, compute instance downtime and add to total downtime
                if (vehicleImpact.toString == 'Monitor'):
                    fleetIntervals.append([downDate, changeDate, vehicle])
                    print(issue.key, "\t", vehicle, "\t", downDate, "\t", changeDate)

    return fleetIntervals

"""
Given a list of intervals and the associated vehicle name, compute in seconds the amount of overlap between intervals for two or more lexus vehicles, and the amount of time in the interval if is the WAMs. Each interval is a three-elem list in the form [initialDatetime, finalDatetime, vehicleName] where each datetime is a numpy datetime object). Return the total downtime in seconds as an integer, as accessed from the datetime.seconds attribute.

The main logic that determines auto readiness is applied here.
"""
def computeDowntime(intervals: list) -> int:

    # no detected downtime
    if len(intervals) == 0:
        return Timedelta(value=0, unit='seconds').seconds

    intervals.sort(key = lambda x: x[0])
    previousEnd = intervals[0][1]
    previousVehicle = intervals[0][2]
    downTime = Timedelta(value=0, unit='seconds')
    overlappingIntervals = [] # keep track of overlapping intervals to avoid counting identical intervals
    SECONDS_IN_DAY = 86400

    # check if first vehicle in list is WAMs and as downtime as needed
    if intervals[0][2] == config.WAMs:
        downTime += computeTimeDelta(intervals[0][0], intervals[0][1])

    # compare two adjacent intervals at a time, specifically the current intervals start point and the previous intervals end point 
    for start, end, vehicle in intervals[1:]:

        # by auto readiness definition, if WAMs is down, then downtime is accruing
        if vehicle == config.WAMs:
            deltaT = computeTimeDelta(start, end)
            downTime += deltaT
            previousEnd = end
            previousVehicle = vehicle
            continue
        
        # we do not want to double count WAMs down time! do not compare it to other downtime intervals.
        if previousVehicle == config.WAMs:
            continue

        # we're only interested in tracking downtime for two or more unique lexus vehicles
        if vehicle == previousVehicle:
            previousEnd = end
            previousVehicle = vehicle
            continue

        # at this point, we have overlapping intervals that we want to accrue downtime for. 
        # overlap is used to check for duplicate intervals -- it is not used to calculate downtime!
        overlap = [start, previousEnd]

        # if current interval's start value is less than previous interval's end, then intervals overlap, so downtime is accruing. Do NOT accrue downtime if the downtime interval has already been accounted for! The overlap interval is [start, min(previousEnd, end)]
        if start < previousEnd and overlap not in overlappingIntervals:
            overlappingIntervals.append(overlap)
            print(start, min(previousEnd, end), computeTimeDelta(start, min(previousEnd, end)))
            downTime += computeTimeDelta(start, min(previousEnd, end))

            # now we must decide which interval to keep for comparison - we ought to keep the overlapping interval with the greater end date. assign vehicle based on this determination
            previousEnd = max(end, previousEnd)
            if previousEnd == end:
                previousVehicle = vehicle

    return downTime.seconds + downTime.days * SECONDS_IN_DAY

"""
Given an integer value downtime in seconds, compute and return the percent auto readiness as a float.
"""
def computeAutoReadyPercent(downtime: int) -> int:
    totalTime = computeTotalTime()
    return ((totalTime - downtime)/totalTime) * 100

"""
"Unique" intervals are intervals with different vehicles. 
Test computeDowntime()
    - When we have three vehicles down - does it double count time or not? Should add 45 min. Check
    - When we have four vehicles down - does it double count time or not? Should add 45 min. Bugged -- FIXED!
    - When we have two vehicles down the whole duration, with intervals that exceed the date range of interest. Bugged -- FIXED!
    - When ONLY the GEM is down for a full day, with time in off hours. Bugged -- FIXED!
    - When downtime intervals exist for the same platform (possible with redundant/duplicate tickets).  Check
    - When downtime exists for two vehicles, each with duplicate/redundant intervals. Check
    - When no downtime exists. Bugged -- FIXED
    - 
"""
def tests():
    # test cases
    computeDowntimeTestCases = [
        [Timestamp('2021-12-31 08:00:00.000000'), Timestamp('2022-04-01 08:45:00.000000'), 'Marinara']
        ]

    # function calls
    print(computeDowntime(computeDowntimeTestCases))
    

def main():
    # tests()
    dateTimeRange =  [createDatetimeObject(config.quarterStart), createDatetimeObject(config.quarterEnd)]
    jira = createServerInstance()
    relatedIssues = jira.search_issues(jql_str=config.query)[::-1]
    intervals = generateDowntimeIntervals(relatedIssues, jira, dateTimeRange)
    downtime = computeDowntime(intervals)
    autoReadyPercent = computeAutoReadyPercent(downtime)
    print("Auto readiness is {0}".format(autoReadyPercent))
    
if __name__ == '__main__':
    main()
    print('End program')