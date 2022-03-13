#! /usr/bin/python3
"""

This program uses the Jira API to calculate the total autonomy availability uptime for the Ann Arbor May fleet. 

Uptime is defined as having no more than one Lexus in a non-auto ready state (manual only or grounded) as determined by Jira tickets. This means that any time the GEM goes out of a Monitor status, downtime is accruing. 

100% auto readiness therefore is limited to two cases: where the whole fleet is auto ready, or where only one Lexus is NOT auto ready.

TODO: 
    - Handle cases where the ticket is opened in non-auto state and does NOT change state before being closed!
    - Identify those tickets which most severely impact auto-readiness, i.e. has the greatest downtime (could be as simple as finding top 5 elems in sorted list)
    - Add a function checkAutoReadiness() that clearly applies auto readiness condition logic so this program can be easily changed for changing definition in future. Currently all of that logic is in computeDowntime
    - Handle cases where Vehicle State Impact includes 'N/A'. This is the default option for fix on site. Maybe just make this a required field in Jira? Ask Graham.
    - 'Auto readiness' definition will differ slightly be site. Account for this! See point 3. 
    - Add a downtime visualizer? Might be nice. 
    - Add relevant downtime tickets to a dataframe, and allow user to have option to output content to a csv or similar
    - Make terminal output look nicer
    - Add ticket numbers to ignore -- such as when a vehicle is involved in a collision and taken out of service but is grounded in Jira
"""

from jira import JIRA
from pandas import Timedelta, to_datetime, bdate_range, Timestamp
from numpy import argsort, busday_count
import argparse

import config.config as config
import config.jiraConfig as jiraConfig

"""
Checks for required command line input. Returns an argparse Namespace object with relevant information. 
"""
def parseArgs():
    parser = argparse.ArgumentParser(description='This program uses the Jira API to calculate the total autonomy availability uptime for the Ann Arbor May fleet.')
    parser.add_argument('-s', '--site', type = str, required=True,
                        help='Site name.', choices=["AA", "INF", "ARL","HHF", "GRF"])
    parser.add_argument('-q', '--quarter', type = int, required=True,
                        help='Quarter of the year', choices=[1,2,3,4])
    parser.add_argument('-e', '--exclude', type = str, default="",
                        help='Jira ticket IDs to exclude. Must be a single string where keys are comma delineated, e.g. "INF-1380, INF-1381"')
    
    global args
    args = parser.parse_args()
    return 

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
    start, end = config.getQuarter(args.quarter)
    # TODO: Why not use bdate_range() to avoid redundant imports?
    NUM_WEEKDAYS = busday_count(start, end)
    SECONDS_IN_BUSINESS_DAY = (config.close - config.open) * 3600
    return NUM_WEEKDAYS * SECONDS_IN_BUSINESS_DAY

