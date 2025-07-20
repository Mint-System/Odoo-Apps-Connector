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


def _get_sql_for_journal_query(condition1=None, condition2=None):
    # sql = f"""
    #       WITH CTE AS (
    #             SELECT
    #                 BzId,
    #                  CASE
    #                     WHEN Seriennummer IS NOT NULL AND Seriennummer != '' THEN Seriennummer
    #                     WHEN Charge IS NOT NULL AND Charge != '' THEN Charge
    #                     ELSE '__none__'
    #                 END AS SerienOrCharge,
    #                 Belegnummer,
    #                 Suchbegriff,
    #                 Richtung,
    #                 Row_Create_Time,
    #                 Row_Update_Time,
    #                 SUM(Menge) AS MengeErledigt,
    #                 MAX(Komplett) AS MaxKomplett
    #             FROM PPG_Journal
    #             {condition1}
    #             GROUP BY
    #                 BzId,
    #                 CASE
    #                     WHEN Seriennummer IS NOT NULL AND Seriennummer != '' THEN Seriennummer
    #                     WHEN Charge IS NOT NULL AND Charge != '' THEN Charge
    #                     ELSE '__none__'
    #                 END,
    #                 Belegnummer,
    #                 Suchbegriff,
    #                 Richtung,
    #                 Row_Create_Time,
    #                 Row_Update_Time
    #         )
    #         SELECT
    #             c.*,
    #             STUFF(
    #                 (
    #                     SELECT ', ' + CAST(ID AS VARCHAR)
    #                     FROM PPG_Journal j
    #                     WHERE
    #                         j.BzId = c.BzId
    #                         AND ISNULL(NULLIF(COALESCE(j.Seriennummer, j.Charge), ''), '__none__') = c.SerienOrCharge
    #                         AND j.Belegnummer = c.Belegnummer
    #                         AND j.Suchbegriff = c.Suchbegriff
    #                         AND j.Richtung = c.Richtung
    #                         AND j.Row_Create_Time = c.Row_Create_Time
    #                         AND j.Row_Update_Time = c.Row_Update_Time
    #                     FOR XML PATH(''), TYPE
    #                 ).value('.', 'NVARCHAR(MAX)'),
    #                 1, 2, ''
    #             ) AS id_list
    #         FROM CTE c;
    #     """

    sql = f"""
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
                {condition1}
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
                (
                    SELECT
                        STUFF((
                            SELECT ', ' + CAST(j.ID AS VARCHAR)
                            FROM PPG_Journal j
                            WHERE j.BzId = c.BzId
                            FOR XML PATH(''), TYPE).value('.', 'NVARCHAR(MAX)')
                        , 1, 2, '')
                ) AS id_list
            FROM CTE c


        """

    return sql
