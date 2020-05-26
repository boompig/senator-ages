"""
Crawl the age of senators on wikipedia
"""

import json
import logging
import os
import re
from argparse import ArgumentParser
from datetime import datetime
from pprint import pprint
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

import pandas as pd
import requests
import wikipedia as wiki
import wptools
from bs4 import BeautifulSoup
from dateutil.parser import ParserError, parse  # type: ignore

import date_utils


BORN_DATE_PATTERN = re.compile(r'\(.*?born (.*?)(in .*?)?\)')



def extract_wikitable(url: str, id: Optional[str] = None) -> BeautifulSoup:
    selector = {"class": "wikitable"}
    if id:
        selector["id"] = id
    r = requests.get(url)
    html = r.text
    soup = BeautifulSoup(html, features="lxml")
    table = soup.find("table", selector)
    return table


def extract_wikitable_schema(table: BeautifulSoup) -> List[str]:
    cols = []
    for col in table.find('tr').findAll('th'):
        if 'colspan' in col.attrs:
            n = int(col.attrs['colspan'])
            for i in range(n):
                cols.append(f'{col.text.strip()} - {i + 1}')
        else:
            cols.append(col.text.strip())
    return cols


def extract_wikitable_content(table: BeautifulSoup, cols: List[str]) -> List[dict]:
    rows = []
    next_row = {}  # type: Dict[str, Any]

    for i, row in enumerate(table.find('tbody').find_all('tr', recursive=False)):
        d = next_row
        next_row = {}

        if i == 0:
            # skip first row - that's the header row
            continue

        # hack for rowspan
        cols_to_search = cols[:]
        for key in d:
            cols_to_search.remove(key)

        for col, key in zip(row.find_all(['td', 'th'], recursive=False), cols_to_search):
            d[key] = col.text.replace('&nbsp;', ' ').replace('\xa0', ' ').strip()
            if 'rowspan' in col.attrs and int(col.attrs['rowspan']) == 2:
                next_row[key] = d[key]

        rows.append(d)
    return rows


def wikitable_to_dataframe(table: BeautifulSoup) -> pd.DataFrame:
    cols = extract_wikitable_schema(table)
    rows = extract_wikitable_content(table, cols)
    df = pd.DataFrame(rows)
    return df


def save_parsed_data(rows: Any, fname: str):
    with open(fname, "w") as fp:
        json.dump(rows, fp, indent=4)


def extract_all_wikitables(url: str, id=None) -> List[BeautifulSoup]:
    """return soup table from URL"""
    selector = {'class': 'wikitable'}
    if id:
        selector['id'] = id
    r = requests.get(url)
    html = r.text
    soup = BeautifulSoup(html)
    tables = soup.find_all('table', selector)
    return tables


def extract_wikitable_content_with_links(table: BeautifulSoup, cols: List[str]) -> List[dict]:
    rows = []
    next_row = {}  # type: Dict[str, Any]

    for i, row in enumerate(table.find('tbody').find_all('tr', recursive=False)):
        d = next_row
        next_row = {}

        if i == 0:
            # skip first row - that's the header row
            continue

        # hack for rowspan
        cols_to_search = cols[:]
        for key in d:
            cols_to_search.remove(key)

        for col, key in zip(row.find_all(['td', 'th'], recursive=False), cols_to_search):
            d[key] = col.text.replace('&nbsp;', ' ').replace('\xa0', ' ').strip()
            if 'rowspan' in col.attrs and int(col.attrs['rowspan']) == 2:
                next_row[key] = d[key]

            anchor = col.find('a')
            if anchor:
                d[key + '_link'] = anchor.attrs['href']

        rows.append(d)
    return rows


def __title_from_relative_link(s: str) -> str:
    return unquote(s.replace('/wiki/', '', 1).replace('_', ' '))


