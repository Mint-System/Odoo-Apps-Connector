import re

from .config import AGGREGATE_PALETTEN


def _get_location_base(s):
    if s:
        match = re.match(r"^[^\s-]+", s)
        return match.group(0) if match else s
    return None


def _transform_location(location):
    if _get_location_base(location) == "Shuttle":
        return "Shuttle"
    elif _get_location_base(location) == "Palette" and AGGREGATE_PALETTEN:
        return "Palette"
    return location


def _update_locations(data, transform_func):
    for item in data:
        item["LocationName"] = transform_func(item["LocationName"])
    return data


def _harmonize_empty_values(data):
    for item in data:
        for key, value in item.items():
            if value == "" or value is None or value == "---":
                item[key] = None
    return data


def _get_sql_for_journal_query(bzid, processed_journal_ids=()):
    """Journal rows of one Kardex order (BzId) that Odoo has not processed yet.

    Rows are summed per serial/lot; ``id_list`` holds the journal ids that went
    into each sum so the caller can mark them as processed.
    """
    bzid = int(bzid)
    not_processed = ", ".join(str(int(journal_id)) for journal_id in processed_journal_ids) or "0"

    return f"""
        WITH CTE AS (
            SELECT
                BzId,
                CASE
                    WHEN Seriennummer IS NOT NULL AND Seriennummer != '' THEN Seriennummer
                    WHEN Charge IS NOT NULL AND Charge != '' THEN Charge
                    ELSE '__none__'
                END AS SerienOrCharge,
                Belegnummer,
                Suchbegriff,
                Richtung,
                Row_Create_Time,
                Row_Update_Time,
                SUM(Menge) AS MengeErledigt,
                MAX(Komplett) AS MaxKomplett
            FROM PPG_Journal
            WHERE BzId = {bzid} AND ID NOT IN ({not_processed})
            GROUP BY
                BzId,
                CASE
                    WHEN Seriennummer IS NOT NULL AND Seriennummer != '' THEN Seriennummer
                    WHEN Charge IS NOT NULL AND Charge != '' THEN Charge
                    ELSE '__none__'
                END,
                Belegnummer,
                Suchbegriff,
                Richtung,
                Row_Create_Time,
                Row_Update_Time
        )
        SELECT
            c.BzId,
            c.Belegnummer,
            c.SerienOrCharge,
            c.Suchbegriff,
            c.Richtung,
            c.Row_Create_Time,
            c.Row_Update_Time,
            c.MengeErledigt,
            c.MaxKomplett,
            STUFF((
                SELECT ', ' + CAST(j.ID AS VARCHAR)
                FROM PPG_Journal j
                WHERE j.BzId = c.BzId AND j.ID NOT IN ({not_processed})
                FOR XML PATH(''), TYPE).value('.', 'NVARCHAR(MAX)'), 1, 2, '') AS id_list
        FROM CTE c
    """
