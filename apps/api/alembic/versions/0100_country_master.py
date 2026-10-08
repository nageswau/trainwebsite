"""upc-002 -- country master: ISO 3166-1 alpha-2 code, region, catalogue visibility, and every ISO country as an internal row.

Revision ID: 0100_country_master
Revises: 0099_tel_settings

docs/superpowers/specs/2026-10-08-upc-002-country-master-design.md §2 (U12; Q-06 regions answered 2026-10-08). Adds `countries.iso2`
(unique, nullable so ad-hoc test rows need no code), `region` (one of REGIONS) and `catalogue_visible` (default true: every existing row
is a catalogue row and stays public). Backfills the twelve catalogue slugs, prints any other existing row (left without a code), then
inserts each ISO country not yet present as an internal row (no catalogue text, catalogue_visible=false). A plain INSERT, so a duplicate
code fails loudly; an existing row that already holds an ISO row's slug fails before anything is inserted. 0001 builds a fresh database
from the current models, which already carry the columns and constraints, so those steps are guarded. REGIONS repeats
app.models.COUNTRY_REGIONS (test_upc_002_migration). downgrade() refuses while a university or scholarship uses an internal country.
"""

import re
import unicodedata

import sqlalchemy as sa

from alembic import op

revision = "0100_country_master"
down_revision = "0099_tel_settings"
branch_labels = None
depends_on = None

TABLE = "countries"
REGIONS = ("UK", "Europe", "North America", "Latin America & Caribbean", "Middle East", "Asia", "Oceania", "Africa", "Antarctica")
CHECKS = {
    "ck_countries_iso2": "iso2 ~ '^[A-Z]{2}$'",
    "ck_countries_region": "region IN (" + ", ".join(f"'{r}'" for r in REGIONS) + ")",
}
UNIQUE = "uq_countries_iso2"

# The catalogue rows of seed/countries.json, by slug.
CATALOGUE_SLUGS = {
    "germany": "DE", "united-kingdom": "GB", "canada": "CA", "australia": "AU", "usa": "US", "ireland": "IE",
    "new-zealand": "NZ", "france": "FR", "netherlands": "NL", "sweden": "SE", "dubai-uae": "AE", "singapore": "SG",
}
# A fresh database gets the placeholders under the catalogue's slugs, so the seed finds and fills them.
SLUG_OVERRIDES = {"US": "usa", "AE": "dubai-uae"}