def read_age_from_wikipedia_page(member_link: str) -> Optional[int]:
    """
    Wikipedia articles for a person have a pretty static structure.
    Usually the summary will include the date when a person was born.
    Wikipedia's style is to include this information in brackets like this:

    (born <date>)

    In some cases the format varies slightly:

    (<some other information>, born <date>)
    (<some other information>; born <date>)
    (born <date> in <location>)
    (born in <year>)
    (born <year-1> or <year-2>)

    This method may fail for some of these cases, but tries to handle most of them

    member_link: The relative wikipedia link from the MP's name in the wiki page
    """
    title = __title_from_relative_link(member_link)
    try:
        pg = wiki.page(title=title)
    except wiki.PageError as e:
        logging.error(f'failed to load page with title {title}')
        logging.error(e)
        return None
    except wiki.DisambiguationError as e:
        logging.error(f'ERROR: loaded ambiguous page with title {title}')
        logging.error(e)
        return None
    logging.debug(f'loaded Wiki page for {member_link}')
    try:
        m = BORN_DATE_PATTERN.search(pg.summary)
        assert m is not None
        date_str = m.group(1)
    except AssertionError:
        logging.error(f'ERROR: failed to extract birthday from summary: {repr(pg.summary)} ; title = {title}')
        return None
    logging.debug(f'Found born date pattern: {date_str}')
    try:
        dt = parse(date_str)
        age = date_utils.get_age_from_birthday(dt)
        return age
    except ParserError:
        logging.error(f'ERROR: Failed to extract date from string: {repr(date_str)} ; title = {title}')
        return None


def extract_birth_date_from_infobox(member_link: str) -> Optional[str]:
    title = __title_from_relative_link(member_link)
    try:
        page = wptools.page(title)
        d = page.get_parse()
    except LookupError as e:
        print(f'failed to get page for title {title}')
        print(e)
        return None
    try:
        return d.data['infobox']['birth_date']
    except KeyError:
        pprint(d.data['infobox'])
        return None


def parse_birth_date_and_age(birthday: str) -> datetime:
    """
    Return the birthday *only*
    """
    pattern = re.compile(r'(\d{4}\|\d+\|\d+)[\}\|]')
    m = pattern.search(birthday)
    if m is None:
        # there is a date that is parsable
        i = birthday.index('|')
        j = birthday.index('}', i)
        date_str = birthday[i + 1: j].strip()
        logging.warning('had to parse date in birth-date-and-age macro: %s', date_str)
        return parse(date_str)
    else:
        year, month, day = [int(x) for x in m.group(1).split('|')]
        return datetime(year=year, month=month, day=day)


def parse_birth_year_and_age(birthday: str) -> datetime:
    """
    Return the birthday *only*
    Since here we have only the year, assume months are 1, 1
    """
    i = birthday.index('|')
    j = birthday.index('}', i)
    year = int(birthday[i + 1: j].strip())
    return datetime(year=year, month=1, day=1)


def parse_birth_based_on_age_as_of(birth_date: str) -> datetime:
    """
    Return the (calculated) birthday *only*
    """
    pattern = re.compile(r'(\d+)\s?\|(\d{4}\|\d+\|\d+)')
    m = pattern.search(birth_date)
    if m is None:
        print(birth_date)
        raise Exception()
    age = int(m.group(1))
    year, month, day = [int(x) for x in m.group(2).split('|')]
    birthday = datetime(year=year - age, month=month, day=day)
    return birthday


def parse_rest(birthday: str) -> datetime:
    if len(birthday) == 4 and birthday.isdigit():
        return datetime(year=int(birthday), month=1, day=1)
    elif birthday.startswith(r'{{circa'):
        i = birthday.find('|')
        j = birthday.find('}', i)
        year = int(birthday[i + 1: j])
        return datetime(year=year, month=1, day=1)

    if birthday.startswith('c. '):
        birthday = birthday.replace('c. ', '')
    return parse(birthday)


