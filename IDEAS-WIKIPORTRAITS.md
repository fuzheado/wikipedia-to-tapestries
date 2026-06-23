# WikiPortraits × Tapestry Ideas

WikiPortraits is a global photography initiative delivering high-quality, freely
licensed portraits for Wikipedia infoboxes. Since 2024 it has covered major events
— Sundance, Cannes, Eurovision, the Nobel ceremonies, the Venice Biennale, the
Winter Olympics, and more — growing to over 79,000 photos.

The Tapestry infinite canvas offers new ways to explore, present, and celebrate
this collection beyond the traditional Commons category page.

---

## 1. Event Portrait Wall

Take a single event (e.g., "Cannes 2026") and build a tapestry showing every
person photographed there. All portraits arranged in a dense, center-aligned grid
— each face clickable. The presentation steps through each one like a red carpet
gallery.

**Useful for:** Journalists, publicists, Wikipedia editors — seeing who was at an
event at a glance.

**Data needed:** Commons category `WikiPortraits/Cannes_2026` subfiles + SDC for
person's name and occupation.

---

## 2. Photographer's Portfolio

A single photographer's entire body of work for WikiPortraits. All the portraits
they've captured, arranged as a visual portfolio. Each portrait links to the
Commons file page. Could be automatically generated and shared with the
photographer as a showcase of their contributions.

**Useful for:** Photographer recognition, recruitment, contributor retention.

**Data needed:** Commons search by photographer credit + SDC `P170` (creator)
statements.

---

## 3. Award Season Timeline

Map an entire year: Sundance → Berlinale → SXSW → Cannes → Eurovision → Venice →
Toronto → Nobel → … Each event is a station on a timeline, with its portraits
clustered beneath. The presentation walks through the year month-by-month. Shows
the story of where the project went and who it captured.

**Useful for:** Annual reports, grant proposals, telling the project's story.

**Data needed:** WikiPortraits event list + Commons categories per event + event
dates from Wikidata.

---

## 4. Career Evolution — Same Person, Multiple Events

Many subjects appear at multiple events across years. Find all WikiPortraits
photos of a single person and arrange them chronologically. Shows how they look
across different events, lighting, backgrounds, and months/years — a mini-portfolio
for each notable person that Commons' flat category system can't easily assemble.

**Useful for:** Wikipedia article improvement (choosing the best portrait), fan
engagement, event planning.

**Data needed:** Wikidata `P18` (image) or direct Commons filename search + SDC
`P180` (depicts) linking to the person's QID.

---

## 5. Occupation Constellation

Query Wikidata for the occupation of each photographed person (actor, director,
musician, activist, scientist, …). Arrange portraits in clusters on the canvas
— all Film Directors in one area, all Musicians in another. Color-code
cross-connections (a musician who is also an activist sits between both clusters).
Shows the diversity of the collection at a glance.

**Useful for:** Understanding the demographic spread of coverage, identifying
gaps.

**Data needed:** SPARQL via Wikidata QIDs + `wdt:P106` (occupation) properties.

---

## 6. "From Red Link to Blue Link" Impact Map

Find Wikipedia articles that previously had no infobox photo and now have a
WikiPortraits portrait. Create a before/after comparison: the article title as
text on the left, the new portrait on the right, connected by an arrow. A
powerful visualization of the project's mission for grant reports and
presentations.

**Useful for:** Grant reporting, impact metrics, donor communications.

**Data needed:** Page history API checking when a WikiPortraits image was first
added + Wikidata before/after comparison.

---

## 7. Behind the Portrait — Camera & Metadata Gallery

Each WikiPortraits file has rich SDC metadata. Create a tapestry where each
portrait is accompanied by its technical details: camera model, lens, aperture,
ISO, photographer credit, location, date. Celebrates the craft of the photography
as much as the subjects — part gallery, part equipment museum.

**Useful for:** Photography community engagement, technical tutorials, camera
brand showcases.

**Data needed:** Commons `prop=imageinfo&iiprop=extmetadata` + SDC `P4082`
(camera), `P170` (creator), `P571` (date).

---

## 8. Commons Category Tree Browser for WikiPortraits

A browsable tapestry mirroring the `Category:WikiPortraits` hierarchy. Top level
shows all events as tiles with representative portraits. Zoom (presentation step)
into an event to see all its portraits. Zoom further into a person to see all
their portraits across events. A visual sitemap of the entire project corpus.

**Useful for:** Exploring the collection, discovering connections, navigation.

**Data needed:** Commons `list=categorymembers` walking the
`Category:WikiPortraits` tree recursively.

---

## 9. Geographic Portrait Atlas

Plot each portrait on a rough world map layout based on where the photo was taken
(or the subject's nationality). European subjects clustered left, Americas center,
Asia right. At a glance you see geographic coverage gaps — "we need more portraits
from Africa, South America" — which becomes a planning tool for future events.

**Useful for:** Strategic planning, identifying coverage gaps, global impact
visualization.

**Data needed:** SDC `P1071` (location of creation) or Wikidata `P27` (country of
citizenship) + coordinate mapping.

---

## 10. Style Study — Pose & Composition Analysis

Arrange portraits not by name or event, but by visual similarity — all straight-on
shots in one area, three-quarter profiles in another, smiling vs. serious, light
vs. dark backgrounds. A photographic style study of the project's collective
visual language.

**Useful for:** Photography workshops, style guides, artistic exploration.

**Data needed:** Basic image analysis (face detection angle, brightness histogram,
color palette) via Python script to classify and arrange.

---

## 11. "Six Degrees of WikiPortraits"

Pick any two people photographed by the project and find the shortest connection
path between them through shared events, photographers, or Wikidata relationships.
Render the chain as connected portraits on the canvas. A fun, shareable parlor
game using the collection.

**Useful for:** Social media engagement, virality, introducing people to the
collection.

**Data needed:** Wikidata SPARQL path queries + shared event categories + shared
photographer SDC statements.

---

## 12. Live Event Dashboard

During a live event (e.g., "Venice Biennale 2026"), create a tapestry that updates
as portraits are uploaded. New faces appear in real time. The presentation
auto-advances through the latest additions. Could be displayed on a monitor at
the event venue itself — attendees walk up and see their portrait appear on the
canvas.

**Useful for:** In-venue engagement, real-time coverage tracking, social media
moment.

**Data needed:** Commons EventStreams (new file uploads) filtered by WikiPortraits
category + Commons API for thumbnail + WebSocket or polling for live updates.
