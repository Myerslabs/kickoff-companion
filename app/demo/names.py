"""Word lists for the made-up league. Every school, mascot, conference, bowl and network here is
invented (checked against the FBS list in tests when the private recordings are present). Player
and coach names are common first and last names put together at random; towns are generic."""

from __future__ import annotations

# The demo's own team: the one the app follows in demo mode and in the tests.
OUR_SCHOOL = "Swampwater Tech"

# (conference, short label, [(school, mascot, abbreviation), ...]). Four conferences of 16, five
# of 12, one of 10, and two independents: 136 teams, the size of FBS.
CONFERENCES: list[tuple[str, str, list[tuple[str, str, str]]]] = [
    ("Biscuit Belt", "BBC", [
        ("Swampwater Tech", "Mudpuppies", "SWT"),
        ("Gravy Boat State", "Ladles", "GBS"),
        ("Possum Holler", "Thunder Possums", "POSS"),
        ("Catfish Bend", "Whiskers", "CATB"),
        ("Okra Valley", "Pods", "OKRA"),
        ("Magnolia Flats", "Petals", "MAGF"),
        ("Hushpuppy State", "Fryers", "HUSH"),
        ("Bayou Bottom", "Crawdads", "BAYB"),
        ("Peach Fuzz Tech", "Fuzzies", "PFT"),
        ("Grits Junction", "Spoons", "GRIT"),
        ("Sweet Tea State", "Sippers", "STS"),
        ("Lower Kudzu", "Vines", "KUDZ"),
        ("Moonpie Mountain", "Marshmallows", "MOON"),
        ("Bluegrass Bottoms", "Banjos", "BLUE"),
        ("Red Clay", "Rattlers", "RCLY"),
        ("Front Porch State", "Rockers", "PORC"),
    ]),
    ("Gravy Ten", "G10", [
        ("Cheese Curd Tech", "Squeakers", "CURD"),
        ("Hotdish State", "Casseroles", "HOT"),
        ("Lake Wobble", "Walleyes", "WOBL"),
        ("Cornfield Central", "Stalks", "CORN"),
        ("Brat Haven", "Mustards", "BRAT"),
        ("Tater Tot Tech", "Tots", "TOT"),
        ("Snowdrift State", "Plowmen", "SNOW"),
        ("Frozen Custard", "Cones", "CUST"),
        ("Prairie Dog Plains", "Diggers", "PDOG"),
        ("Ice Fishing State", "Augers", "AUGR"),
        ("Buttered Corn", "Kernels", "KERN"),
        ("Steelmill Polytech", "Ingots", "INGT"),
        ("Hayloft", "Haybalers", "HAY"),
        ("Pierogi Point", "Dumplings", "PIER"),
        ("Rust Belt", "Rivets", "RVT"),
        ("Silo City", "Grainers", "SILO"),
    ]),
    ("Big Casserole", "BIGC", [
        ("Brisket State", "Smokers", "BRSK"),
        ("Tumbleweed Tech", "Rollers", "TUMB"),
        ("Armadillo Flats", "Shells", "ARMA"),
        ("Jackrabbit Junction", "Hares", "JACK"),
        ("Chili Bowl", "Peppers", "CHIL"),
        ("Dust Devil State", "Twisters", "DUST"),
        ("Cactus Gulch", "Prickles", "CACT"),
        ("Prairie Fire", "Embers", "EMBR"),
        ("Oil Patch", "Roughnecks", "OILP"),
        ("Rodeo State", "Wranglers", "RODO"),
        ("Tornado Alley", "Funnels", "TORN"),
        ("Sagebrush", "Sages", "SAGE"),
        ("Mesquite Tech", "Grillers", "MESQ"),
        ("Pecan Pie", "Pralines", "PCAN"),
        ("Buffalo Wing State", "Flats", "WING"),
        ("Saddle Sore", "Saddlebags", "SADL"),
    ]),
    ("Atlantic Pickle", "APC", [
        ("Clam Chowder", "Clams", "CLAM"),
        ("Lighthouse Point", "Beacons", "BCN"),
        ("Lobster Pot Tech", "Claws", "LOBS"),
        ("Boardwalk State", "Taffies", "TAFY"),
        ("Seagull Shores", "Squawkers", "GULL"),
        ("Cranberry Bog", "Berries", "BOG"),
        ("Old Harbor", "Anchors", "ANCH"),
        ("Fogbank", "Foghorns", "FOG"),
        ("Maple Syrup State", "Drips", "SYRP"),
        ("Turnpike Tech", "Tollbooths", "TOLL"),
        ("Brownstone", "Pigeons", "PIGN"),
        ("Crab Cake", "Pinchers", "CRAB"),
        ("Soft Pretzel State", "Twists", "PRTZ"),
        ("Bagel Bay", "Schmears", "BAGL"),
        ("Pine Barrens", "Pinecones", "PINE"),
        ("Cobblestone", "Colonials", "COBL"),
    ]),
    ("Mountain Muffin", "MMC", [
        ("Avalanche Valley", "Snowballs", "AVAL"),
        ("Bigfoot State", "Sasquatches", "BIGF"),
        ("Pinecone Peak", "Pikas", "PIKA"),
        ("Geyser Tech", "Steamers", "GYSR"),
        ("Nugget Gulch", "Panners", "NUGT"),
        ("Switchback State", "Hikers", "HIKE"),
        ("Trout Creek", "Tailwaters", "TROT"),
        ("Moose Lake", "Antlers", "MOOS"),
        ("Thunder Basin", "Boomers", "BOOM"),
        ("Elk Ridge", "Buglers", "ELK"),
        ("Ski Lift State", "Gondolas", "SKI"),
        ("Rimrock", "Ravens", "RIM"),
    ]),
    ("Sun Pudding", "SPC", [
        ("Sandspur State", "Burrs", "SAND"),
        ("Flamingo Flats", "Flamingos", "FLMG"),
        ("Pelican Point", "Pouches", "PELI"),
        ("Key Lime", "Limes", "LIME"),
        ("Seashell Tech", "Conchs", "CONC"),
        ("Mangrove", "Mudskippers", "MANG"),
        ("Coconut Coast", "Husks", "COCO"),
        ("Sunburn State", "Lobsters", "BURN"),
        ("Palmetto Bug Tech", "Skitters", "BUGT"),
        ("Spanish Moss", "Mossbacks", "MOSS"),
        ("Brackish Bay", "Tadpoles", "BRAK"),
        ("Sweetgrass", "Weavers", "SWGR"),
    ]),
    ("Mid-Prairie Pie", "MPP", [
        ("Rhubarb State", "Stalkers", "RHUB"),
        ("Pumpkin Patch", "Gourds", "GOUR"),
        ("Apple Orchard", "Cores", "CORE"),
        ("Butter Churn", "Churners", "CHRN"),
        ("Tractor Pull Tech", "Torque", "TORQ"),
        ("Meadowlark Meadows", "Larks", "LARK"),
        ("Holstein Heights", "Heifers", "HOLS"),
        ("Windmill State", "Blades", "WIND"),
        ("Grain Elevator", "Lifts", "GRAN"),
        ("Pothole Plains", "Puddles", "PUDL"),
        ("County Fair", "Ribbons", "FAIR"),
        ("Sweet Corn State", "Cobs", "COB"),
    ]),
    ("Cornbread USA", "CBU", [
        ("Kettle Corn", "Poppers", "POP"),
        ("Skillet State", "Irons", "SKIL"),
        ("Molasses Flats", "Sorghums", "MOLA"),
        ("Bottle Rocket Tech", "Fuses", "FUSE"),
        ("Jalopy Junction", "Junkers", "JALO"),
        ("Pickup Truck State", "Tailgaters", "TAIL"),
        ("Honky Tonk", "Two-Steppers", "HONK"),
        ("Bass Boat", "Lunkers", "LUNK"),
        ("Dollar Store State", "Bargains", "BARG"),
        ("Waffle Iron", "Waffles", "WAFL"),
        ("Funnel Cake", "Swirls", "SWRL"),
        ("Mud Bog", "Mudders", "MUDB"),
    ]),
    ("Lakeshore Lemonade", "LLC", [
        ("Dune Buggy State", "Buggies", "DUNE"),
        ("Lake Effect", "Flurries", "FLUR"),
        ("Driftwood", "Drifters", "DRFT"),
        ("Cherry Pit", "Spitters", "PIT"),
        ("Snowmobile Tech", "Sleds", "SLED"),
        ("Smelt Run", "Smelts", "SMLT"),
        ("Loon Lake", "Loons", "LOON"),
        ("Ferry Boat", "Ferrymen", "FERY"),
        ("Fudge Island", "Fudgies", "FUDG"),
        ("Perch Point", "Perchers", "PRCH"),
        ("Iron Ore Tech", "Taconites", "ORE"),
        ("Pasty State", "Crimpers", "PSTY"),
    ]),
    ("Pancake Athletic", "PAC", [
        ("Flapjack State", "Flippers", "FLAP"),
        ("Short Stack Tech", "Stackers", "STAK"),
        ("Silver Dollar", "Griddles", "GRID"),
        ("Hash Brown", "Spuds", "SPUD"),
        ("Blue Plate", "Specials", "BPLT"),
        ("Diner Tech", "Cooks", "DINR"),
        ("Sunny Side", "Yolks", "YOLK"),
        ("Coffee Pot State", "Percolators", "PERC"),
        ("Bacon Strip", "Sizzlers", "BACN"),
        ("Toast Point", "Crusts", "TOST"),
    ]),
    ("FBS Independents", "IND", [
        ("Okapi Institute", "Okapis", "OKPI"),
        ("Zeppelin", "Blimps", "ZEPP"),
    ]),
]

