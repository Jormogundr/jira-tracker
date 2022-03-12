"""

This program uses the Jira API to calculate the total autonomy availability uptime for the Ann Arbor May fleet. 

Uptime is defined as having no more than one Lexus in a non-auto ready state (manual only or grounded) as determined by Jira tickets. This means that any time the GEM goes out of a Monitor status, downtime is accruing. 

100% auto readiness therefore is limited to two cases: where the whole fleet is auto ready, or where only one Lexus is NOT auto ready.


TODO: 
    - Handle cases where the ticket is opened in non-auto state and does NOT change state before being closed!
    - Identify those tickets which most severely impact auto-readiness.
    - What about if/when a vehicle is non-auto ready for the WHOLE quarter...?
    - Add a function checkAutoReadiness() that clearly applies auto readiness condition logic so this program can be easily changed for changing definition in future. Currently all of that logic is in computeDowntime()
    - Write test cases for computeDowntime() to make sure it is working as expected.
    - Holidays? 
    - Handle cases where Vehicle State Impact includes 'N/A'. This is the default option for fix on site. Maybe just make this a required field in Jira? Ask Graham.
    - 'Auto readiness' definition will differ slightly be site. Account for this! See point 3. 
    - Add a downtime visualizer? Might be nice. 
    - Clean up. Good lord.
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

    # check if interval open/closing times are confined to site operating hours, and re-assign hours as needed
    if start.hour < config.open:
        start = start.replace(hour = 8, minute = 0, second = 0)
    if  start.hour > config.close:
        start = start.replace(hour = 8, minute = 0, second = 0) + Timedelta(days=1)
    if end.hour > config.close:
        end = end.replace(hour = 20, minute = 0, second = 0)
    if end.hour  < config.open:
        end = end.replace(hour = 20, minute = 0, second = 0) - Timedelta(days=1)

    endTimeInSeconds = end.hour * 3600 + end.minute*60 + end.second
    startTimeInSeconds = start.hour * 3600 + start.minute*60 + start.second
    diff = len(bdate_range(start, end, inclusive='neither')) * SITE_DAILY_OPERATING_SECONDS

    # if the end time is greater than the start time, just subtract them
    if endTimeInSeconds > startTimeInSeconds:
        diff += endTimeInSeconds - startTimeInSeconds
        return Timedelta(diff, unit='seconds')
    # otherwise, diff += |site close - start time| + |site open - end time|, where end time < start time. Note start and end time have been coerced into times between hours of operation at this point in the function
    else:
        diff += (abs(end.replace(day = start.day, hour = config.close, minute = 0, second = 0) - start) + abs((end.replace(day = end.day, hour = config.open, minute = 0, second = 0) - end))).total_seconds()
        return Timedelta(diff, unit='seconds')


"""
Given a date as a string in the form 'YYYY-MM-DD', or a string in the date time format used by Jira (e.g. '2022-01-14T13:25:07.139-0500'), convert the string to a pandas datetime object and strip any possible timezone information. If needed is, coerce downtime interval start and end datetime bounds to conform to the period of time we are interested in. 

e.g, if we are looking at the first quarter of the year, and downtime accrued prior to and through the new year, we would not want to count the downtime prior to the new year, only the time from the interval [YYYY-01-01 00:00:00, time vehicle was fixed]. 

