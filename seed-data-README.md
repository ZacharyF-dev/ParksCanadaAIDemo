# Parks Canada demo — seed data

`parks-canada-seed-data.json` contains everything needed to populate the
backend booking database for the demo. Load it directly, or convert to SQL
inserts matching whatever schema the coding agent builds from
`parks-canada-mcp-demo-spec.md`.

## What's real vs. made up

- **`parks` (49 entries) — real.** Pulled from Wikipedia's "List of national
  parks of Canada": every current national park and national park reserve,
  with real province, establishment year, area, and natural region. Proposed
  parks, abolished parks, national marine conservation areas, and the one
  national landmark were left out to keep this focused on bookable land-based
  parks. Descriptions are short original one-liners, not copied text.

- **`campgrounds`, `sites`, `accommodations` — entirely fictional.**
  Real campgrounds/site numbers/prices were not scraped. Ten well-known,
  camping-heavy parks were picked and given 2 invented campgrounds each:

  Banff, Jasper, Kootenay, Yoho, Waterton Lakes, Pacific Rim,
  Prince Edward Island, Cape Breton Highlands, Riding Mountain, Gros Morne

  Each campground has 4–6 invented sites (mix of serviced/unserviced/
  pull-through/walk-in, with randomized hookups, equipment limits, pet/
  accessibility flags, and pricing) and usually one invented roofed
  accommodation type (oTENTik/yurt/cabin/microcube) with its own amenities
  and pricing.

  The other 39 parks exist as `park` records only — no campgrounds seeded.
  That's intentional: many (e.g. Quttinirpaaq, Auyuittuq, Wapusk) don't
  realistically have reservable frontcountry campsites, and it keeps the
  demo dataset a manageable size. More campgrounds can be added to the same
  JSON shape later if a bigger demo is needed.

## Shape

```
{
  "parks": [ { id, name, province, park_type, established, area_km2, natural_region, description } ],
  "campgrounds": [ { id, park_id, name, description, operating_season_start, operating_season_end, num_loops } ],
  "sites": [ { id, campground_id, site_number, site_type, max_party_size, max_vehicles,
               is_accessible, is_pet_friendly, equipment_allowed, max_equipment_length_ft,
               electrical_hookup, water_hookup, sewer_hookup, price_per_night_cad } ],
  "accommodations": [ { id, campground_id, park_id, type, name, sleeps_min, sleeps_max,
                         amenities, is_pet_friendly, is_accessible, price_per_night_cad, num_units } ]
}
```

Note: this seed data does not include per-night `Availability` rows (see the
main spec's schema) — the coding agent should generate those programmatically
(e.g. mark every site available for the campground's operating season, then
randomly book out ~20–30% of nights so search results look realistic).
