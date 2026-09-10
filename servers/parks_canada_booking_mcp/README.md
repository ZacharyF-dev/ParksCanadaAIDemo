# Parks Canada Booking MCP Demo — Build Spec

## Context
Demo of an AI agent booking a Parks Canada stay via MCP. Modeled on the real
Parks Canada Reservation Service (reservation.pc.gc.ca) and its public
documentation (parks.canada.ca reservation/camping guides). This is a
**simplified clone for demo purposes**, not a production system — see
"Out of scope" at the end.

Three components:
1. **MCP Server** — tools an AI agent calls to search and book
2. **Backend booking database** — API + persistence backing the MCP server and frontend
3. **Frontend** — simple demo website showing the same flow a human would use, so we can demo both "AI books it" and "human books it" against the same data

---

## 1. Domain model / database schema

Based on real site structure, model these entities:

- **Park** (id, name, province, type: national_park / national_historic_site / marine_conservation_area, timezone)
- **Campground** (id, park_id, name, description, operating_season_start, operating_season_end, has_map/loops)
- **Loop** (id, campground_id, name) — optional, campgrounds are organized into loops (e.g. "A-Loop")
- **Site** (id, campground_id, loop_id, site_number, site_type: serviced / unserviced / pull-through / walk-in, max_party_size, max_vehicles, is_accessible, is_pet_friendly, hookups: electrical/water/sewer, equipment_types_allowed: tent/RV/trailer + max length)
- **Accommodation** (id, park_id or campground_id, type: oTENTik / yurt / cabin / microcube / oasis / tipi, sleeps_min, sleeps_max, amenities: list, has_woodstove, etc.) — roofed accommodations are modeled separately from bare sites since their attributes differ
- **Availability** (site_id or accommodation_id, date, is_available, price) — one row per unit per night; this is what search/calendar queries hit
- **User/Account** (id, name, email, phone) — simplified stand-in for GCKey/social sign-in
- **Reservation** (id, user_id, site_id or accommodation_id, arrival_date, departure_date, party_size, equipment_type, status: pending/confirmed/cancelled, total_price, created_at)
- **ReservationNight** (reservation_id, date, site_id) — supports "split your stay across sites" (different site per night under one reservation)
- **AvailabilityNotification** (id, user_id, search_criteria as JSON, created_at, fulfilled_at) — optional stretch feature

## 2. Backend API endpoints (what the MCP server and frontend both call)

- `GET /parks` — list/search parks (by name, province, type)
- `GET /parks/{id}/campgrounds`
- `GET /campgrounds/{id}` — details + loops + map info
- `GET /availability?location=&arrival=&departure=&party_size=&equipment_type=&filters=` — core search; returns matching sites/accommodations with per-night availability and price
- `GET /sites/{id}` — site detail
- `GET /sites/{id}/calendar?month=` — monthly availability calendar for one site
- `GET /accommodations/{id}` — roofed accommodation detail
- `POST /reservations` — create a reservation (site/accommodation, dates, party size, user info)
- `GET /reservations/{id}` — reservation detail/confirmation
- `GET /users/{id}/reservations` — reservation history
- `PATCH /reservations/{id}` — modify dates/cancel
- `DELETE /reservations/{id}` — cancel
- (stretch) `POST /notifications` — create an availability notification

## 3. MCP Server tools (agent-facing)

Map directly to the backend, but phrased as agent actions:

- `search_parks(query)` — find a park/site by name or region
- `search_availability(location, arrival_date, departure_date, party_size, equipment_type, filters?)` — the core tool; equipment_type should include tent / RV / trailer / roofed (oTENTik etc.); filters should support electrical hookup, pet-friendly, accessible
- `get_site_details(site_id)`
- `get_site_calendar(site_id, month)` — for "can't find your dates" fallback flow
- `create_reservation(user_id, site_id, arrival_date, departure_date, party_size)`
- `get_reservation(reservation_id)`
- `cancel_reservation(reservation_id)`
- `list_user_reservations(user_id)`
- (stretch) `create_availability_notification(user_id, search_criteria)`

Design note: give `search_availability` a response shape that's easy for an LLM to reason over (flat list of {site_id, name, type, price, available: true/false per night}) rather than mimicking the real site's calendar-grid UI.

## 4. Frontend (simple demo site)

Minimum pages to demonstrate the flow end to end:

1. **Search page** — park/location picker, arrival/departure date pickers, party size, equipment type, filter checkboxes (electrical, pet-friendly, accessible) — mirrors real search criteria
2. **Results page** — list or simple grid of matching sites/accommodations with price and availability, basic filtering
3. **Site detail page** — description, amenities, small availability calendar, "Book" button
4. **Checkout / reservation form** — party size, dates confirm, simple user info form (name/email — skip real auth)
5. **Confirmation page** — reservation number, dates, site, summary
6. **My Reservations page** — list existing reservations, allow cancel (simple account concept, no real login required for the demo)
7. **(Nice to have) Agent chat panel** — a simple chat box on the same frontend that talks to the MCP server, so you can show a human using the UI and an agent booking via chat side by side

## 5. Out of scope / simplify for demo

- Real GCKey/Facebook/Google/bank sign-in — use a trivial email/name form instead
- Real payment processing — mock/fake payment step, no real transaction
- Launch-day queuing system — not needed for a demo
- Multi-language (EN/FR) — English only unless specifically wanted
- Real park/campground data at scale — seed the DB with a small handful of real or realistic parks/campgrounds/sites (e.g. Banff/Tunnel Mtn, Kootenay/Redstreak, PEI/Cavendish) rather than scraping the full catalog
- First-come-first-serve site handling — reservable-only is fine for demo

## 6. Suggested build order

1. Backend: schema + seed data (a few parks, campgrounds, sites, a couple weeks of availability)
2. Backend: availability search + reservation CRUD endpoints
3. MCP server: wrap the backend endpoints as tools, test with an MCP-compatible client
4. Frontend: search → results → detail → checkout → confirmation flow against the same backend
5. Wire up agent chat panel (optional) to visually demo MCP calls happening live