_BY_REGION = {
    "UK": [("GB", "United Kingdom")],
    "Europe": [
        ("AD", "Andorra"), ("AL", "Albania"), ("AT", "Austria"), ("AX", "Åland Islands"), ("BA", "Bosnia and Herzegovina"),
        ("BE", "Belgium"), ("BG", "Bulgaria"), ("BY", "Belarus"), ("CH", "Switzerland"), ("CY", "Cyprus"), ("CZ", "Czechia"),
        ("DE", "Germany"), ("DK", "Denmark"), ("EE", "Estonia"), ("ES", "Spain"), ("FI", "Finland"), ("FO", "Faroe Islands"),
        ("FR", "France"), ("GG", "Guernsey"), ("GI", "Gibraltar"), ("GR", "Greece"), ("HR", "Croatia"), ("HU", "Hungary"),
        ("IE", "Ireland"), ("IM", "Isle of Man"), ("IS", "Iceland"), ("IT", "Italy"), ("JE", "Jersey"), ("LI", "Liechtenstein"),
        ("LT", "Lithuania"), ("LU", "Luxembourg"), ("LV", "Latvia"), ("MC", "Monaco"), ("MD", "Moldova"), ("ME", "Montenegro"),
        ("MK", "North Macedonia"), ("MT", "Malta"), ("NL", "Netherlands"), ("NO", "Norway"), ("PL", "Poland"), ("PT", "Portugal"),
        ("RO", "Romania"), ("RS", "Serbia"), ("RU", "Russia"), ("SE", "Sweden"), ("SI", "Slovenia"), ("SJ", "Svalbard and Jan Mayen"),
        ("SK", "Slovakia"), ("SM", "San Marino"), ("UA", "Ukraine"), ("VA", "Holy See"),
    ],
    "North America": [("US", "United States"), ("CA", "Canada"), ("GL", "Greenland"), ("BM", "Bermuda"), ("PM", "Saint Pierre and Miquelon")],
    "Latin America & Caribbean": [
        ("AG", "Antigua and Barbuda"), ("AI", "Anguilla"), ("AR", "Argentina"), ("AW", "Aruba"), ("BB", "Barbados"),
        ("BL", "Saint Barthélemy"), ("BO", "Bolivia"), ("BQ", "Bonaire, Sint Eustatius and Saba"), ("BR", "Brazil"), ("BS", "Bahamas"),
        ("BZ", "Belize"), ("CL", "Chile"), ("CO", "Colombia"), ("CR", "Costa Rica"), ("CU", "Cuba"), ("CW", "Curaçao"),
        ("DM", "Dominica"), ("DO", "Dominican Republic"), ("EC", "Ecuador"), ("FK", "Falkland Islands"), ("GD", "Grenada"),
        ("GF", "French Guiana"), ("GP", "Guadeloupe"), ("GT", "Guatemala"), ("GY", "Guyana"), ("HN", "Honduras"), ("HT", "Haiti"),
        ("JM", "Jamaica"), ("KN", "Saint Kitts and Nevis"), ("KY", "Cayman Islands"), ("LC", "Saint Lucia"),
        ("MF", "Saint Martin (French part)"), ("MQ", "Martinique"), ("MS", "Montserrat"), ("MX", "Mexico"), ("NI", "Nicaragua"),
        ("PA", "Panama"), ("PE", "Peru"), ("PR", "Puerto Rico"), ("PY", "Paraguay"), ("SR", "Suriname"), ("SV", "El Salvador"),
        ("SX", "Sint Maarten (Dutch part)"), ("TC", "Turks and Caicos Islands"), ("TT", "Trinidad and Tobago"), ("UY", "Uruguay"),
        ("VC", "Saint Vincent and the Grenadines"), ("VE", "Venezuela"), ("VG", "British Virgin Islands"), ("VI", "U.S. Virgin Islands"),
    ],
    "Middle East": [
        ("AE", "United Arab Emirates"), ("BH", "Bahrain"), ("IL", "Israel"), ("IQ", "Iraq"), ("IR", "Iran"), ("JO", "Jordan"),
        ("KW", "Kuwait"), ("LB", "Lebanon"), ("OM", "Oman"), ("PS", "Palestine"), ("QA", "Qatar"), ("SA", "Saudi Arabia"),
        ("SY", "Syria"), ("TR", "Türkiye"), ("YE", "Yemen"),
    ],
    "Asia": [
        ("AF", "Afghanistan"), ("AM", "Armenia"), ("AZ", "Azerbaijan"), ("BD", "Bangladesh"), ("BN", "Brunei"), ("BT", "Bhutan"),
        ("CN", "China"), ("GE", "Georgia"), ("HK", "Hong Kong"), ("ID", "Indonesia"), ("IN", "India"), ("JP", "Japan"),
        ("KG", "Kyrgyzstan"), ("KH", "Cambodia"), ("KP", "North Korea"), ("KR", "South Korea"), ("KZ", "Kazakhstan"), ("LA", "Laos"),
        ("LK", "Sri Lanka"), ("MM", "Myanmar"), ("MN", "Mongolia"), ("MO", "Macao"), ("MV", "Maldives"), ("MY", "Malaysia"),
        ("NP", "Nepal"), ("PH", "Philippines"), ("PK", "Pakistan"), ("SG", "Singapore"), ("TH", "Thailand"), ("TJ", "Tajikistan"),
        ("TL", "Timor-Leste"), ("TM", "Turkmenistan"), ("TW", "Taiwan"), ("UZ", "Uzbekistan"), ("VN", "Vietnam"),
    ],
    "Oceania": [
        ("AS", "American Samoa"), ("AU", "Australia"), ("CC", "Cocos (Keeling) Islands"), ("CK", "Cook Islands"),
        ("CX", "Christmas Island"), ("FJ", "Fiji"), ("FM", "Micronesia"), ("GU", "Guam"), ("KI", "Kiribati"), ("MH", "Marshall Islands"),
        ("MP", "Northern Mariana Islands"), ("NC", "New Caledonia"), ("NF", "Norfolk Island"), ("NR", "Nauru"), ("NU", "Niue"),
        ("NZ", "New Zealand"), ("PF", "French Polynesia"), ("PG", "Papua New Guinea"), ("PN", "Pitcairn"), ("PW", "Palau"),
        ("SB", "Solomon Islands"), ("TK", "Tokelau"), ("TO", "Tonga"), ("TV", "Tuvalu"), ("UM", "United States Minor Outlying Islands"),
        ("VU", "Vanuatu"), ("WF", "Wallis and Futuna"), ("WS", "Samoa"),
    ],
    "Africa": [
        ("AO", "Angola"), ("BF", "Burkina Faso"), ("BI", "Burundi"), ("BJ", "Benin"), ("BW", "Botswana"),
        ("CD", "Democratic Republic of the Congo"), ("CF", "Central African Republic"), ("CG", "Republic of the Congo"),
        ("CI", "Côte d'Ivoire"), ("CM", "Cameroon"), ("CV", "Cabo Verde"), ("DJ", "Djibouti"), ("DZ", "Algeria"), ("EG", "Egypt"),
        ("EH", "Western Sahara"), ("ER", "Eritrea"), ("ET", "Ethiopia"), ("GA", "Gabon"), ("GH", "Ghana"), ("GM", "Gambia"),
        ("GN", "Guinea"), ("GQ", "Equatorial Guinea"), ("GW", "Guinea-Bissau"), ("IO", "British Indian Ocean Territory"), ("KE", "Kenya"),
        ("KM", "Comoros"), ("LR", "Liberia"), ("LS", "Lesotho"), ("LY", "Libya"), ("MA", "Morocco"), ("MG", "Madagascar"),
        ("ML", "Mali"), ("MR", "Mauritania"), ("MU", "Mauritius"), ("MW", "Malawi"), ("MZ", "Mozambique"), ("NA", "Namibia"),
        ("NE", "Niger"), ("NG", "Nigeria"), ("RE", "Réunion"), ("RW", "Rwanda"), ("SC", "Seychelles"), ("SD", "Sudan"),
        ("SH", "Saint Helena, Ascension and Tristan da Cunha"), ("SL", "Sierra Leone"), ("SN", "Senegal"), ("SO", "Somalia"),
        ("SS", "South Sudan"), ("ST", "Sao Tome and Principe"), ("SZ", "Eswatini"), ("TD", "Chad"), ("TG", "Togo"), ("TN", "Tunisia"),
        ("TZ", "Tanzania"), ("UG", "Uganda"), ("YT", "Mayotte"), ("ZA", "South Africa"), ("ZM", "Zambia"), ("ZW", "Zimbabwe"),
    ],
    "Antarctica": [
        ("AQ", "Antarctica"), ("BV", "Bouvet Island"), ("GS", "South Georgia and the South Sandwich Islands"),
        ("HM", "Heard Island and McDonald Islands"), ("TF", "French Southern Territories"),
    ],
}
ISO_COUNTRIES = tuple((code, name, region) for region, rows in _BY_REGION.items() for code, name in rows)


