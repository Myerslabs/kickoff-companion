"""Word lists for the test league (ENH-25, owner 2026-10-25: "why not make the real teams the backup
league?"): the schools, mascots, abbreviations, conferences and colors are real FBS teams, laid into the league's fixed
shape (four conferences of 16, five of 12, one of 10, two independents), mostly in their real conference; UAB and UTSA sit
out to fit. The games, the stats, the players and the coaches stay invented, so every test plays the same on every run.
Bowls, networks and the FCS teams are invented too."""

from __future__ import annotations

# The demo's own team: the one the app follows in demo mode and in the tests.
OUR_SCHOOL = "Florida"

# (conference, short label, [(school, mascot, abbreviation), ...]). Four conferences of 16, five
# of 12, one of 10, and two independents: 136 teams, the size of FBS.
CONFERENCES: list[tuple[str, str, list[tuple[str, str, str]]]] = [
    ("SEC", "SEC", [
        ("Florida", "Gators", "FLA"),
        ("Alabama", "Crimson Tide", "ALA"),
        ("Arkansas", "Razorbacks", "ARK"),
        ("Auburn", "Tigers", "AUB"),
        ("Georgia", "Bulldogs", "UGA"),
        ("Kentucky", "Wildcats", "UK"),
        ("LSU", "Tigers", "LSU"),
        ("Mississippi State", "Bulldogs", "MSST"),
        ("Missouri", "Tigers", "MIZ"),
        ("Oklahoma", "Sooners", "OU"),
        ("Ole Miss", "Rebels", "MISS"),
        ("South Carolina", "Gamecocks", "SC"),
        ("Tennessee", "Volunteers", "TENN"),
        ("Texas", "Longhorns", "TEX"),
        ("Texas A&M", "Aggies", "TA&M"),
        ("Vanderbilt", "Commodores", "VAN"),
    ]),
    ("Big Ten", "B1G", [
        ("Illinois", "Fighting Illini", "ILL"),
        ("Indiana", "Hoosiers", "IU"),
        ("Iowa", "Hawkeyes", "IOWA"),
        ("Maryland", "Terrapins", "MD"),
        ("Michigan", "Wolverines", "MICH"),
        ("Michigan State", "Spartans", "MSU"),
        ("Minnesota", "Golden Gophers", "MINN"),
        ("Nebraska", "Cornhuskers", "NEB"),
        ("Northwestern", "Wildcats", "NU"),
        ("Ohio State", "Buckeyes", "OSU"),
        ("Oregon", "Ducks", "ORE"),
        ("Penn State", "Nittany Lions", "PSU"),
        ("Purdue", "Boilermakers", "PUR"),
        ("Rutgers", "Scarlet Knights", "RUTG"),
        ("UCLA", "Bruins", "UCLA"),
        ("USC", "Trojans", "USC"),
    ]),
    ("Big 12", "B12", [
        ("Arizona", "Wildcats", "ARIZ"),
        ("Arizona State", "Sun Devils", "ASU"),
        ("BYU", "Cougars", "BYU"),
        ("Baylor", "Bears", "BAY"),
        ("Cincinnati", "Bearcats", "CIN"),
        ("Colorado", "Buffaloes", "COLO"),
        ("Houston", "Cougars", "HOU"),
        ("Iowa State", "Cyclones", "ISU"),
        ("Kansas", "Jayhawks", "KU"),
        ("Kansas State", "Wildcats", "KSU"),
        ("Oklahoma State", "Cowboys", "OKST"),
        ("TCU", "Horned Frogs", "TCU"),
        ("Texas Tech", "Red Raiders", "TTU"),
        ("UCF", "Knights", "UCF"),
        ("Utah", "Utes", "UTAH"),
        ("West Virginia", "Mountaineers", "WVU"),
    ]),
    ("ACC", "ACC", [
        ("Boston College", "Eagles", "BC"),
        ("California", "Golden Bears", "CAL"),
        ("Clemson", "Tigers", "CLEM"),
        ("Duke", "Blue Devils", "DUKE"),
        ("Florida State", "Seminoles", "FSU"),
        ("Georgia Tech", "Yellow Jackets", "GT"),
        ("Louisville", "Cardinals", "LOU"),
        ("Miami", "Hurricanes", "MIA"),
        ("NC State", "Wolfpack", "NCSU"),
        ("North Carolina", "Tar Heels", "UNC"),
        ("Pittsburgh", "Panthers", "PITT"),
        ("SMU", "Mustangs", "SMU"),
        ("Stanford", "Cardinal", "STAN"),
        ("Syracuse", "Orange", "SYR"),
        ("Virginia", "Cavaliers", "UVA"),
        ("Virginia Tech", "Hokies", "VT"),
    ]),
    ("Mountain West", "MWC", [
        ("Air Force", "Falcons", "AF"),
        ("Hawai'i", "Rainbow Warriors", "HAW"),
        ("Nevada", "Wolf Pack", "NEV"),
        ("New Mexico", "Lobos", "UNM"),
        ("North Dakota State", "Bison", "NDSU"),
        ("Northern Illinois", "Huskies", "NIU"),
        ("San José State", "Spartans", "SJSU"),
        ("UNLV", "Rebels", "UNLV"),
        ("UTEP", "Miners", "UTEP"),
        ("Wyoming", "Cowboys", "WYO"),
        ("Washington", "Huskies", "WASH"),
        ("Wisconsin", "Badgers", "WIS"),
    ]),
    ("Sun Belt", "SBC", [
        ("App State", "Mountaineers", "APP"),
        ("Arkansas State", "Red Wolves", "ARST"),
        ("Coastal Carolina", "Chanticleers", "CCU"),
        ("Georgia Southern", "Eagles", "GASO"),
        ("Georgia State", "Panthers", "GAST"),
        ("James Madison", "Dukes", "JMU"),
        ("Louisiana", "Ragin' Cajuns", "UL"),
        ("Louisiana Tech", "Bulldogs", "LT"),
        ("Marshall", "Thundering Herd", "MRSH"),
        ("Old Dominion", "Monarchs", "ODU"),
        ("South Alabama", "Jaguars", "USA"),
        ("Southern Miss", "Golden Eagles", "USM"),
    ]),
    ("Mid-American", "MAC", [
        ("Akron", "Zips", "AKR"),
        ("Ball State", "Cardinals", "BALL"),
        ("Bowling Green", "Falcons", "BGSU"),
        ("Buffalo", "Bulls", "BUF"),
        ("Central Michigan", "Chippewas", "CMU"),
        ("Eastern Michigan", "Eagles", "EMU"),
        ("Kent State", "Golden Flashes", "KENT"),
        ("Massachusetts", "Minutemen", "MASS"),
        ("Miami (OH)", "RedHawks", "M-OH"),
        ("Ohio", "Bobcats", "OHIO"),
        ("Sacramento State", "Hornets", "SAC"),
        ("Toledo", "Rockets", "TOL"),
    ]),
    ("Conference USA", "CUSA", [
        ("Delaware", "Blue Hens", "DEL"),
        ("Florida International", "Panthers", "FIU"),
        ("Jacksonville State", "Gamecocks", "JXST"),
        ("Kennesaw State", "Owls", "KENN"),
        ("Liberty", "Flames", "LIB"),
        ("Middle Tennessee", "Blue Raiders", "MTSU"),
        ("Missouri State", "Bears", "MOST"),
        ("New Mexico State", "Aggies", "NMSU"),
        ("Sam Houston", "Bearkats", "SHSU"),
        ("Western Kentucky", "Hilltoppers", "WKU"),
        ("Wake Forest", "Demon Deacons", "WAKE"),
        ("Troy", "Trojans", "TROY"),
    ]),
    ("American Athletic", "AAC", [
        ("Army", "Black Knights", "ARMY"),
        ("Charlotte", "49ers", "CLT"),
        ("East Carolina", "Pirates", "ECU"),
        ("Florida Atlantic", "Owls", "FAU"),
        ("Memphis", "Tigers", "MEM"),
        ("Navy", "Midshipmen", "NAVY"),
        ("North Texas", "Mean Green", "UNT"),
        ("Rice", "Owls", "RICE"),
        ("South Florida", "Bulls", "USF"),
        ("Temple", "Owls", "TEM"),
        ("Tulane", "Green Wave", "TULN"),
        ("Tulsa", "Golden Hurricane", "TLSA"),
    ]),
    ("Pac-12", "PAC", [
        ("Boise State", "Broncos", "BOIS"),
        ("Colorado State", "Rams", "CSU"),
        ("Fresno State", "Bulldogs", "FRES"),
        ("Oregon State", "Beavers", "ORST"),
        ("San Diego State", "Aztecs", "SDSU"),
        ("Texas State", "Bobcats", "TXST"),
        ("Utah State", "Aggies", "USU"),
        ("Washington State", "Cougars", "WSU"),
        ("UL Monroe", "Warhawks", "ULM"),
        ("Western Michigan", "Broncos", "WMU"),
    ]),
    ("FBS Independents", "IND", [
        ("Notre Dame", "Fighting Irish", "ND"),
        ("UConn", "Huskies", "CONN"),
    ]),
]