"""
Given two pandas datetime objects with timestamps in the form ('YYYY-MM-DD HH:MM:SS.XXXXXX'), compute the downtime. Downtime only accrues for business days within the range defined by the bounds [start, end]. The start and end timestamps are generated from Jira ticket update and creation timestamps, so it must be checked that these times fall within normal site operating hours (since we only want to accrue downtime while the site is open for business), and if not, adjust them for the final computation. The sum deltaT is the accrued downtime, which is stored in a pandas Timedelta object, and is what this function returns.

The order of operations here are: 
1. Coerce given start and end datetimes to fall within the [site open hours, site closed hours] interval as needed
2. Compute difference between end and start times in seconds
3. Based on whether the end day time (only considering seconds in day) is greater than the start

INPUT: 
- start, the opening bound of the down time interval passed to this function. pd.Timestamp
- end, the closing bound of the down time interval passed to this function. pd.Timestamp
OUTPUT:
- directly returns a pd.Timedelta object, in seconds
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

    # compute difference in business days between bounds and convert to seconds
    diff = len(bdate_range(start, end, inclusive='neither')) * SITE_DAILY_OPERATING_SECONDS

    # compute difference in seconds (assuming same day bounds)
    endTimeInSeconds = end.hour * 3600 + end.minute*60 + end.second
    startTimeInSeconds = start.hour * 3600 + start.minute*60 + start.second

    # if the end time is greater than the start time, just subtract them
    if endTimeInSeconds > startTimeInSeconds:
        diff += endTimeInSeconds - startTimeInSeconds
        return Timedelta(diff, unit='seconds')
    # otherwise, diff += |site close - start time| + |site open - end time|, where end time < start time. Note start and end time have been coerced into times between hours of operation at this point in the function
    else:
        diff += (abs(end.replace(day = start.day, hour = config.close, minute = 0, second = 0) - start) + abs((end.replace(day = end.day, hour = config.open, minute = 0, second = 0) - end))).total_seconds()
        return Timedelta(diff, unit='seconds')

"""
Given a date as a string in the form 'YYYY-MM-DD', or a string in the date time format used by Jira (e.g. '2022-01-14T13:25:07.139-0500'), convert the string to a pandas datetime object and strip any possible timezone information, as we are interested in absolute time differences only. If needed, coerce downtime interval start and end datetime bounds to conform to the period of time we are interested in. 

e.g, if we are looking at the first quarter of the year, and downtime accrued prior to and through the new year, we would not want to count the downtime prior to the new year, only the time from the interval [YYYY-01-01 00:00:00, time vehicle was fixed]. 

INPUT: A pandas timestamp object, and a string passed to the function that indicates if the datetime is the 'open' (start) or 'close' (end) of an interval.
OUTPUT: a pandas timestamp object 
"""
def createDatetimeObject(date: str, bound: str) -> Timestamp:
    datetime = to_datetime(date).tz_localize(None)
    startQuarter, endQuarter = config.getQuarter(args.quarter)
    open = to_datetime(startQuarter).tz_localize(None)
    close = to_datetime(endQuarter).tz_localize(None)

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
This function requires that all relevant json data have been collected using the Jira REST API. This data is provided to it through the relatedIssues input. It parses through items (tickets) in relatedIssues and generates a list (downtimeIntervals) of datetime intervals and relevant vehicle name. It works primarily by inspecting the 'history' tab of each Jira issue for a change in the 'Vehicle State Impact' field. It also checks for tickets that were created in a non-auto ready state and were eventually updated to an auto ready state, within the quarter of interest.

INPUT: 
    - relatedIssues: A list of jira ticket objects (jira.client.ResultList), converted from raw json to a class by the Jira module
    - jira: a jira server instance (jira.client.JIRA)
    - dateTimeRange: two element list containing pandas datetime objects - the closed interval for the date range of interest 
OUTPUT:
    - A three element list containing an interval, and the related vehicle name e.g. [initialDatetime (pd.Timestamp), finalDatetime (pd.Timestamp), vehicle (str)]. These intervals are filtered out from the list of Jira tickets for the given dateTimeRange. The interval itself indicates the time range where the vehicle was NOT auto ready, but does not include any information as to the specific state of the vehicle (manual only or grounded), as these are not needed in the scope of this program's objective.

TODO: Check for tickets that were created with vehicle in non-auto ready state, vehicle impact never changed, and then closed in non-auto ready state (presumably, the vehicle was fixed but the ticket not updated)
"""
def generateDowntimeIntervals(relatedIssues: list, jira: JIRA, dateTimeRange: list) -> list:
    startDatetime, endDatetime = dateTimeRange[0], dateTimeRange[1]
    downtimeIntervals = []

    print("Generating downtime intervals...")

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
    
                    downtimeIntervals.append([initialDate, changeDate, vehicle])
                    print(issue.key, "\t", vehicle, "\t", initialDate, "\t", changeDate)
                    continue

                # catch when cars are made non-auto ready in ticket history when the change occurs after the start of the period of interest
                if (vehicleImpact.toString == 'Manual Only' or vehicleImpact.toString == 'Grounded'):
                    initialCondition = False
                    downDate = changeDate
                
                # mark the transition from non-auto ready to auto-ready, compute instance downtime and add to total downtime
                if (vehicleImpact.toString == 'Monitor'):
                    downtimeIntervals.append([downDate, changeDate, vehicle])
                    print(issue.key, "\t", vehicle, "\t", downDate, "\t", changeDate)

        # at this point we have checked the whole history of a particular vehicle for a change in state. Now check if car was created and closed in non-auto ready state, and if so, add to fleetInterval
        vehicleImpact = issue.fields.customfield_10064.value
        if vehicleImpact in config.nonAutoStates:
            upDate = createDatetimeObject(changelog[-1].created, 'end')
            downDate = createDatetimeObject(changelog[0].created, 'start')
            downtimeIntervals.append([downDate, upDate, vehicle])
            print(issue.key, "\t", vehicle, "\t", downDate, "\t", upDate)

    return downtimeIntervals

