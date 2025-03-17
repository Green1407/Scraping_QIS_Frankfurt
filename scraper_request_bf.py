"""
Web scraping module for the QIS system of Goethe University Frankfurt.
Handles all scraping processes. Uses requests and BeautifulSoup to extract course and personnel data from the course catalog.
Data is stored as CSV files in the Database/ folder. Alternative to the original selenium webscraper.
"""

import os
from typing import List, Tuple

import pandas as pd
import requests
from requests.exceptions import RequestException, Timeout
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import unicodedata




def get_soup(url: str, session: requests.Session, timeout: int = 10) -> Tuple[str, BeautifulSoup]:
    """
    Helper function to get a BeautifulSoup object from a URL using requests

    Parameters:
    url (str) : The url that needs to be loaded
    session (request.Session) : The current requests session
    timeout (int) : Seconds after which timeout occurs

    Returns:
    Tuple[str, BeautifulSoup] : the response url and the beatiful soup object

    """
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.url, BeautifulSoup(response.text, 'html.parser')


def start_session(url: str = "https://qis.server.uni-frankfurt.de/qisserver/rds?state=user&type=0") -> Tuple[requests.Session, BeautifulSoup]:
    """
    Initializes and starts a requests Session with the Goethe University course lecture site as instance.

    Parameters:
        url (str, optional): The URL to open. Defaults to the Goethe University course lecture site.

    Returns:
        Tuple[requests.Session, BeautifulSoup]: The initialized Session and the parsed initial page.
    """
    session = requests.Session()
    try:
        current_url, soup = get_soup(url, session, timeout=5)
    except RequestException as e:
        print(f"Error fetching {url}: {e}")
        raise
    return session, soup
def get_course_catalog(semester_name: str, session: requests.Session, soup: BeautifulSoup) -> Tuple[str, BeautifulSoup]:
    """
    Retrieves the course catalog URL for a given semester from the Goethe University website.
    Simulates navigation by following links.

    Parameters:
        semester_name (str): The semester for which to retrieve the course catalog (e.g., "SoSe 2025").
        session (requests.Session): The requests Session instance.
        soup (BeautifulSoup): Parsed HTML of the current page.

    Returns:
        Tuple[str, BeautifulSoup]: The final catalog URL and the parsed page.
    """
    base_url = "https://qis.server.uni-frankfurt.de"

    # Open the choose semester url on the goethe uni website
    choosesemester = soup.find("a", id="choosesemester")
    if not choosesemester:
        raise ValueError("Link mit der ID 'choosesemester' nicht gefunden.")
    href = choosesemester.get("href")
    semester_page_url = urljoin(base_url, href)
    semester_page_url, soup = get_soup(semester_page_url, session)
    print(semester_page_url)
    # Choose the input semester on the choose semester url, the website will change to the choosen semester
    semester_link = None
    for a in soup.find_all("a", class_="regular"):
        link_text = a.get_text(strip=True)
        if semester_name.lower() in link_text.lower():
            semester_link = a
            break
    if not semester_link:
        raise ValueError(f"Semester '{semester_name}' nicht gefunden.")

    href = semester_link.get("href")
    new_url = urljoin(base_url, href)
    new_url, soup = get_soup(new_url, session)

    # Navigate to the Veranstaltungen directory on the website
    link = soup.find("a", string=lambda text: text and "Veranstaltungen" in text)
    if link:
        href = link.get("href")
        new_url = urljoin(base_url, href)
        try:
            new_url, soup = get_soup(new_url, session)
        except RequestException:
            pass
        else:
            base_url = new_url

    # Navigate to the Vorlesungsverzeichnis
    link = soup.find("a", string=lambda text: text and "Vorlesungsverzeichnis" in text)
    if link:
        href = link.get("href")
        new_url = urljoin(base_url, href)
        try:
            new_url, soup = get_soup(new_url, session)
        except RequestException:
            pass
        else:
            base_url = new_url

    return base_url, soup