# Each school's real colors (CFBD's /teams/fbs, recorded 2026-09-20): the league uses them in place of its drawn ones.
REAL_COLORS: dict[str, tuple[str, str]] = {
    "Air Force": ("#003594", "#ffffff"),
    "Akron": ("#041e42", "#a89968"),
    "Alabama": ("#9e1b32", "#ffffff"),
    "App State": ("#000000", "#ffcd00"),
    "Arizona": ("#cc0033", "#003366"),
    "Arizona State": ("#ffc627", "#8c1d40"),
    "Arkansas": ("#a32136", "#ffffff"),
    "Arkansas State": ("#cc092f", "#000000"),
    "Army": ("#000000", "#d3bc8d"),
    "Auburn": ("#0c2340", "#f26522"),
    "BYU": ("#003da5", "#002e5d"),
    "Ball State": ("#ba0c2f", "#ffffff"),
    "Baylor": ("#154734", "#ffb81c"),
    "Boise State": ("#0033a0", "#d64309"),
    "Boston College": ("#8c2232", "#dbcca6"),
    "Bowling Green": ("#fd5000", "#4f2c1d"),
    "Buffalo": ("#005bbb", "#ffffff"),
    "California": ("#041e42", "#ffc72c"),
    "Central Michigan": ("#6a0032", "#ffc82e"),
    "Charlotte": ("#005035", "#a49665"),
    "Cincinnati": ("#000000", "#e00122"),
    "Clemson": ("#f56600", "#522d80"),
    "Coastal Carolina": ("#006f71", "#a27752"),
    "Colorado": ("#cfb87c", "#000000"),
    "Colorado State": ("#1e4d2b", "#c8c372"),
    "Delaware": ("#00539f", "#ffd200"),
    "Duke": ("#00539b", "#ffffff"),
    "East Carolina": ("#592a8a", "#fdc82f"),
    "Eastern Michigan": ("#046a38", "#ffffff"),
    "Florida": ("#0021a5", "#fa4616"),
    "Florida Atlantic": ("#003366", "#cc0000"),
    "Florida International": ("#091f3f", "#c3993f"),
    "Florida State": ("#782f40", "#ceb888"),
    "Fresno State": ("#c41230", "#13284c"),
    "Georgia": ("#ba0c2f", "#2c2a29"),
    "Georgia Southern": ("#041e42", "#ffffff"),
    "Georgia State": ("#0039a6", "#ffffff"),
    "Georgia Tech": ("#b3a369", "#ffffff"),
    "Hawai'i": ("#024731", "#000000"),
    "Houston": ("#c8102e", "#ffffff"),
    "Illinois": ("#ff5f05", "#13294b"),
    "Indiana": ("#990000", "#ffffff"),
    "Iowa": ("#000000", "#ffcd00"),
    "Iowa State": ("#c8102e", "#f1be48"),
    "Jacksonville State": ("#cc0000", "#000000"),
    "James Madison": ("#450084", "#cbb677"),
    "Kansas": ("#0051ba", "#e8000d"),
    "Kansas State": ("#512888", "#ffffff"),
    "Kennesaw State": ("#fdbb30", "#0b1315"),
    "Kent State": ("#002664", "#eaab00"),
    "Kentucky": ("#0033a0", "#ffffff"),
    "LSU": ("#461d7c", "#fdd023"),
    "Liberty": ("#0a254e", "#b72025"),
    "Louisiana": ("#ce181e", "#000000"),
    "Louisiana Tech": ("#003087", "#cb333b"),
    "Louisville": ("#c9001f", "#000000"),
    "Marshall": ("#00b140", "#000000"),
    "Maryland": ("#ce1126", "#ffffff"),
    "Massachusetts": ("#881c1c", "#ffffff"),
    "Memphis": ("#00498f", "#9c9ea1"),
    "Miami": ("#f47321", "#005030"),
    "Miami (OH)": ("#c41230", "#ffffff"),
    "Michigan": ("#00274c", "#ffcb05"),
    "Michigan State": ("#173f35", "#ffffff"),
    "Middle Tennessee": ("#036eb7", "#ffffff"),
    "Minnesota": ("#7a0019", "#ffcc33"),
    "Mississippi State": ("#5d1725", "#c1c6c8"),
    "Missouri": ("#f1b82d", "#000000"),
    "Missouri State": ("#5e0009", "#ffffff"),
    "NC State": ("#cc0000", "#ffffff"),
    "Navy": ("#00225b", "#b5a67c"),
    "Nebraska": ("#d00000", "#ffffff"),
    "Nevada": ("#041e42", "#8a8d8f"),
    "New Mexico": ("#ba0c2f", "#a7a8aa"),
    "New Mexico State": ("#8c0b42", "#ffffff"),
    "North Carolina": ("#7bafd4", "#13294b"),
    "North Dakota State": ("#00583d", "#ffc425"),
    "North Texas": ("#00853e", "#ffffff"),
    "Northern Illinois": ("#c8102e", "#000000"),
    "Northwestern": ("#582c83", "#ffffff"),
    "Notre Dame": ("#0c2340", "#c99700"),
    "Ohio": ("#024230", "#ffffff"),
    "Ohio State": ("#ba0c2f", "#a7b1b7"),
    "Oklahoma": ("#841617", "#ffffff"),
    "Oklahoma State": ("#fe5c00", "#000000"),
    "Old Dominion": ("#043657", "#98c5ea"),
    "Ole Miss": ("#13294b", "#cf142b"),
    "Oregon": ("#007030", "#fee11a"),
    "Oregon State": ("#dc4405", "#000000"),
    "Penn State": ("#001e44", "#ffffff"),
    "Pittsburgh": ("#003594", "#ffb81c"),
    "Purdue": ("#ceb888", "#000000"),
    "Rice": ("#00205b", "#c1c6c8"),
    "Rutgers": ("#ce0e2d", "#ffffff"),
    "SMU": ("#d70000", "#0033a1"),
    "Sacramento State": ("#00573c", "#cdb97d"),
    "Sam Houston": ("#f56423", "#ffffff"),
    "San Diego State": ("#a6192e", "#000000"),
    "San José State": ("#0055a2", "#e5a823"),
    "South Alabama": ("#00205b", "#bf0d3e"),
    "South Carolina": ("#73000a", "#000000"),
    "South Florida": ("#006747", "#cfc493"),
    "Southern Miss": ("#ffc72c", "#231f20"),
    "Stanford": ("#8c1515", "#ffffff"),
    "Syracuse": ("#f76900", "#000e54"),
    "TCU": ("#4d1979", "#ffffff"),
    "Temple": ("#a41e35", "#ffffff"),
    "Tennessee": ("#ff8200", "#ffffff"),
    "Texas": ("#bf5700", "#ffffff"),
    "Texas A&M": ("#500000", "#ffffff"),
    "Texas State": ("#501214", "#6a5638"),
    "Texas Tech": ("#c30020", "#000000"),
    "Toledo": ("#0b2240", "#ffcd00"),
    "Troy": ("#862633", "#b1b1b1"),
    "Tulane": ("#006747", "#418fde"),
    "Tulsa": ("#003595", "#d0b787"),
    "UCF": ("#000000", "#b4a169"),
    "UCLA": ("#2774ae", "#f2a900"),
    "UConn": ("#000e2f", "#ffffff"),
    "UL Monroe": ("#840029", "#fdb913"),
    "UNLV": ("#cf0a2c", "#cac8c8"),
    "USC": ("#990000", "#ffcc00"),
    "UTEP": ("#ff8200", "#041e42"),
    "Utah": ("#be0000", "#ffffff"),
    "Utah State": ("#0f2439", "#ffffff"),
    "Vanderbilt": ("#000000", "#cfae70"),
    "Virginia": ("#232d4b", "#f84c1e"),
    "Virginia Tech": ("#861f41", "#e87722"),
    "Wake Forest": ("#ceb888", "#2c2a29"),
    "Washington": ("#33006f", "#e8d3a2"),
    "Washington State": ("#a60f2d", "#4d4d4d"),
    "West Virginia": ("#eaaa00", "#002855"),
    "Western Kentucky": ("#c60c30", "#ffffff"),
    "Western Michigan": ("#532e1f", "#f1c500"),
    "Wisconsin": ("#a00000", "#ffffff"),
    "Wyoming": ("#492f24", "#ffc425"),
}

