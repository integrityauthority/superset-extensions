# Magyar települési térképek - Superset Setup Guide

## Előfeltétel: Lookup tábla betöltése

Futtasd az alábbi SQL scriptet a DB-ben (SSMS-ben vagy más SQL klienssel):

```
D:\superset-extensions\hun_admin_boundaries\create_geo_telepules.sql
```

Ez létrehozza az `x_ih_geo_telepules` táblát 4041 sorral (3142 település, lat/lon koordinátákkal).

---

## 1. EU Pályázatok település szinten (deck.gl Scatter)

### SQL Lab-ban:

1. Nyisd meg a Superset SQL Lab-ot
2. Válaszd a PARTNER_CONTROL_RAW_P adatbázist
3. Másold be a `superset_eu_palyazat_telepules.sql` tartalmát
4. Futtasd -> ellenőrizd az eredményt
5. **SAVE AS DATASET** -> név: `eu_palyazat_telepulesenkent`

### Chart létrehozás:

1. Charts -> + New Chart
2. Dataset: `eu_palyazat_telepulesenkent`
3. Chart típus: **deck.gl Scatterplot**
4. Beállítások:
   - **Longitude**: `lon`
   - **Latitude**: `lat`
   - **Point Size**: `palyazat_db` (vagy `megitelt_mrd_ft`)
   - **Point Size (fixed or by column)**: By column
   - **Min/Max Point Size**: 5 / 50
   - **Color**: fixed szín vagy metrika alapján
   - **Mapbox Style**: light / dark / streets
   - **Viewport**: lat ~47.2, lon ~19.5, zoom ~7 (Magyarország)

### Mit mutat:
Buborékos térkép ahol minden település egy pont, méretük arányos az EU pályázatok számával vagy összegével. ~3000 település jelenik meg, a nagyobbak nagyobb buborékkal.

---

## 2. Partner Control cégek irányítószámonként (deck.gl Scatter/Heatmap)

### SQL Lab-ban:

1. Nyisd meg a Superset SQL Lab-ot
2. Válaszd a PARTNER_CONTROL_RAW_P adatbázist
3. Másold be a `superset_alap_fajl_irsz.sql` tartalmát
4. Futtasd -> ellenőrizd az eredményt
5. **SAVE AS DATASET** -> név: `cegek_iranyitoszamonkent`

### Chart létrehozás - Scatter:

1. Charts -> + New Chart
2. Dataset: `cegek_iranyitoszamonkent`
3. Chart típus: **deck.gl Scatterplot**
4. Beállítások:
   - **Longitude**: `lon`
   - **Latitude**: `lat`
   - **Point Size**: `ceg_db`
   - **Min/Max Point Size**: 3 / 40
   - **Viewport**: lat ~47.2, lon ~19.5, zoom ~7

### Chart létrehozás - Heatmap (alternatív):

1. Charts -> + New Chart
2. Dataset: `cegek_iranyitoszamonkent`
3. Chart típus: **deck.gl Heatmap** (ha elérhető)
4. Beállítások:
   - **Longitude**: `lon`
   - **Latitude**: `lat`
   - **Weight**: `ceg_db`
   - **Intensity**: 1-3
   - **Radius**: 20-50 pixels

### Mit mutat:
Hőtérkép vagy buborékos térkép, ahol látszik hol koncentrálódnak a cégek Magyarországon. Budapest kiugróan nagy lesz (300K+ cég), de a vidéki centrumok is jól látszanak.

---

## Fájlok összefoglaló

| Fájl | Cél |
|------|-----|
| `create_geo_telepules.sql` | Lookup tábla létrehozása (4041 sor, 3142 település) |
| `superset_eu_palyazat_telepules.sql` | Virtual dataset: EU pályázatok településenként |
| `superset_alap_fajl_irsz.sql` | Virtual dataset: cégek irányítószámonként |
| `hu_geonames.txt` | Forrás adat (geonames.org) |
| `postal_codes_geohungary.geojson` | Irányítószám poligonok (3569 feature, 3044 egyedi irszám) |
| `load_postal_geojson.py` | GeoJSON betöltő script MSSQL-be (x_ih_geo_irsz_polygon tábla) |