def dfs_course_catalog(catalog_url: str, session: requests.Session, semester: str) -> int:
    """
    Performs a depth-first search on the course catalog website, extracting course data and saving it to a CSV file.

    Parameters:
        catalog_url (str): The URL of the course catalog page to scrape.
        session (requests.Session): The requests Session instance used for navigation and data extraction.
        semester (str): Current semester that is scraped.

    Returns:
        int: Always returns 0 upon completion.
    """
    result_dataframe = pd.DataFrame(columns=[
        'Kursname', 'Fachbereich', 'Zugeordnete Einrichtungen', 'verantwortliche Lehrpersonen',
        'Lehrpersonen', 'Veranstaltungsart', "Kürzel", "Semester", "SWS", "Credits", "Link"
    ])

    open_link_list: List[Tuple[str, str]] = []
    closed_link_list: List[str] = []

    # Initialize search with start site of Goethe Uni
    current_url, soup = get_soup(catalog_url, session)

    # Everything else is the same as in the scraper.py
    current_links = find_links_onsite(soup)
    open_link_list.extend(current_links)

    while open_link_list:
        link, link_type = open_link_list[-1]
        if link_type == "r" and link not in closed_link_list:
            data_visit = open_link_list.pop()[0]
            try:
                page_url, page_soup = get_soup(data_visit, session)
            except RequestException:
                continue
            print(data_visit)
            try:
                course_data = get_course_data(page_soup)
                result_dataframe.loc[len(result_dataframe)] = course_data + [data_visit]
            except Exception:
                pass
            closed_link_list.append(data_visit)
        elif link not in closed_link_list:
            next_visit = open_link_list.pop()[0]
            print(next_visit)
            try:
                page_url, page_soup = get_soup(next_visit, session)
            except RequestException:
                closed_link_list.append(next_visit)
                continue
            closed_link_list.append(next_visit)
            current_links = find_links_onsite(page_soup)
            open_link_list.extend(current_links)
        else:
            open_link_list.pop()

    os.makedirs("Database", exist_ok=True)
    result_dataframe.to_csv(f"Database/{semester.replace('/', '_')}_GoetheUni_Veranstaltungen.csv")

    return 0


def get_course_data(soup: BeautifulSoup) -> list:
    """
    Extracts course-related data from a Goethe University course webpage of the course catalog.

    Parameter:
        soup (BeautifulSoup): Parsed HTML of a course page.

    Returns:
        list: A list containing course information including title, faculties,
        associated institutions, responsible and other persons, and basic course details.
    """
    # Result list
    data = []

    # Get course title
    course_title_element = soup.find("h1")
    course_title = course_title_element.get_text().strip().replace(" - Einzelansicht", "").replace(";", "-").replace(",","-") if course_title_element else ""
    data.append(course_title)

    # Get the "Fachbereiche" where the course is listed
    fachbereiche = []
    divs = soup.find_all("div", style=lambda s: s and "padding-left: 10px" in s)
    for div in divs:
        a = div.find("a")
        if a:
            fachbereiche.append(a.get_text().strip().replace(";", ","))
    data.append(fachbereiche)

    # Extract associated institutions ("Einrichtungen")
    einrichtungen_tags = soup.select('table[summary="Übersicht über die zugehörigen Einrichtungen"] td a')
    einrichtungen_liste = [tag.get_text().strip() for tag in einrichtungen_tags]
    data.append(einrichtungen_liste if einrichtungen_liste else "")

    # Extract responsible and other persons from the "Verantwortliche Dozenten" table
    tables = soup.select('table[summary="Verantwortliche Dozenten"]')
    responsible_persons = []
    other_persons = []
    for table in tables:
        rows = table.find_all("tr")[1:]
        for row in rows:
            person_element = row.find("td", headers="persons_1")
            responsibility_element = row.find("td", headers="persons_2")
            if person_element and responsibility_element:
                a = person_element.find("a")
                person_name = a.get_text().strip().replace(";", ",").replace(",", "<")
                person_name = unicodedata.normalize("NFKC", person_name)
                responsibility = responsibility_element.get_text().strip().replace(";", ",")
                if responsibility == "verantwortlich":
                    responsible_persons.append([person_name, responsibility])
                else:
                    other_persons.append([person_name, responsibility])
    data.append(responsible_persons)
    data.append(other_persons)

    # Extract general data from the other table "Grunddaten zur Veranstaltung"
    tables = soup.select('table[summary="Grunddaten zur Veranstaltung"]')
    # Initialisiere Felder, falls nicht gefunden
    grunddaten = {"Veranstaltungsart": "", "SWS": "", "Credits": "", "Semester": "", "Kürzel": ""}
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            headers = row.find_all("th")
            values = row.find_all("td")
            for header, value in zip(headers, values):
                header_text = header.get_text().strip()
                value_text = value.get_text().strip().replace(";", ",")
                # Only add certain important fields to the result data
                if header_text in grunddaten:
                    grunddaten[header_text] = value_text
    data.extend([
        grunddaten["Veranstaltungsart"],
        grunddaten["Kürzel"],
        grunddaten["Semester"],
        grunddaten["SWS"],
        grunddaten["Credits"]
    ])

    return data


def find_links_onsite(soup: BeautifulSoup) -> List[Tuple[str, str]]:
    """
    Finds all relevant links to courses or other lecture directories.
    This function extracts links from a given webpage that lead either to deeper lecture directories
    or individual courses. Certain unwanted links (e.g., to page views or the general lecture directory)
    are explicitly excluded.

    Parameters:
        soup (BeautifulSoup): Parsed HTML of the current page.

    Returns:
        List[Tuple[str, str]]: Eine Liste von Tupeln mit URL und Typ.
        - "d" for deeper lecture directories (node)
        - "r" for regular course links (leaf)
    """
    # Structure is the same as in scraper.py
    current_link_list: List[Tuple[str, str]] = []
    deeper_links = soup.find_all("a", class_="ueb")
    course_links = soup.find_all("a", class_="regular")

    for link in deeper_links:
        title = link.get("title", "")
        if "Vorlesungsverzeichnis" in title:
            continue
        href = link.get("href")
        if href:
            current_link_list.append((href, "d"))

    for link in course_links:
        title = link.get("title", "")
        if "zur Seitenansicht" in title:
            continue
        href = link.get("href", "")
        if "state=user" in href or "category=veranstaltung.browse" in href:
            continue
        current_link_list.append((href, "r"))

    return current_link_list