# The four big conferences are the "power" ones: stronger on average and favoured by the polls.
POWER_CONFERENCES = ("SEC", "Big Ten", "Big 12", "ACC")

# Each conference's home states, so venues and recruits land somewhere plausible.
CONFERENCE_STATES: dict[str, list[str]] = {
    "SEC": ["GA", "AL", "MS", "LA", "TN", "KY", "SC", "AR"],
    "Big Ten": ["WI", "MN", "IA", "IL", "IN", "OH", "MI", "PA"],
    "Big 12": ["TX", "OK", "KS", "NM", "AZ", "CO"],
    "ACC": ["ME", "MA", "CT", "NJ", "NY", "MD", "VA", "NC"],
    "Mountain West": ["CO", "WY", "MT", "ID", "UT", "NV"],
    "Sun Belt": ["FL", "GA", "SC", "AL", "LA"],
    "Mid-American": ["NE", "KS", "IA", "MO", "SD", "ND"],
    "Conference USA": ["TX", "AR", "MO", "TN", "KY", "WV"],
    "American Athletic": ["MI", "OH", "WI", "NY", "IN"],
    "Pac-12": ["OR", "WA", "CA", "VT", "NH"],
    "FBS Independents": ["IL", "OH"],
}

# Rough state centres for coordinates (lat, lon) and time zones. Recruits come from everywhere,
# weighted toward the football-rich states.
STATES: dict[str, tuple[float, float, str]] = {
    "AL": (32.8, -86.8, "America/Chicago"), "AR": (34.9, -92.4, "America/Chicago"),
    "AZ": (34.2, -111.6, "America/Phoenix"), "CA": (36.8, -119.4, "America/Los_Angeles"),
    "CO": (39.0, -105.5, "America/Denver"), "CT": (41.6, -72.7, "America/New_York"),
    "FL": (28.6, -82.4, "America/New_York"), "GA": (32.7, -83.4, "America/New_York"),
    "IA": (42.0, -93.5, "America/Chicago"), "ID": (44.1, -114.6, "America/Boise"),
    "IL": (40.0, -89.2, "America/Chicago"), "IN": (39.9, -86.3, "America/Indiana/Indianapolis"),
    "KS": (38.5, -98.4, "America/Chicago"), "KY": (37.5, -85.3, "America/New_York"),
    "LA": (31.1, -92.0, "America/Chicago"), "MA": (42.3, -71.8, "America/New_York"),
    "MD": (39.0, -76.8, "America/New_York"), "ME": (45.3, -69.2, "America/New_York"),
    "MI": (44.3, -85.4, "America/Detroit"), "MN": (46.3, -94.3, "America/Chicago"),
    "MO": (38.4, -92.5, "America/Chicago"), "MS": (32.7, -89.7, "America/Chicago"),
    "MT": (47.0, -109.6, "America/Denver"), "NC": (35.6, -79.4, "America/New_York"),
    "ND": (47.5, -100.5, "America/Chicago"), "NE": (41.5, -99.8, "America/Chicago"),
    "NH": (43.7, -71.6, "America/New_York"), "NJ": (40.2, -74.7, "America/New_York"),
    "NM": (34.4, -106.1, "America/Denver"), "NV": (39.3, -116.6, "America/Los_Angeles"),
    "NY": (42.9, -75.5, "America/New_York"), "OH": (40.3, -82.8, "America/New_York"),
    "OK": (35.6, -97.5, "America/Chicago"), "OR": (43.9, -120.6, "America/Los_Angeles"),
    "PA": (40.9, -77.8, "America/New_York"), "SC": (33.9, -80.9, "America/New_York"),
    "SD": (44.4, -100.2, "America/Chicago"), "TN": (35.9, -86.4, "America/Chicago"),
    "TX": (31.5, -99.3, "America/Chicago"), "UT": (39.3, -111.7, "America/Denver"),
    "VA": (37.5, -78.9, "America/New_York"), "VT": (44.1, -72.7, "America/New_York"),
    "WA": (47.4, -120.5, "America/Los_Angeles"), "WI": (44.6, -89.9, "America/Chicago"),
    "WV": (38.6, -80.6, "America/New_York"), "WY": (43.0, -107.6, "America/Denver"),
}
RECRUIT_STATE_WEIGHTS: dict[str, int] = {
    "TX": 14, "FL": 13, "GA": 10, "CA": 9, "AL": 5, "LA": 5, "OH": 5, "NC": 4, "PA": 4, "TN": 4,
    "MS": 3, "SC": 3, "VA": 3, "MI": 3, "IL": 3, "AZ": 2, "MD": 2, "NJ": 2, "OK": 2, "MO": 2,
    "KY": 2, "IN": 2, "WA": 2, "AR": 2, "CO": 1, "UT": 1, "MN": 1, "WI": 1, "NY": 1, "KS": 1,
    "IA": 1, "NE": 1, "OR": 1, "NV": 1, "CT": 1, "MA": 1, "WV": 1,
}