---

## 3. Irányítószám poligonok térképen (deck.gl GeoJSON)

Ez valódi területi poligonokat rajzol ki irányítószámonként (choropleth térkép), nem csak pontokat.

### Előkészítés: GeoJSON betöltése adatbázisba

```powershell
# pyodbc kell hozzá
py -m pip install pyodbc

# Betöltés (a server paramétert cseréld a sajátodra)
cd D:\superset-extensions\hun_admin_boundaries
py load_postal_geojson.py --server YOUR_SQL_SERVER --database PARTNER_CONTROL_RAW_P
```

Ez létrehozza az `x_ih_geo_irsz_polygon` táblát 3044 sorral (3044 egyedi irányítószám, összevont poligonokkal).

### SQL Lab-ban - Virtual Dataset létrehozása:

Példa: cégek száma irányítószámonként, poligon megjelenítéssel:

```sql
SELECT
    p.irsz,
    p.geojson,
    COALESCE(a.ceg_db, 0) AS ceg_db,
    COALESCE(a.aktiv_ceg_db, 0) AS aktiv_ceg_db
FROM [PARTNER_CONTROL_RAW_P].[dbo].[x_ih_geo_irsz_polygon] p
LEFT JOIN (
    SELECT
        bejegyzett_cim_irsz AS irsz,
        COUNT(*) AS ceg_db,
        SUM(CASE WHEN ceg_allapota = '0' THEN 1 ELSE 0 END) AS aktiv_ceg_db
    FROM [PARTNER_CONTROL_RAW_P].[dbo].[alap_fajl]
    WHERE bejegyzett_cim_irsz IS NOT NULL
        AND bejegyzett_cim_irsz != ''
    GROUP BY bejegyzett_cim_irsz
) a ON p.irsz = a.irsz
```

1. Futtasd SQL Lab-ban
2. **SAVE AS DATASET** -> név: `cegek_irsz_polygon`

### Chart létrehozás:

1. Charts -> + New Chart
2. Dataset: `cegek_irsz_polygon`
3. Chart típus: **deck.gl GeoJSON**
4. Beállítások:
   - **GeoJSON Column**: `geojson`
   - **Fill Color**: metrika alapján (`ceg_db` vagy `aktiv_ceg_db`)
   - **Stroke Color**: sötétszürke
   - **Stroke Width**: 1
   - **Opacity**: 0.7
   - **Mapbox Style**: Light
   - **Viewport**: lat ~47.2, lon ~19.5, zoom ~7 (Magyarország)
   - **Label**: `irsz` (opcionális, irányítószám felirat)
5. **Autozoom**: bekapcsolva (automatikusan Magyarországra zoomol)

### Mit mutat:
Choropleth térkép ahol minden irányítószám területe egy színezett poligon. A szín intenzitása arányos a kiválasztott metrikával (pl. cégek száma). Hover-re tooltip mutatja az irányítószámot és az értéket.

---

## Megjegyzések

- A `COLLATE Latin1_General_CI_AI` biztosítja az ékezet-független összehasonlítást
- Budapest kerületek (`Budapest, XIII.ker.` stb.) NEM matchelnek a geonames-zel (ott csak "Budapest" van). Ezek egy pontként jelennek meg.
- A lookup tábla irányítószám + település kombinációkat tartalmaz, egy irányítószámhoz több település is tartozhat
- A `postal_codes_geohungary.geojson` fájl 3569 feature-t tartalmaz, 3044 egyedi irányítószámmal. A betöltő script összevonja a duplikált irányítószámokat MultiPolygon-ná.
- Az `x_ih_geo_irsz_polygon` tábla bármilyen üzleti adattal JOIN-olható az `irsz` oszlopon keresztül