"""
Computes the sum of accrued downtimes as provided in the list intervals.

INPUT: A list of lists, where each elem represents a specific vehicle's downtime interval, and has the form [start downtime (pd.Timestamp), end downtime (pd.Timestamp), vehicle name (str) ]
OUTPUT: A sum of all accrued downtime over all intervals.

The main logic that determines auto readiness is applied here.

TODO: Add seperate functions for the WAMs and non-WAMs cases to make this function more readable.
"""
def computeDowntime(intervals: list) -> int:
    if len(intervals) == 0:
        return Timedelta(value=0, unit='seconds').seconds

    intervals.sort(key = lambda x: x[0]) # sort intervals in ascending chronologically updated order, based on the start bound
    prevEnd = intervals[0][1]
    previousWamsEnd = Timestamp(config.getQuarter(args.quarter)[0])
    previousVehicle = intervals[0][2]
    deltaWAMs = Timedelta(0, unit='seconds')
    downTime = Timedelta(value=0, unit='seconds')
    overlappingIntervals = []
    WAMs = config.mayFleet[args.site][-1]
    SECONDS_IN_DAY = 86400

    print("Computing site auto readiness...")

    # check if first vehicle in list is WAMs and add downtime as needed
    if intervals[0][2] == WAMs:
        downTime += computeTimeDelta(intervals[0][0], intervals[0][1])
        previousWamsEnd = intervals[0][1]

    for currStart, currEnd, vehicle in intervals[1:]:

        if vehicle == WAMs:
            # if current WAMs downtime interval overlaps previous WAMs interval, find difference between two time deltas
            if currStart <= previousWamsEnd:
                deltaWAMs = computeTimeDelta(currStart, currEnd) - deltaWAMs
            # else, current WAMs interval does not overlap with previous, so just add the whole interval block to downtime
            else:
                deltaWAMs = computeTimeDelta(currStart, currEnd)

            downTime += deltaWAMs
            print(f"Start: {currStart} End: {min(previousWamsEnd, currEnd)} Delta: {deltaT} Downtime: {downTime} Vehicle: {vehicle} Previous Vehicle: {previousVehicle})")
            previousWamsEnd = max(currEnd, previousWamsEnd)
            continue

        # if current interval's start value is less than previous interval's end, then intervals overlap, so downtime is accruing. The overlap interval is [currStart, min(prevEnd, currEnd)]
        if currStart < prevEnd:
            overlap = [currStart, min(prevEnd, currEnd)]
            overlappingIntervals.append(overlap)
            n = len(overlappingIntervals)
            
            # exclude cases where both overlapping intervals are for same car, and where the interval we accrue for has matching bounds (really, no downtime accrued)
            if vehicle != previousVehicle and currStart != currEnd: 

                # check that current interval start bound isn't less than any previously accounted for end bounds, then compute relevant time delta
                newStart = currStart
                if n < 1:
                    newStart = max([x[1] for x in overlappingIntervals[ : n - 1]])    
                if currStart < newStart:
                    deltaT = computeTimeDelta(newStart, min(prevEnd, currEnd)) 
                    print(f"Start: {newStart} End: {min(previousWamsEnd, currEnd)} Delta: {deltaT} Downtime: {downTime} Vehicle: {vehicle} Previous Vehicle: {previousVehicle})")
                else:
                    deltaT = computeTimeDelta(currStart, min(prevEnd, currEnd))
                    print(f"Start: {currStart} End: {min(previousWamsEnd, currEnd)} Delta: {deltaT} Downtime: {downTime} Vehicle: {vehicle} Previous Vehicle: {previousVehicle})")
                downTime += deltaT
                
        # preserve interval with greater end bound
        prevEnd = max(currEnd, prevEnd)

        # if the larger datetime is the same as the current interval end datetime, update previous vehicle to current vehicle
        if prevEnd == currEnd:
            previousVehicle = vehicle
        
    return downTime.seconds + downTime.days * SECONDS_IN_DAY

