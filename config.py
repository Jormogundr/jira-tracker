# Define the period of interest
quarterStart = '2022-01-01'
quarterEnd = '2022-04-01'

# Site specific settings
WAMs = 'Mukti'
site = 'AA'
fleet = ['Mukti', 'Momo', 'Mayble', 'Mitzi', 'Makeba', 'Marinara']
query = 'project IN ("{0}") AND updatedDate >= "{1}" AND updatedDate <= "{2}" AND statusCategory in ("New", "In Progress", "Complete") AND type IN ("Fix On Site","Preventative Maintenance","Support Request") ORDER BY created DESC'.format(site, quarterStart, quarterEnd)
open = 8 # site opening time (int)
close = 20 # site closing time (int)