# The four big conferences are the "power" ones: stronger on average and favoured by the polls.
POWER_CONFERENCES = ("Biscuit Belt", "Gravy Ten", "Big Casserole", "Atlantic Pickle")

# Each conference's home states, so venues and recruits land somewhere plausible.
CONFERENCE_STATES: dict[str, list[str]] = {
    "Biscuit Belt": ["GA", "AL", "MS", "LA", "TN", "KY", "SC", "AR"],
    "Gravy Ten": ["WI", "MN", "IA", "IL", "IN", "OH", "MI", "PA"],
    "Big Casserole": ["TX", "OK", "KS", "NM", "AZ", "CO"],
    "Atlantic Pickle": ["ME", "MA", "CT", "NJ", "NY", "MD", "VA", "NC"],
    "Mountain Muffin": ["CO", "WY", "MT", "ID", "UT", "NV"],
    "Sun Pudding": ["FL", "GA", "SC", "AL", "LA"],
    "Mid-Prairie Pie": ["NE", "KS", "IA", "MO", "SD", "ND"],
    "Cornbread USA": ["TX", "AR", "MO", "TN", "KY", "WV"],
    "Lakeshore Lemonade": ["MI", "OH", "WI", "NY", "IN"],
    "Pancake Athletic": ["OR", "WA", "CA", "VT", "NH"],
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
    "Funnel Cake Bowl", "Mashed Potato Bowl", "Hot Sauce Bowl", "Biscuit Bowl", "Pickle Jar Bowl",
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