FIRST_NAMES = (
    "Aaron Adam Adrian Aiden Alex Andre Andrew Anthony Austin Bailey Ben Blake Brady Brandon Brian "
    "Brock Bryce Caleb Calvin Cameron Carson Carter Casey Chase Chris Cody Colby Cole Colin Connor "
    "Cooper Corey Dakota Dale Damon Daniel Dante Darius David Dean Derek Devin Dillon Dominic Drew "
    "Dylan Eli Elijah Eric Ethan Evan Felix Gabe Garrett Gavin Grant Grayson Hayden Henry Hudson "
    "Hunter Ian Isaac Isaiah Jack Jacob Jaden Jalen Jamal James Jared Jason Javon Jay Jayden Jeremiah "
    "Jesse Joel John Jonah Jordan Joseph Josh Julian Justin Kaden Kai Keegan Keith Kendall Kevin "
    "Kyle Lamar Landon Lane Leo Levi Liam Logan Lucas Luke Malik Marcus Mario Mason Matt Max Micah "
    "Miles Mitchell Nate Nathan Nick Noah Nolan Omar Owen Parker Patrick Paul Peyton Preston Quinn "
    "Reed Reggie Riley Rodney Roman Ryan Sam Sean Seth Shane Simon Spencer Stefan Terrell Theo Tony "
    "Travis Trent Trevor Tristan Troy Tyler Tyrell Victor Wade Walker Wes Will Xavier Zach Zion"
).split()

