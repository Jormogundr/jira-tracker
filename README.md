# jira-tracker

This tool is meant to be a metric generator for sites to use to track auto readiness, as part of the larger goal of achieving driver out readiness by the end of the year.

# Solution

First, we must define auto-readiness. One hundred percent auto-readiness is no more than one Lexus vehicle down, and the GEM must not be down. Down is manual only or grounded. 

The challenge is then to use the Jira API to extract relevant tickets, dates, and vehicle state impact transitions. The vehicle state impact is the custom field for all Jira tickets that defines the health of the vehicle. 

To accomplish computing vehicle uptime, we can envision a timeline over an interval [start of quarter, end of quarter], or any arbitrary date range. Then over the entire date range, plot out all vehicle transitions from up to down, and vice versa. For example, take the plot below.

![Time Line](resources/img/timeline.png)

Here, a box is generated any time a vehicle goes down. The box's length covers the interval [down time start date, down time end date i.e. fix date]. By the definition of auto readiness above, we can easily see when the condition is violated: any time two boxes or more boxes overlap, and anytime the WAMs (in this case Mukti) goes down. The red portions of the box indicate the time that would count against 100% auto readiness. 

To implement this, we can try leaning on pandas dataframes. We first need to filter out only the relevant date changes for all tickets in Jira that were updated over the timeline. 

# Environment setup:
Go to https://maymobility.atlassian.net/jira/your-work and click on the gear icon > Atlassian Account Settings > Security > Create and manage API tokens > Create API Token. Copy this token to jiraConfig.jiraToken

While you're there, make sure the email associated with your Jira account is entered, and the server name is correct, e.g. 'https://maymobility.atlassian.net/'

Then, install dependencies:

pip install virtualenv

virtualenv --python=/usr/bin/python3.8 jira-tracker

cd jira-tracker

source bin/activate

pip install -r requirements.txt

Run using the python3.8 interpeter in ./bin/

