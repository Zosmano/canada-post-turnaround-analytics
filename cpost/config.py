"""Paths and every business assumption in one place.

Values marked ASSUMPTION are public-domain approximations or modelling choices. Replace
them with Canada Post internal figures when available; every downstream number updates.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "outputs"

# Statistics Canada 2021 Census Profile downloads (left untouched; read directly from the zips)
FSA_ZIP = ROOT / "No_CI_File_ for_ Analysi_98-401-X2021013_eng_CSV.zip"       # FSAs, all characteristics
FSA_CI_ZIP = ROOT / "File_for_Analysis_98-401-X2021013CI_eng_CSV.zip"          # FSAs, 25% sample with 95% CIs
CMA_CI_ZIP = ROOT / "File_for_Analysis2_98-401-X2021003CI_eng_CSV.zip"         # CMAs/CAs/tracts with 95% CIs

# --- Delivery cost model (annual cost per delivery point, CAD) ---------------------------
# Door and CMB: Canada Post 2025 Annual Report ("Aligning our network"), $284 vs $162 per address/yr.
COST_PER_POINT = {
    "door": 284.0,        # letter carrier walks to each door
    "cmb": 162.0,         # community mailbox (CMB)
    "lobby": 137.0,       # ASSUMPTION: apartment lobby lock-box
    "rural": 205.0,       # ASSUMPTION: rural roadside / rural CMB / PO box mix
}
# Government estimate for converting ~4M addresses, used as a sanity check on the model total
PUBLISHED_ANNUAL_SAVINGS = 400_000_000
CMB_CAPEX_PER_POINT = 180.0   # ASSUMPTION: one-time CMB unit, pad and install, per compartment (2026 $)

# Which door-eligible points (letter-carrier houses and duplex flats) are still door-to-door.
# CMBs became the standard for new subdivisions from the mid-1980s, so relative propensity
# falls with construction period; one scale factor is calibrated so the national total matches
# the ~4 million door-to-door addresses (Canada Post Q2 2026 report).
DOOR_PROPENSITY = {"pre1981": 1.0, "1981_1990": 0.35, "post1990": 0.03}
NATIONAL_DOOR_POINTS_TARGET = 4_000_000

# Accommodation: ~18,000 households use the Delivery Accommodation Program today (Q2 2026 report).
# That rate, among households already on centralized delivery, is applied to converted points and
# scaled by each FSA's share of maintainers aged 75+. ASSUMPTION: uplift for newly converted areas.
ACCOMMODATION_PROGRAM_HOUSEHOLDS = 18_000
ACCOMMODATION_UPLIFT = 1.0

# Canada Post 2026 Second Quarter Financial Report (period ended July 4, 2026)
Q2_2026 = {
    "segment_loss_before_tax_q2": 277e6, "segment_loss_before_tax_h1": 482e6,
    "group_loss_before_tax_h1": 439e6, "segment_cumulative_loss_before_tax_since_2018": 5.9e9,
    "funding_received_total": 1.369e9, "funding_approved_remaining": 673e6,
    "parcel_revenue_q2": 574e6, "parcel_revenue_growth_q2": 0.207, "parcel_volume_growth_q2": 0.156,
    "transaction_mail_revenue_growth_q2": -0.091,
    "conversion_wave_late_2026": {"addresses": 136_000, "communities": 13},
    "conversion_wave_2027": {"addresses": 485_000, "communities": 37},
    "accommodation_households": 18_000,
}

CONVERSION_WAVES = 3

# --- Route optimizer -------------------------------------------------------------------
WALK_SPEED_KMH = 4.5
DRIVE_SPEED_KMH = 25.0          # residential average including intersections
ROAD_CIRCUITY = 1.3             # ASSUMPTION: road distance / straight line for real addresses (no road file yet)
SERVICE_SEC = {"door": 14, "lobby_base": 60, "lobby_per_unit": 3, "cmb_base": 45, "cmb_per_unit": 4}
ROUTE_MAX_HOURS = {"walk": 4.5, "drive": 6.5}   # ASSUMPTION: delivery time inside a shift
CMB_SITE_CAPACITY = 48          # ASSUMPTION: three 16-compartment units per site
CMB_MAX_WALK_M = 250            # ASSUMPTION: max street distance from a home to its CMB
LOADED_LABOUR_COST_PER_HOUR = 48.0   # ASSUMPTION: wage plus benefits
VEHICLE_COST_PER_KM = 0.75           # ASSUMPTION
WORKING_DAYS_PER_YEAR = 250

# --- Churn model -------------------------------------------------------------------------
CHURN_SEED = 42
N_BUSINESS_CUSTOMERS = 8000
SAVE_RATE = {"service_recovery": 0.35, "price_retention_offer": 0.30,
             "reliability_guarantee": 0.40, "account_review": 0.20, "integration_support": 0.30}
INTERVENTION_COST = {"service_recovery": 150, "price_retention_offer": 600,
                     "reliability_guarantee": 400, "account_review": 120, "integration_support": 350}

PROVINCE_BY_LETTER = {
    "A": "NL", "B": "NS", "C": "PE", "E": "NB", "G": "QC", "H": "QC", "J": "QC",
    "K": "ON", "L": "ON", "M": "ON", "N": "ON", "P": "ON", "R": "MB", "S": "SK",
    "T": "AB", "V": "BC", "X": "NT/NU", "Y": "YT",
}