INPUT: A pandas timestamp object, and a string passed to the function that indicates if the datetime is the 'open' (start) or 'close' (end) of an interval.
OUTPUT: a pandas datetime object 
"""
def createDatetimeObject(date: str, bound: str) -> Timestamp:
    datetime = to_datetime(date).tz_localize(None)
    open = to_datetime(config.quarterStart).tz_localize(None)
    close = to_datetime(config.quarterEnd).tz_localize(None)

    # check for invalid datetimes, i.e. when a ticket is closed prior to period of interest but gets 'updated' with a comment WITHIN the period of interest
    # returning either bound of the period of interest should result in identical intervals i.e. [start, start] so no downtime would accrue for these tickets
    if bound == 'end' and datetime < open:
        return open
    if bound == 'start' and datetime > close:
        return close 

    # check for valid datetimes but check if they need to be corrected
    if bound == 'start' and datetime < open:
        datetime = open
    if bound == 'end' and datetime > close:
        datetime = close
    return datetime

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
        initialDate = createDatetimeObject(issue.fields.created, 'start')
        vehicle = issue.fields.customfield_10068[0].capitalize()

        for i, change in enumerate(changelog):
            vehicleImpact = changelog[i].items[0]
            changeDate = createDatetimeObject(change.created, 'end')

            # if history item changes Vehicle State Impact and change was made within period of interest
            if vehicleImpact.field == 'Vehicle State Impact' and changeDate > startDatetime and changeDate < endDatetime:

                # if ticket was created in non-auto ready state -- vehicle impact only changed to monitor from grounded or manual only
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

        # at this point we have checked the whole history of a particular vehicle for a change in state. Now check if car was created and closed in non-auto ready state, and if so, add to fleetInterval
        vehicleImpact = issue.fields.customfield_10064.value
        if vehicleImpact in config.nonAutoStates:
            upDate = createDatetimeObject(changelog[-1].created, 'end')
            downDate = createDatetimeObject(changelog[0].created, 'start')
            fleetIntervals.append([downDate, upDate, vehicle])
            print(issue.key, "\t", vehicle, "\t", downDate, "\t", upDate)

    return fleetIntervals

"""
Given a list of intervals and the associated vehicle name, compute in seconds the amount of overlap between intervals for two or more lexus vehicles, and the amount of time in the interval if is the WAMs. Each interval is a three-elem list in the form [initialDatetime, finalDatetime, vehicleName] where each datetime is a numpy datetime object). Return the total downtime in seconds as an integer, as accessed from the datetime.seconds attribute.

