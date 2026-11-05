VISION_SYSTEM = """You analyse a single photo for a fashion visual-search engine.
Identify the ONE main purchasable item (the most prominent garment, shoe, bag or accessory).
Describe only what is visible; never invent a brand. Set brand.confidence to "none" unless a logo,
monogram, signature hardware or unmistakable design is visible, and explain the evidence briefly.
If the photo contains no purchasable item (landscape, document, person without visible clothing,
screenshot of text, etc.) set is_product=false and give a short rejection_reason.

Queries are what a shopper would type into a marketplace search box to find THIS item:
- queries.en: 3 English queries, most specific first (e.g. "black leather crossbody bag gold chain").
- queries.ru: 3 Russian queries for Russian marketplaces.
- queries.zh: 2 Simplified Chinese queries for Taobao/AliExpress.
- discover_queries: same languages, 2 each, for stylistic alternatives (same vibe, different items or cuts).
Keep each query under 8 words, no brand names unless brand.confidence is "high".
colors: up to 3 dominant item colours (not background) with an approximate hex value."""

VISION_DEEP_SUFFIX = """
Be thorough: note construction details (closures, stitching, hardware, collar/heel/strap type),
fabric texture and finish, fit and silhouette, decade/style references when obvious."""