LAST_NAMES = (
    "Adams Allen Anderson Armstrong Bailey Baker Banks Barnes Bell Bennett Brooks Brown Bryant Burke "
    "Butler Campbell Carter Chambers Clark Coleman Collins Cook Cooper Cox Crawford Cruz Daniels Davis "
    "Dawson Dixon Douglas Duncan Edwards Ellis Evans Ferguson Fields Fisher Fleming Ford Foster Fowler "
    "Freeman Garcia Gardner Gibson Gordon Graham Grant Gray Green Griffin Hall Hamilton Harper Harris "
    "Hart Hawkins Hayes Henderson Henry Hicks Hill Holland Holmes Howard Hudson Hughes Hunt Jackson "
    "James Jenkins Johnson Jones Jordan Kelly Kennedy King Knight Lane Lawrence Lee Lewis Little Long "
    "Lowe Marshall Martin Mason Matthews Mendez Miller Mills Mitchell Moore Morgan Morris Murphy Myles "
    "Nelson Newton Nichols Norris Owens Palmer Parker Patterson Payne Perry Peters Phillips Pierce "
    "Porter Powell Price Ramirez Ray Reed Reese Reynolds Rice Richards Riley Rivera Roberts Robinson "
    "Rogers Ross Russell Sanders Scott Shaw Simmons Simpson Sims Smith Snyder Spencer Stephens Stewart "
    "Stone Sullivan Taylor Thomas Thompson Torres Tucker Turner Wade Walker Wallace Ward Warren "
    "Washington Watkins Watson Weaver Webb Wells West Wheeler White Williams Willis Wilson Wood Woods "
    "Wright Young"
).split()