The main logic that determines auto readiness is applied here.
"""
def computeDowntime(intervals: list) -> int:

    # no detected downtime
    if len(intervals) == 0:
        return Timedelta(value=0, unit='seconds').seconds

    intervals.sort(key = lambda x: x[0]) # sort intervals in ascending chronologically updated order, based on the start bound
    previousEnd = intervals[0][1]
    previousWamsEnd = Timestamp(config.quarterStart)
    previousVehicle = intervals[0][2]
    downTime = Timedelta(value=0, unit='seconds')
    overlappingIntervals = [] # keep track of overlapping intervals to avoid counting identical intervals
    SECONDS_IN_DAY = 86400

    # check if first vehicle in list is WAMs and add downtime as needed
    if intervals[0][2] == config.WAMs:
        downTime += computeTimeDelta(intervals[0][0], intervals[0][1])
        previousWamsEnd = intervals[0][1]

    # compare two adjacent intervals at a time, specifically the current intervals start point and the previous intervals end point 
    for start, end, vehicle in intervals[1:]:

        # we do not want to double count WAMs down time! do not compare it to other downtime intervals.
        if previousVehicle == config.WAMs:
                previousVehicle = vehicle
                previousEnd = end
                continue

        # by auto readiness definition, if WAMs is down, then downtime is accruing. 
        if vehicle == config.WAMs and end > previousWamsEnd:
            deltaT = computeTimeDelta(previousWamsEnd, end)
            downTime += deltaT
            previousWamsEnd = end
            previousVehicle = vehicle
            print(start, min(previousEnd, end), deltaT)
            continue

        # at this point, we have overlapping intervals that we want to accrue downtime for. 
        # overlap is used to check for duplicate intervals -- it is not used to calculate downtime!
        #overlap = [start, previousEnd]

        # if current interval's start value is less than previous interval's end, then intervals overlap, so downtime is accruing. Do NOT accrue downtime if the downtime interval has already been accounted for! The overlap interval is [start, min(previousEnd, end)]
        if start < previousEnd:# and overlap not in overlappingIntervals:
            #overlappingIntervals.append(overlap)
            print(start, min(previousEnd, end), computeTimeDelta(start, min(previousEnd, end)))

            # exclude cases where both overlapping intervals are for same car, and when the interval we accrue for has matching bounds
            if vehicle != previousVehicle and start != end: 
                downTime += computeTimeDelta(start, min(previousEnd, end))

        # now we must decide which interval to keep for comparison - we ought to keep the overlapping interval with the greater end date. assign vehicle based on this determination
        previousEnd = max(end, previousEnd)

        # if the larger datetime is the same as the current interval end datetime, update previous vehicle to current vehicle
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

"""
At the time of writing this program, the Jira API GET methods are limited to a maximum of 100 results per call, so a workaround like this is necessary to collect all issues related to the JQL for the site in cases where the number of issues exceeds 100. 
INPUT: a Jira server instance, defined in the main function
OUTPUT: a list of jira issues that results from a JQL search defined by config.query
"""
def getRelatedIssues(jira: JIRA) -> list:
    numResults = 100
    relatedIssues = jira.search_issues(jql_str=config.query, maxResults = numResults, startAt = 0)
    idx = numResults

    
    # TODO: Maybe only collect fields that are pertinent to the work done by this program
    while True:
        if len(relatedIssues) % numResults == 0:
            relatedIssues += jira.search_issues(jql_str=config.query, maxResults = numResults, startAt = idx)
            idx += numResults
        else:
            break
    
    return relatedIssues

# This is just here to speed up debugging. This is the output for ARB.
def REMOVE_ME():
    return [
        [Timestamp('2022-01-01 00:00:00'), Timestamp('2022-01-01 00:00:00'), 'Meow'] ,
        [Timestamp('2022-01-01 00:00:00'), Timestamp('2022-01-03 14:04:08.341000'), 'Minerva'] ,
        [Timestamp('2022-01-01 00:00:00'), Timestamp('2022-01-01 00:00:00'), 'Mischief'] ,
        [Timestamp('2022-01-01 00:00:00'), Timestamp('2022-01-10 09:48:25.490000'), 'Michigan'] ,
        [Timestamp('2022-01-01 00:00:00'), Timestamp('2022-01-04 12:33:35.489000'), 'Michigan'] ,
        [Timestamp('2022-01-01 00:00:00'), Timestamp('2022-01-14 12:01:42.276000'), 'Murphy'] ,
        [Timestamp('2022-01-01 00:00:00'), Timestamp('2022-01-17 07:20:44.863000'), 'Murphy'] ,
        [Timestamp('2022-01-04 14:19:14.735000'), Timestamp('2022-01-05 15:06:31.129000'), 'Minerva'] ,
        [Timestamp('2022-01-05 13:46:04.299000'), Timestamp('2022-01-06 05:51:10.380000'), 'Mischief'] ,
        [Timestamp('2022-01-05 15:29:13.288000'), Timestamp('2022-01-06 05:47:05.881000'), 'Mischief'] ,
        [Timestamp('2022-01-05 18:27:34.217000'), Timestamp('2022-01-14 15:04:08.277000'), 'Minerva'] ,
        [Timestamp('2022-01-12 14:01:38.929000'), Timestamp('2022-01-21 08:14:26.929000'), 'Mischief'] ,
        [Timestamp('2022-01-14 10:34:20.973000'), Timestamp('2022-01-14 13:32:11.442000'), 'Mischief'] ,
        [Timestamp('2022-01-14 15:41:09.106000'), Timestamp('2022-01-14 15:41:11.292000'), 'Mischief'] ,
        [Timestamp('2022-02-04 11:37:26.428000'), Timestamp('2022-03-04 14:34:53.947000'), 'Michigan'] ,
        [Timestamp('2022-02-08 11:22:43.697000'), Timestamp('2022-02-08 11:56:07.179000'), 'Mischief'] ,
        [Timestamp('2022-02-10 11:08:29.898000'), Timestamp('2022-03-02 12:36:20.659000'), 'Meow'] ,
        [Timestamp('2022-02-14 05:33:33.351000'), Timestamp('2022-03-02 09:39:54.232000'), 'Mischief'] ,
        [Timestamp('2022-02-14 05:41:04.157000'), Timestamp('2022-02-17 11:20:00.134000'), 'Murphy'] ,
        [Timestamp('2022-02-18 11:14:53.296000'), Timestamp('2022-02-22 11:17:29.872000'), 'Michigan'] ,
        [Timestamp('2022-02-18 11:16:02.157000'), Timestamp('2022-02-28 13:00:53.640000'), 'Michigan'] ,
        [Timestamp('2022-02-23 09:14:44.744000'), Timestamp('2022-02-24 16:00:26.543000'), 'Michigan'] ,
        [Timestamp('2022-02-24 08:45:57.579000'), Timestamp('2022-03-01 11:27:19.850000'), 'Mischief']
    ]

def main():
    # tests()
    # dateTimeRange =  [to_datetime(config.quarterStart).tz_localize(None), to_datetime(config.quarterEnd).tz_localize(None)]
    # jira = createServerInstance()
    # relatedIssues = getRelatedIssues(jira)
    # intervals = generateDowntimeIntervals(relatedIssues, jira, dateTimeRange)
    intervals = REMOVE_ME()
    downtime = computeDowntime(intervals)
    autoReadyPercent = computeAutoReadyPercent(downtime)
    print("Auto readiness is {0}".format(autoReadyPercent))
    
if __name__ == '__main__':
    main()
    print('End program')