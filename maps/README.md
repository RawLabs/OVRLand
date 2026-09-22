# Offline maps on the Pi

The dashboard's Offline map source reads a local **raster MBTiles** package,
including PNG, JPEG, or WebP tiles. Vector/PBF packages need conversion to raster
before use. The reader opens the database read-only and does not download tiles.

Place an appropriately licensed package at `maps/offline.mbtiles`, or start the
app with `OVRLAND_MAP_FILE=/absolute/path/to/region.mbtiles`. Use the Offline tab's
**Check again** button after installing a package. If changing the environment
variable, restart the app. Packages are excluded from Git. No region is bundled.

The package must contain standard MBTiles `metadata` and `tiles` tables or views,
including format, name, bounds, and attribution. Attribution is displayed as text.
Use a package whose provider permits local offline use and preserve its credits.
Only covered tiles/zoom levels are available. This is map viewing, not offline
routing or turn-by-turn guidance. The Pi's app server must stay running; the
browser must still reach the Pi over localhost or the local network.

Online OpenStreetMap uses its standard public tiles with attribution and browser
HTTP caching. There is no prefetch/download action for that service: its policy
prohibits bulk downloads and offline packages. Build or obtain a licensed raster
package instead. Gaia mobile downloads do not supply this reader with a supported
map package; the Gaia option opens the user's web map in a separate browser tab.

Sources:
- https://operations.osmfoundation.org/policies/tiles/
- https://github.com/mapbox/mbtiles-spec/blob/master/1.3/spec.md
- https://help.gaiagps.com/hc/en-us/articles/360041232334-Can-I-use-Gaia-GPS-offline-with-a-laptop