def parse_bbad(birth_date: str) -> datetime:
    """
    We can do lots of different stuff here
    Going to take the simplest path
    """
    pattern = re.compile(r'(\d+)\|(\d{4}\|\d+\|\d+)')
    m = pattern.search(birth_date)
    assert m is not None, birth_date
    age = int(m.group(1))
    year, month, day = [int(x) for x in m.group(2).split('|')]
    birthday = datetime(year=year - age, month=month, day=day)
    return birthday


def extract_birthday_from_infobox_macro(birth_date: str) -> Optional[datetime]:
    """When using wputils, birth_date is usually returned as a macro.
    There are a few different macros and we have stuff to parse all of them
    """
    if birth_date is None:
        return None
    elif birth_date.startswith(r'{{birth date and age') or birth_date.startswith(r'{{Birth date and age') or birth_date.startswith(r'{{Birth-date and age') or birth_date.startswith(r'{{nowrap|birth date and age'):
        return parse_birth_date_and_age(birth_date)
    elif birth_date.startswith(r'{{birth based on age as of date') or birth_date.startswith(r'{{Birth based on age as of date'):
        return parse_birth_based_on_age_as_of(birth_date)
    elif birth_date.startswith(r'{{birth year and age') or birth_date.startswith(r'{{Birth year and age'):
        return parse_birth_year_and_age(birth_date)
    elif birth_date.startswith(r'{{Bbad'):
        return parse_bbad(birth_date)
    else:
        return parse_rest(birth_date)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--us-senators", action="store_true",
                        help="Extract and save data for US Senators")
    parser.add_argument("--ca-senators", action="store_true",
                        help="Extract and save data for Canadian Senators")
    parser.add_argument("--us-reps", action="store_true",
                        help="Extract and save data for US Reps")
    parser.add_argument("--ca-reps", action="store_true",
                        help="Extract and save data for Canadian MPs")
    args = parser.parse_args()

    if args.us_senators:
        url = 'https://en.wikipedia.org/wiki/List_of_current_United_States_senators'
        table = extract_wikitable(url, id="senators")
        cols = extract_wikitable_schema(table)
        rows = extract_wikitable_content(table, cols)
        df = pd.DataFrame(rows)

        try:
            os.makedirs("data/us_senators")
        except FileExistsError:
            pass
        save_parsed_data(rows, "data/us_senators/senators.json")
        df.to_parquet(path="data/us_senators/senators.parquet")
    if args.ca_senators:
        url = 'https://en.wikipedia.org/wiki/List_of_current_senators_of_Canada'
        table = extract_wikitable(url)
        cols = extract_wikitable_schema(table)
        rows = extract_wikitable_content(table, cols)
        df = pd.DataFrame(rows)

        try:
            os.makedirs("data/ca_senators")
        except FileExistsError:
            pass
        save_parsed_data(rows, "data/ca_senators/senators.json")
        df.to_parquet(path="data/ca_senators/senators.parquet")
    if args.us_reps:
        url = 'https://en.wikipedia.org/wiki/List_of_current_members_of_the_United_States_House_of_Representatives'
        table = extract_wikitable(url)
        cols = extract_wikitable_schema(table)
        rows = extract_wikitable_content(table, cols)
        df = pd.DataFrame(rows)

        try:
            os.makedirs("data/us_reps")
        except FileExistsError:
            pass
        save_parsed_data(rows, "data/us_reps/us_reps.json")
        df.to_parquet(path="data/us_reps/us_reps.parquet")
    if args.ca_reps:
        url = 'https://en.wikipedia.org/wiki/List_of_House_members_of_the_43rd_Parliament_of_Canada'
        table = extract_wikitable(url)
        cols = extract_wikitable_schema(table)
        rows = extract_wikitable_content_with_links(table, cols)
        df = pd.DataFrame(rows)

        try:
            os.makedirs("data/ca_reps")
        except FileExistsError:
            pass
        save_parsed_data(rows, "data/ca_reps/ca_reps_with_links.json")
        df.to_parquet(path="data/us_reps/ca_reps_with_links.parquet")
