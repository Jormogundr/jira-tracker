from datetime import date

open = 8 # site opening time (int)
close = 20 # site closing time (int)
holidays = [] # each elem should be in form "YYYY, MM, DD", e.g. ["2022, 5, 30", "2022, 6, 20", "2022, 7, 4"]
nonAutoStates = ['Grounded', 'Manual Only']

###########################################################################################################################################################
###################         Nothing below should need to be changed. Exceptions might include something like site fleet changes         ###################
###########################################################################################################################################################

"""
The WAMs vehicle must be the last item in each list!
"""
mayFleet = {
    "INF": ['Mandu', 'Marbles', 'Mvemjsunp', 'Mario', 'Mooi'], 
    "AA": ['Momo', 'Mitzi', 'Makeba', 'Marinara', 'Mayble', 'Mukti'],
    "ARL": ['Mojo', 'Morocca', 'Molly', 'Marty','McHale'],
    "GRF": ['Minerva', 'Meow', 'Michigan', 'Murphy'],
    "HHF": ['Maria', 'Myla', 'Mimi']
    }

"""
Given a quarter of the year [1,2,3,4], return the start and end of the quarter in dates as strings, in the form YYYY-MM-DD
"""
def getQuarter(quarter):
    currentYear = date.today().year
    quarters = {
    1: [f"{currentYear}-01-01", f"{currentYear}-04-01"],
    2: [f"{currentYear}-04-01", f"{currentYear}-07-01"],
    3: [f"{currentYear}-07-01", f"{currentYear}-10-01"],
    4: [f"{currentYear}-10-01", f"{currentYear + 1}-01-01"]
    }   
    return quarters[quarter][0], quarters[quarter][1]