TOWN_HEADS = (
    "Cedar Maple Oak Pine Willow Shady Pleasant Fair Green Rock Silver Mill Spring Clear Bright Elm "
    "Hickory Walnut Birch Ash Laurel Pebble Sandy Copper Stone Cotton Honey Clover Briar Fox Deer "
    "Hawk Bear Pigeon Turkey Possum Rabbit Beaver Otter Mossy Misty Windy Sunny Rocky Muddy"
).split()
TOWN_TAILS = (
    "ville|ton|burg| Springs| Creek| Falls| Grove| Hollow| Bluff| Ridge| Valley| Crossing| Point|"
    " Lake| Heights| Park| Corner| Mills| Station| Junction"
).split("|")

HIGH_SCHOOL_TAILS = ("High", "Central", "North", "South", "East", "West", "Academy", "Prep", "Christian", "Catholic")

STADIUM_FORMS = (
    "{school} Stadium", "{last} Field", "{last} Stadium", "The {mascot} Den", "{last} Field at {school} Stadium",
    "{school} Memorial Stadium", "{last} Bowl", "{school} Coliseum",
)

# Bowl names for the postseason (the playoff games use "College Football Playoff ..." names).
BOWLS = (
    "Gravy Train Bowl", "Snack Pack Bowl", "Leftovers Bowl", "Second Helping Bowl", "Potluck Bowl",
    "Casserole Classic", "Tailgate Bowl", "Pigskin Pie Bowl", "Corn Dog Bowl", "Nacho Bowl",
    "Breakfast Burrito Bowl", "Pancake Bowl", "Fry Basket Bowl", "Lemonade Stand Bowl",
    "Picnic Basket Bowl", "Crockpot Bowl", "Butter Bowl", "Chili Cook-Off Bowl", "Sweet Potato Bowl",
    "Wake Forest Bowl", "Mashed Potato Bowl", "Hot Sauce Bowl", "Biscuit Bowl", "Pickle Jar Bowl",
    "Shrimp Boil Bowl", "Pretzel Bowl", "Gumbo Bowl", "Cobbler Bowl", "Jambalaya Bowl", "Hush Bowl",
    "Kettle Bowl", "Marshmallow Bowl", "Drumstick Bowl", "Bake Sale Bowl", "Sundae Bowl",
)
PLAYOFF_SITES = ("Gravy Bowl", "Grits Bowl", "Casserole Bowl", "Pickle Bowl", "Muffin Bowl", "Pudding Bowl")

# Made-up TV networks for listings (the demo never names a real broadcaster).
NETWORKS = (
    "Couch Network", "Couch Network 2", "Snack Sports", "KCN", "Gravy+", "Big Bowl TV",
    "Tailgate Channel", "Sofa Sports", "Remote Control TV",
)
STREAMING = ("Gravy+",)

PROVIDERS = ("Pickle Book", "Gravy Odds")  # betting-line providers in /lines
