"""
Magyar irányítószám poligonok betöltése MSSQL-be a GeoJSON fájlból.

Felhasználás:
    py load_postal_geojson.py --server YOUR_SERVER --database PARTNER_CONTROL_RAW_P

A script:
  1. Beolvassa a postal_codes_geohungary.geojson fájlt
  2. Összevonja az azonos irányítószámú poligonokat MultiPolygon-ná
  3. Létrehozza az x_ih_geo_irsz_polygon táblát
  4. Beszúrja az adatokat batch-enként

Előfeltétel:
  - pyodbc: py -m pip install pyodbc
  - ODBC Driver 17 vagy 18 for SQL Server
"""

import argparse
import json
import os
import sys

try:
    import pyodbc
except ImportError:
    print("ERROR: pyodbc not installed. Run: py -m pip install pyodbc")
    sys.exit(1)


GEOJSON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "postal_codes_geohungary.geojson",
)

TABLE_NAME = "[dbo].[x_ih_geo_irsz_polygon]"

DDL = f"""
IF OBJECT_ID('{TABLE_NAME}', 'U') IS NOT NULL
    DROP TABLE {TABLE_NAME};

CREATE TABLE {TABLE_NAME} (
    irsz            NVARCHAR(10)    NOT NULL,
    geojson         NVARCHAR(MAX)   NOT NULL,
    polygon_count   INT             NOT NULL,
    CONSTRAINT PK_x_ih_geo_irsz_polygon PRIMARY KEY (irsz)
);
"""


def load_geojson(path: str) -> dict:
    print(f"Reading GeoJSON from: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"  Total features: {len(data['features'])}")
    return data


def merge_features(data: dict) -> list[dict]:
    """
    Merge features with the same postal_code into a single MultiPolygon.
    Returns list of dicts: {irsz, geojson_str, polygon_count}
    """
    by_code: dict[str, list[dict]] = {}
    for feat in data["features"]:
        code = str(feat["properties"]["postal_code"])
        by_code.setdefault(code, []).append(feat)

    results = []
    for code, features in sorted(by_code.items()):
        if len(features) == 1:
            geom = features[0]["geometry"]
            poly_count = 1
        else:
            # Merge multiple polygons into a single MultiPolygon
            all_coords = []
            for feat in features:
                g = feat["geometry"]
                if g["type"] == "Polygon":
                    all_coords.append(g["coordinates"])
                elif g["type"] == "MultiPolygon":
                    all_coords.extend(g["coordinates"])
            geom = {"type": "MultiPolygon", "coordinates": all_coords}
            poly_count = len(all_coords)

        # Build a complete GeoJSON Feature (this is what deck.gl expects)
        geojson_feature = {
            "type": "Feature",
            "properties": {"postal_code": code},
            "geometry": geom,
        }

        results.append({
            "irsz": code,
            "geojson_str": json.dumps(geojson_feature, ensure_ascii=False),
            "polygon_count": poly_count,
        })

    print(f"  Unique postal codes after merge: {len(results)}")
    multi = sum(1 for r in results if r["polygon_count"] > 1)
    print(f"  Codes with merged polygons: {multi}")
    return results


def get_connection(server: str, database: str, trusted: bool = True) -> pyodbc.Connection:
    # Try ODBC Driver 18 first, then 17
    for driver in ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"]:
        try:
            conn_str = (
                f"DRIVER={{{driver}}};"
                f"SERVER={server};"
                f"DATABASE={database};"
            )
            if trusted:
                conn_str += "Trusted_Connection=yes;"
            # Driver 18 defaults to encrypt=yes, which may fail with self-signed certs
            if "18" in driver:
                conn_str += "TrustServerCertificate=yes;"

            print(f"Connecting with {driver}...")
            conn = pyodbc.connect(conn_str, timeout=10)
            print(f"  Connected to {server}/{database}")
            return conn
        except pyodbc.Error as e:
            print(f"  {driver} failed: {e}")
            continue

    print("ERROR: No working ODBC driver found.")
    print("  Available drivers:", pyodbc.drivers())
    sys.exit(1)


def create_table(conn: pyodbc.Connection) -> None:
    cursor = conn.cursor()
    print(f"Creating table {TABLE_NAME}...")
    for statement in DDL.split("GO"):
        stmt = statement.strip()
        if stmt:
            cursor.execute(stmt)
    conn.commit()
    print("  Table created.")


def insert_data(conn: pyodbc.Connection, rows: list[dict], batch_size: int = 100) -> None:
    cursor = conn.cursor()
    sql = f"INSERT INTO {TABLE_NAME} (irsz, geojson, polygon_count) VALUES (?, ?, ?)"

    total = len(rows)
    inserted = 0

    print(f"Inserting {total} rows (batch size: {batch_size})...")
    for i in range(0, total, batch_size):
        batch = rows[i : i + batch_size]
        params = [(r["irsz"], r["geojson_str"], r["polygon_count"]) for r in batch]
        cursor.executemany(sql, params)
        conn.commit()
        inserted += len(batch)
        if inserted % 500 == 0 or inserted == total:
            print(f"  {inserted}/{total} rows inserted")

    print(f"  Done. {inserted} rows total.")


def verify(conn: pyodbc.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
    count = cursor.fetchone()[0]
    cursor.execute(f"SELECT MIN(irsz), MAX(irsz) FROM {TABLE_NAME}")
    min_code, max_code = cursor.fetchone()
    cursor.execute(
        f"SELECT TOP 1 irsz, polygon_count, LEN(geojson) as geojson_len FROM {TABLE_NAME} ORDER BY LEN(geojson) DESC"
    )
    biggest = cursor.fetchone()
    print(f"\nVerification:")
    print(f"  Total rows: {count}")
    print(f"  Postal code range: {min_code} - {max_code}")
    print(f"  Largest GeoJSON: irsz={biggest[0]}, polygons={biggest[1]}, {biggest[2]:,} chars")


def main():
    parser = argparse.ArgumentParser(description="Load Hungarian postal code polygons into MSSQL")
    parser.add_argument("--server", required=True, help="SQL Server hostname (e.g. localhost or myserver\\instance)")
    parser.add_argument("--database", default="PARTNER_CONTROL_RAW_P", help="Database name (default: PARTNER_CONTROL_RAW_P)")
    parser.add_argument("--batch-size", type=int, default=100, help="INSERT batch size (default: 100)")
    parser.add_argument("--geojson", default=GEOJSON_PATH, help="Path to GeoJSON file")
    args = parser.parse_args()

    data = load_geojson(args.geojson)
    rows = merge_features(data)

    conn = get_connection(args.server, args.database)
    create_table(conn)
    insert_data(conn, rows, args.batch_size)
    verify(conn)

    conn.close()
    print("\nDone! Next steps:")
    print("  1. Superset SQL Lab -> create a virtual dataset that JOINs this table with your data")
    print("  2. Charts -> deck.gl GeoJSON -> select the geojson column")


if __name__ == "__main__":
    main()