def slug_for(code: str, name: str) -> str:
    if code in SLUG_OVERRIDES:
        return SLUG_OVERRIDES[code]
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def upgrade() -> None:
    inspector = _inspector()
    columns = set() if inspector is None else {c["name"] for c in inspector.get_columns(TABLE)}
    if "iso2" not in columns:
        op.add_column(TABLE, sa.Column("iso2", sa.String(2), nullable=True))
    if "region" not in columns:
        op.add_column(TABLE, sa.Column("region", sa.String(40), nullable=True))
    if "catalogue_visible" not in columns:
        op.add_column(TABLE, sa.Column("catalogue_visible", sa.Boolean(), nullable=False, server_default=sa.text("true")))

    region_of = {code: region for code, _, region in ISO_COUNTRIES}
    for slug, code in CATALOGUE_SLUGS.items():
        op.execute(sa.text(f"UPDATE {TABLE} SET iso2 = :code, region = :region WHERE slug = :slug AND iso2 IS NULL")
                   .bindparams(code=code, region=region_of[code], slug=slug))

    present: set[str] = set()
    if inspector is not None:
        bind = op.get_bind()
        rows = bind.execute(sa.text(f"SELECT slug, iso2 FROM {TABLE}")).all()
        present = {iso2 for _, iso2 in rows if iso2}
        unmapped = sorted(slug for slug, iso2 in rows if not iso2)
        if unmapped:
            print(f"0100_country_master: {len(unmapped)} existing row(s) have no ISO code and stay as they are: {', '.join(unmapped)}")
        taken = {slug for slug, iso2 in rows if not iso2}
        clashes = sorted(slug_for(code, name) for code, name, _ in ISO_COUNTRIES if code not in present and slug_for(code, name) in taken)
        if clashes:
            raise RuntimeError(f"0100_country_master: existing country row(s) already use the slug of an ISO country: {', '.join(clashes)}. "
                               "Give each its ISO code (or rename it) deliberately, then upgrade again.")

    for code, name, region in ISO_COUNTRIES:
        if code in present:
            continue
        op.execute(sa.text(
            f"INSERT INTO {TABLE} (id, slug, name, iso2, region, catalogue_visible, overview, tuition, living_expenses, visa_process, "
            "work_opportunities, post_study_work, pr_opportunities, faq) "
            "VALUES (gen_random_uuid(), :slug, :name, :code, :region, false, '', '', '', '[]', '', '', '', '[]')"
        ).bindparams(slug=slug_for(code, name), name=name, code=code, region=region))

    constraints = set() if inspector is None else {c["name"] for c in inspector.get_unique_constraints(TABLE)} | {
        c["name"] for c in inspector.get_check_constraints(TABLE)}
    if UNIQUE not in constraints:
        op.create_unique_constraint(UNIQUE, TABLE, ["iso2"])
    for name, sql in CHECKS.items():
        if name not in constraints:
            op.create_check_constraint(name, TABLE, sql)


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        internal = f"SELECT id FROM {TABLE} WHERE NOT catalogue_visible"
        if bind.execute(sa.text(f"SELECT 1 FROM universities WHERE country_id IN ({internal}) UNION ALL "
                                f"SELECT 1 FROM scholarships WHERE country_id IN ({internal}) LIMIT 1")).first():
            raise RuntimeError("Cannot downgrade 0100_country_master: a university or scholarship uses an internal country. Move it deliberately first.")
    op.execute(sa.text(f"DELETE FROM {TABLE} WHERE NOT catalogue_visible"))
    for name in CHECKS:
        op.drop_constraint(name, TABLE, type_="check")
    op.drop_constraint(UNIQUE, TABLE, type_="unique")
    op.drop_column(TABLE, "catalogue_visible")
    op.drop_column(TABLE, "region")
    op.drop_column(TABLE, "iso2")