"""
Given an integer value downtime in seconds, compute and return the percent auto readiness as a float.
"""
def computeAutoReadyPercent(downtime: int) -> int:
    totalTime = computeTotalTime()
    return ((totalTime - downtime)/totalTime) * 100

"""
At the time of writing this program, the Jira API GET methods are limited to a maximum of 100 results per call, so a workaround like this is necessary to collect all issues related to the JQL for the site in cases where the number of issues exceeds 100. 
INPUT: a Jira server instance, defined in the main function
OUTPUT: a list of jira issues that results from a JQL search defined by buildJQL()
"""
def getRelatedIssues(jira: JIRA) -> list:
    numResults = 100
    relatedIssues = jira.search_issues(jql_str=buildJQL(), maxResults = numResults, startAt = 0)
    assert len(relatedIssues) > 0, "API did not return any Jira issues for JQL {0}".format(buildJQL())
    idx = numResults
    print("Fetching relevant JIRA tickets for site {0}".format(args.site))
    
    while True:
        if len(relatedIssues) % numResults == 0:
            relatedIssues += jira.search_issues(jql_str=buildJQL(), maxResults = numResults, startAt = idx)
            idx += numResults
        else:
            return relatedIssues

def buildJQL():
    assert args.site in config.mayFleet.keys(), "The site name must match one of the keys in the mayFleet hashmap"
    startQuarter, endQuarter = config.getQuarter(args.quarter)

    # check if jira issues to exclude were provided as arguments
    if not args.exclude:
        issuesToExclude = ""
    else:
        issuesToExclude = "AND id NOT IN ({0})".format(args.exclude)
    
    query = 'project IN ("{0}") AND updatedDate >= "{1}" AND updatedDate <= "{2}" AND statusCategory in ("New", "In Progress", "Complete") AND type IN ("Fix On Site","Preventative Maintenance","Support Request") {3} ORDER BY created DESC'.format(args.site, startQuarter, endQuarter, issuesToExclude)
    return query

def dateTimeRange():
    startQuarter, endQuarter = config.getQuarter(args.quarter)
    return [to_datetime(startQuarter).tz_localize(None), to_datetime(endQuarter).tz_localize(None)]


def main():
    parseArgs()
    dateRange = dateTimeRange()
    jira = createServerInstance()
    relatedIssues = getRelatedIssues(jira)
    intervals = generateDowntimeIntervals(relatedIssues, jira, dateRange)
    downtime = computeDowntime(intervals)
    autoReadyPercent = computeAutoReadyPercent(downtime)
    print("Auto readiness is {0}".format(autoReadyPercent))
    print('End program')
    
if __name__ == '__main__':
    main()