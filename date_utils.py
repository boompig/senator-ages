import re
from datetime import datetime
from pprint import pprint
from typing import Optional

import pandas as pd
from dateutil.parser import parse

WIKI_AGE_PATTERN = re.compile('age \\d+')
DATE_PATTERN = re.compile(r'\d{4}-\d{2}-\d{2}')


def extract_age_from_wikitable(born_str: str) -> int:
    """
    Each senator (on the wiki page) has an associated age in the table
    Read that age

    born_str format: (yyyy-mmd-dd) <text str> (age n)
    """
    assert isinstance(born_str, str), repr(born_str)
    m = WIKI_AGE_PATTERN.search(born_str)
    assert m is not None, born_str
    return int(m.group().replace('age ', ''))


def calculate_age_from_birthday_wikitable(born_str: str) -> int:
    """
    Each senator (on the wiki page) has an associated birthday in the table
    Calculate their age from today using the listed age

    born_str format: (yyyy-mmd-dd) <text str> (age n)
    """
    m = DATE_PATTERN.search(born_str)
    assert m is not None, born_str
    iso_date = m.group()
    dt = datetime.fromisoformat(iso_date)
    age = get_age_from_birthday(dt)
    assert age is not None
    return age


def age_from_mandatory_retirement_date(mandatory_retirement_date: str) -> int:
    """
    Canadian senators must retire at 75
    So can use the mandatory retirement date to calculate the age
    """
    today = datetime.today()
    dt = parse(mandatory_retirement_date)
    years_to_retirement = (dt - today).days / 365.25
    assert years_to_retirement > 0 and years_to_retirement < 50, years_to_retirement
    age = int(75 - years_to_retirement)
    return age


def calculate_age_from_year(born_year: int) -> int:
    today = datetime.today()
    dt = datetime(year=born_year, month=1, day=1)
    years = (today - dt).days // 365.25
    return int(years)


def get_age_from_birthday(dt: datetime) -> Optional[int]:
    if dt is None or pd.isna(dt):
        return None
    else:
        today = datetime.today()
        years = (today - dt).days // 365.25
        return int(years)


if __name__ == "__main__":
    df = pd.read_parquet("data/us_senators/senators.parquet")
    df['wiki_age'] = df['Born'].apply(extract_age_from_wikitable)
    df['calculated_age'] = df['Born'].apply(calculate_age_from_birthday_wikitable)
    pprint(
        df[df['calculated_age'] != df['wiki_age']]
    )

    # write this
    df.to_parquet(path="data/us_senators/senators-with-ages.parquet")

    # df['wiki_age'] = df['Born'].apply(extract_wiki_age)
    # df
