# Future Project Ideas

Leveraging Wikimedia data (Wikipedia, Commons, Wikidata) and the Tapestry infinite
canvas to create visual, interactive, and explorable experiences.

---

## 1. Timeline Explorer

Pull dates from a Wikipedia article's infobox and sections, then place images and
text blocks on the canvas along a horizontal timeline axis. Each era gets a column
— photos, key events, and linked figures.

**Great for:** "Space exploration", "Renaissance", "World War II"

**Data needed:** Infobox parsing + section headings with date mentions + Commons
images by century/category

**Tapestry tools:** Presentation steps walk the timeline left-to-right; image items
for each era; text items for event descriptions; rels connecting events to their era.

---

## 2. Wikidata Relationship Map

Take any topic and query Wikidata for its properties — "publisher of",
"influenced by", "member of", "location of", "child of" — then render each
relationship as a connected cluster on the canvas. The center is the main subject,
with spokes radiating to related items, each with an image and description. Think
of it as an interactive knowledge graph.

**Great for:** Artists (influences → works → contemporaries), Companies
(founded-by → subsidiaries → competitors), Scientists (discoveries → awards → mentors)

**Data needed:** SPARQL queries on Wikidata for inbound/outbound properties +
Commons images for each entity

**Tapestry tools:** Rels (arrows) connecting related items; grouping related
entities; presentation step per cluster.

---

## 3. Commons Category Browser

Given a Commons category (e.g., "Category:Saturn V"), walk the subcategory tree
and create a browsable visual index. Each subcategory gets a tile with representative
thumbnails. Clicking through the presentation zooms into deeper subcategories.
A visual sitemap of Commons.

**Great for:** Exploring Commons taxonomy — "Category:Birds" → "Category:Birds by
location" → "Category:Birds of Australia" → images

**Data needed:** Commons category API (`list=categorymembers`) + Commons thumbnails
+ SDC depicts statements

**Tapestry tools:** Groups for expandable sections; action buttons to jump to
subcategories; startView zoomed out to see the full tree.

---

## 4. Wikipedia Article as an Audio/Video Mix

For articles about musicians, filmmakers, or historical speeches, pull audio/video
files from Commons and arrange them into a listening/watching gallery. An article
about "Jazz" could have audio samples from Commons arranged around a timeline,
each with its own play button.

**Great for:** "Jazz" (audio clips), "Charlie Chaplin" (video clips), "Martin Luther
King Jr." (speeches)

**Data needed:** Commons `prop=videoinfo` / `prop=audioinfo` + article sections
for context + TimedMediaHandler metadata

**Tapestry tools:** Audio and video item types with `startTime`/`stopTime` for
clipping; webpage items for YouTube/IA embeds; action buttons for external links.

---

## 5. Citation Graph

Extract all references from a Wikipedia article, resolve DOIs and ISBNs, and map
them out. Each citation becomes a card with the source title, author, year, and a
link through to the actual paper. The canvas shows which statements in the article
are supported by which sources — a visual bibliography.

**Great for:** Dense academic articles with 50+ citations, "COVID-19 pandemic",
"Climate change"

**Data needed:** Wikitext citation template parsing (`cite web`, `cite journal`,
`cite book`) + CrossRef/DOI API for metadata + ISBNdb or OpenLibrary

**Tapestry tools:** Action buttons for external links to papers; text items for
citation previews; color-coded rels showing which citation supports which claim.

---

## 6. Cross-Lingual Article Bridge

Take the same topic in 5–10 languages and place their lead images, descriptions,
and key facts side by side. Each language gets a column. The presentation steps
through each language's take on the same subject.

**Great for:** "Solar System" in EN/FR/DE/ES/JA/ZH, "Mona Lisa" in EN/IT/FR

**Data needed:** Wikidata inter-language links + REST API summaries per language
+ Commons images (often shared across languages)

**Tapestry tools:** Columns of image+text pairs; presentation steps per language;
startView showing all languages at once for comparison.

---

## 7. Glossary on Canvas — Linked Definitions

Extract bolded terms and linked articles from the first paragraph of each section,
then build a visual glossary. Each term gets a small text card with its definition,
connected via arrows to the section it came from. The final result is an explorable
web of concepts from a single article.

**Great for:** Technical articles — "Quantum mechanics", "Photosynthesis", "Supply
and demand"

**Data needed:** Wikitext parsing for bold terms + internal links + summary
extracts for definitions

**Tapestry tools:** Compact text items for definitions; rels connecting definitions
back to their sections; groups for topic clusters.

---

## 8. Commons 3D / 360° Gallery

For articles that have 3D models or 360° photospheres on Commons, build a gallery
that uses Pannellum (equirectangular viewer) embedded via `webpage` items. The
canvas becomes a virtual museum — flat images in one section, 360° panoramas in
another, 3D models as embeddable viewers.

**Great for:** "Grand Canyon" (panoramas), "Colosseum" (360° photospheres),
"Mars rover" (3D models)

**Data needed:** Commons file search (`fileext=stl` or spherical XMP metadata for
Google Photo Sphere) + imageinfo for dimensions

**Tapestry tools:** Webpage items embedding Pannellum; image items for flat
photos; groups per location/artifact.

---

## 9. Revision History as a Filmstrip

Take the edit history of a heavily-edited article and create a visual filmstrip
of how the lead image, description, and size changed over time. Each significant
revision gets a tile showing the state of the article at that point, arranged
chronologically.

**Great for:** "Donald Trump", "COVID-19 pandemic", "Russia", "Taylor Swift"

**Data needed:** Revision history API (`prop=revisions`) + page assessment changes
+ image diffs + pageview spikes for context

**Tapestry tools:** Image items for lead image at each revision; text items for
description changes; rels showing the evolution path; presentation stepping through
time.

---

## 10. ML-Powered Article Audit Dashboard

Run a Wikipedia article through the Wikimedia ML services (Lift Wing / ORES) —
article quality, topic tags, revision risk scores — and render the results as a
dashboard on canvas. Quality score as a gauge, topic distribution as a tag cloud,
flagged issues as highlighted cards.

**Great for:** NPP (New Page Patrol) triage, article quality assessment,
understanding an article's health at a glance

**Data needed:** Lift Wing API (`/v3/models/{wiki}/articlequality`) + ORES
(goodfaith, damaging) + page assessment banners + WikiProject tags

**Tapestry tools:** Color-coded text items for scores; groups for categories of
metrics; action buttons linking to the article for further inspection.
