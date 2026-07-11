# Dashboard Assets

## Brazil States GeoJSON (required for choropleth map)

The Overview page uses `brazil_states.geojson` to render a choropleth of orders by
Brazilian state. The file is not committed because it is large (~1 MB) and available
from public sources.

### Download

Run this PowerShell command from the `src/dashboard/assets/` directory:

```powershell
Invoke-WebRequest `
  -Uri "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/brazil-states.geojson" `
  -OutFile "brazil_states.geojson"
```

The GeoJSON must have `properties.sigla` containing the two-letter UF code (e.g. `SP`, `RJ`).
This matches the `customer_state` values in `gold.fct_orders`.

If the file is absent, the Overview page falls back to a bar chart automatically.