def get_semester_list() -> List[str]:
    """
    Retrieves a list of available semesters for course lookup.

    Returns:
        list: A list of semester names (e.g., ["Winter 2023/24", "Sommer 2023"]).
    """
    url = "https://qis.server.uni-frankfurt.de/qisserver/rds?state=change&type=6&moduleParameter=semesterSelect&nextdir=change&next=SearchSelect.vm&subdir=applications&targettype=7&targetstate=change&getglobal=semester#W"
    session = requests.Session()
    try:
        _, soup = get_soup(url, session)
    except RequestException:
        return []
    semester_elements = soup.select('a.regular')
    semesters = [elem.get_text().strip() for elem in semester_elements if "Sommer" in elem.get_text() or "Winter" in elem.get_text()]
    return semesters


def scrape_institutes(session: requests.Session, url: str = "https://qis.server.uni-frankfurt.de/qisserver/rds?state=wtree&search=lk&trex=step&rootlk20251=1&P.vx=kurz") -> None:
    """
    Scrapes all information about individuals and their affiliated institutes from the personal page of
    the QIS Goethe University Frankfurt.

    Parameters:
        session (requests.Session): Intialized requests session
         url (str): URL of personal site of QIS Goethe University Frankfurt
    """
    result_dataframe = pd.DataFrame(columns=["Person", "Institut"])
    try:
        _, soup = get_soup(url, session)
    except RequestException:
        return

    fachbereich_links = soup.find_all("a", class_="ueb")
    fachbereich_urls = [link.get("href") for link in fachbereich_links if link.get("href")]
    personal_urls = []

    # Now iterate over founded fachbereiche urls
    for fach_url in fachbereich_urls:
        try:
            _, fach_soup = get_soup(fach_url, session)
        except RequestException:
            continue
        print(fach_url)
        personen_links = fach_soup.find_all("a", class_="ver")
        personal_urls.extend([link.get("href") for link in personen_links if link.get("href")])

    # Now iterate over each of the founded urls
    for person_url in personal_urls:
        try:
            _, person_soup = get_soup(person_url, session)
        except RequestException:
            continue
        print(person_url)
        try:
            person_data = get_institut_by_person(person_soup)
            result_dataframe.loc[len(result_dataframe)] = person_data
        except Exception:
            pass

    os.makedirs("Database", exist_ok=True)
    result_dataframe.to_csv("Database/Insitutsliste_Goethe_Uni.csv")


def get_institut_by_person(soup: BeautifulSoup) -> Tuple[str, str]:
    """
    Extracts a person's name and associated institute from their QIS profile page.

    Parameters:
        soup (BeautifulSoup): Parsed HTML of the person's profile page.

    Returns:
        Tuple[str, str]: A tuple containing the person's formatted name and their institute.
    """
    def get_field(field_name: str) -> str:
        th = soup.find("th", string=lambda text: text and field_name in text)
        if th:
            td = th.find_next_sibling("td")
            if td:
                return td.get_text().strip()
        return ""

    nachname = get_field("Nachname")
    vorname = get_field("Vorname")
    title = get_field("Titel")
    academic = get_field("Akad. Grad")
    name_format = f"{nachname} < {vorname} < {title} < {academic}"
    name_format = unicodedata.normalize("NFKC", name_format)

    institute_tag = soup.find("div", style=lambda s: s and "padding-left: 20px" in s)
    if institute_tag:
        a = institute_tag.find("a")
        first_institute = a.get_text().strip() if a else "Bitte manuell einfügen"
    else:
        first_institute = "Bitte manuell einfügen"

    return (name_format, first_institute)


def scrape_semester(semester: str) -> None:
    """
    Scrapes course data for a given semester.
    Initializes a requests Session, retrieves the course catalog for the specified semester,
    and then performs a depth-first search to scrape all course data.

    Parameters:
        semester (str): The semester to be scraped (e.g., "WS2024").
    """
    session, soup = start_session()
    catalog_url, soup = get_course_catalog(semester, session, soup)

    dfs_course_catalog(catalog_url, session, semester)


def scrape_personal() -> None:
    """
    Scrapes personal-related data from the Frankfurt University QIS website.
    Initializes a requests Session and starts the scraping function for personal data and their institutes.
    """
    session, _ = start_session()
    scrape_institutes(session)

# Beispielhafte Ausführung für verschiedene Semester
#semesterliste = ["Winter 2024/25", "Winter 2023/24", "Sommer 2023", "Winter 2022/23", "Sommer 2022"]
#for semester in semesterliste:
#    scrape_semester(semester)
