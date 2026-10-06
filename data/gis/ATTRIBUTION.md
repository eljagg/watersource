# Boundary data in this folder

## parishes.geojson — Jamaica parishes (ADM1)

Source: geoBoundaries (www.geoboundaries.org), gbOpen release, JAM ADM1, WGS 84.
Licence: Creative Commons Attribution 4.0 (CC BY 4.0). Citation: Runfola, D. et al. (2020)
geoBoundaries: A global database of political administrative boundaries. PLoS ONE 15(4): e0231866.

Used as the parish layer on the maps and as the island outline from which the demonstration
basin and WMU shapes are cut. Replace with WRA's own parish layer when supplied.

## demo_seeds.csv — seed points for demonstration basins and WMUs

Approximate centre points (longitude, latitude) of WRA's ten hydrological basins and the WMUs
listed in `data/reference/wmus.csv`. `load_boundaries --demo-shapes` builds Voronoi cells from these
points, clipped to the island (basins) and to the parent basin (WMUs), so the maps have plausible
areas to colour until WRA provides its official boundary shapefiles. Every shape built this way is
tagged `geom_source = "demonstration stand-in"` and is replaced the moment real boundaries are
loaded with `load_boundaries --basins <file> --wmus <file>`.
