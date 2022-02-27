# Define the period of interest
quarterStart = '2022-01-01'
quarterEnd = '2022-04-01'

# Site specific settings
WAMs = 'Mukti'
site = 'AA'
fleet = ['Mayble', 'Makeba', 'Momo', 'Marinara', 'Mitzi']
query = 'project IN ("{0}") AND updatedDate >= "{1}" AND updatedDate <= "{2}" AND statusCategory in ("New", "In Progress", "Complete") AND type IN ("Fix On Site","Preventative Maintenance","Support Request") ORDER BY created DESC'.format(site, quarterStart, quarterEnd)
open = 8 # site opening time (int)
close = 20 # site closing time (int)

# Other configs
holidays = [] # each elem should be in form "YYYY, MM, DD", e.g. ["2022, 5, 30", "2022, 6, 20", "2022, 7, 4"]