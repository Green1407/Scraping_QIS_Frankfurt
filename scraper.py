"""
Web scraping module for the QIS system of Goethe University Frankfurt.
Handles all scraping processes. Uses Selenium to extract course and personnel data from the course catalog.
Data is stored as CSV files in the `Database/` folder.
"""

import os
from datetime import datetime
from typing import List, Tuple

import pandas as pd
from urllib3.exceptions import ReadTimeoutError
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


# Function to start the WebDriver
def start_driver(url: str = "https://qis.server.uni-frankfurt.de/qisserver/rds?state=user&type=0") -> webdriver.Chrome:
    """
    Initializes and starts a headless Chrome WebDriver instance.

    Parameters:
        url (str, optional): The URL to open in the WebDriver. Defaults to the Goethe University course lecture site.

    Returns:
        webdriver.Chrome: The initialized WebDriver instance with the requested page loaded.
    """
    options = Options()
    options.add_argument("--headless")  # Enable headless mode
    options.add_argument("--disable-gpu")  # Disable GPU for stability (optional)
    options.add_argument("--no-sandbox")  # For Linux systems (optional)
    options.add_argument("--disable-extensions")  # Disable extensions

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(5)  # Set page load timeout (in seconds)
    driver.get(url)  # Open the specified URL

    return driver

def get_course_catalog(semester_name: str, driver: WebDriver) -> str:
    """
    Retrieves the course catalog URL for a given semester from the Goethe University website.

    Paramters:
        semester_name (str): The semester for which to retrieve the course catalog (e.g., "Winter 2023/24").
        driver (WebDriver): The Selenium WebDriver instance with current goethe uni QIS website opened.

    Returns:
        str: The URL of the course catalog page for the specified semester.
    """
    # Find and click on the semester dropdown menu
    semester_dropdown = driver.find_element(By.ID, "choosesemester")
    semester_dropdown.click()

    # Wait for the semester options to be visible and select the appropriate one
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, f"//a[contains(text(), '{semester_name}')]"))
    )
    selected_semester_option = driver.find_element(By.XPATH, f"//a[contains(text(), '{semester_name}')]")
    selected_semester_option.click()

    # Select the "Veranstaltungen" section
    link = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Veranstaltungen"))
    )
    link.click()

    # Navigate to the course catalog section
    course_catalog_link = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Vorlesungsverzeichnis"))
    )
    course_catalog_link.click()

    # Return the final catalog URL
    return driver.current_url

def dfs_course_catalog(catalog_url: str, driver: WebDriver, semester: str) -> int:
    """
    Performs a depth-first search on the course catalog website, extracting course data and saving it to a CSV file.

    Parameters:
        catalog_url (str): The URL of the course catalog page to scrape.
        driver (WebDriver): The Selenium WebDriver instance used for navigation and data extraction.
        semester (str): Current semester that is scraped

    Returns:
        int: Always returns 0 upon completion.
    """
    # Initialize DataFrame for result export
    result_dataframe = pd.DataFrame(columns=[
        'Kursname', 'Fachbereich', 'Zugeordnete Einrichtungen', 'verantwortliche Lehrpersonen',
        'Lehrpersonen', 'Veranstaltungsart', "Kürzel", "Semester", "SWS", "Credits", "Link"
    ])

    # Lists for visited and unvisited links, important so no urls will be opened twice
    open_link_list = []
    closed_link_list = []

    # Initialize first search so that open_link_list is not empty
    current_links = find_links_onsite(driver)
    open_link_list.extend(current_links)

    while open_link_list != []:
        # Check if the last link is unvisited and a veranstaltung indicated by the "r"
        if open_link_list[-1][1] == "r" and open_link_list[-1][0] not in closed_link_list:
            data_visit = open_link_list.pop()[0]
            try:
                driver.get(data_visit)
            except (TimeoutException, ReadTimeoutError):
                pass  # Ignore timeout errors and continue
            print(data_visit)

            # After the driver loads the page, fetch the course data and append the result to the result DataFrame
            try:
                result_dataframe.loc[len(result_dataframe)] = get_course_data(driver) + [data_visit]
            except Exception:
                pass  # Ignore errors and continue processing
            # Finally add the visited course link to the closed list, so he wont get visited again
            closed_link_list.append(data_visit)

        # Check if the last link is unvisited and is not a veranstaltung no "r" indicates that
        # Note: The courses can be considered as leaves of the DFS tree, whereas the other URLS can be considered as normal nodes
        elif open_link_list[-1][0] not in closed_link_list:
            # Deletes the url from the open link list and saves it as next visit url
            next_visit = open_link_list.pop()[0]
            print(next_visit)
            # Try to load the url that need to be visited next
            try:
                driver.get(next_visit)
            except (TimeoutException, ReadTimeoutError,):
                pass

            # After the site is loaded append it to the closed link list so it will not be visited again
            closed_link_list.append(next_visit)

            # Now find all relevant urls to other "nodes" of the tree or to all other branches of the course directory
            current_links = find_links_onsite(driver)

            # Add them to the open link list, so they will be visited in future iterations
            open_link_list = open_link_list + current_links
        else:
            open_link_list.pop()[0]

    # Save results to a CSV file
    os.makedirs("Database", exist_ok=True)
    result_dataframe.to_csv(f"Database/{semester.replace("/","_")}_GoetheUni_Veranstaltungen.csv")

    return 0

def get_course_data(driver: WebDriver) -> list:
    """
    Extracts course-related data from a goethe university course website of the course catalog.

    Parameter:
        driver (WebDriver): The Selenium Webdriver instance with a course website loaded

    Returns:
        list: A list containing course information including title, faculties,
              associated institutions, responsible and other persons, and basic course details.
    """
    # Result list
    data = []

    # Get course title
    course_title_element = driver.find_element(By.XPATH, '//h1')
    course_title = course_title_element.text.strip().replace(" - Einzelansicht","").replace(";","-").replace(",","-")
    data.append(course_title)

    # Get the "Fachbereiche" where the course is listed
    fachbereiche = []
    fachbereich_elemente = driver.find_elements(By.XPATH, '//div[contains(@style, "padding-left: 10px")]/a')
    for element in fachbereich_elemente:
        fachbereiche.append(element.text.strip().replace(";", ","))
    data.append(fachbereiche)

    # Extract associated institutions ("Einrichtungen")
    einrichtungen = driver.find_elements(By.XPATH, '//table[@summary="Übersicht über die zugehörigen Einrichtungen"]//td/a')
    einrichtungen_liste = [row.text for row in einrichtungen]
    if einrichtungen_liste:
        data.append(einrichtungen_liste)

    # Extract responsible and other persons from the "Verantwortliche Dozenten" table
    tables = driver.find_elements(By.XPATH, '//table[@summary="Verantwortliche Dozenten"]')
    responsible_persons = []
    other_persons = []

    #Get data from the Dozenten table
    for table in tables:
        rows = table.find_elements(By.TAG_NAME, 'tr')[1:]
        for row in rows:
            person_element = row.find_element(By.XPATH, './td[@headers="persons_1"]/a')
            responsibility_element = row.find_element(By.XPATH, './td[@headers="persons_2"]')
            person_name = person_element.text.strip().replace(";",",").replace(",","<")
            responsibility = responsibility_element.text.strip().replace(";",",")
            # If they are listed as verantwortlich, extract them as responsible, else as other persons
            if responsibility == "verantwortlich":
                responsible_persons.append([person_name, responsibility])
            else:
                other_persons.append([person_name, responsibility])
    data.append(responsible_persons)
    data.append(other_persons)

    # Extract general data from the other table "Grunddaten zur Veranstaltung"
    tables = driver.find_elements(By.XPATH, '//table[@summary="Grunddaten zur Veranstaltung"]')
    for table in tables:
        rows = table.find_elements(By.TAG_NAME, 'tr')
        for row in rows:
            # Find the headers of the table entrys and their values
            headers = row.find_elements(By.TAG_NAME, 'th')
            values = row.find_elements(By.TAG_NAME, 'td')
            for header, value in zip(headers, values):
                header_text = header.text.strip()
                value_text = value.text.strip().replace(";",",")
                # Only add certain important fields to the result data
                if header_text == "Veranstaltungsart" or header_text == "SWS" or header_text == "Credits" or header_text == "Semester" or header_text == "Kürzel":
                    data.append(value_text)

    return data

def find_links_onsite(driver: WebDriver) -> list[Tuple[str, str]]:
    """Finds all relevant links to courses or other lecture directories.
    This function extracts links from a given webpage that lead either to deeper lecture directories
    or individual courses. Certain unwanted links (e.g., to page views or the general lecture directory)
    are explicitly excluded.

    Parameters:
        driver (WebDriver): A Selenium WebDriver object to interact with the webpage.

    Returns:
        List[Tuple[str, str]]: A list of tuples containing the extracted links and their type (node or leaf).
        - "d" for deeper lecture directories (node)
        - "r" for regular course links (leaf)
    """
    # Define result url list and get all course links and deeper links by css style
    current_link_list = []
    deeper_links = driver.find_elements(By.CSS_SELECTOR, "a.ueb")
    course_links = driver.find_elements(By.CSS_SELECTOR, "a.regular")

    # Goes deeper link list and deletes the url to the course catalog root (tree root)
    for link in deeper_links:
        title = link.get_attribute("title")
        if title and "Vorlesungsverzeichnis" in title:
            continue
        # Add to the result link list with a "d" indicating that the url is not a course url
        current_link_list.append([link.get_attribute("href"),"d"])

    # Goes through the course link list and deletes specifed elements that are no courses
    for link in course_links:
        # Deletes the Seitenansicht
        title = link.get_attribute("title")
        if title and "zur Seitenansicht" in title:
            continue
        # Deletes the url to the start site
        href = link.get_attribute("href")
        if href and ("state=user" in href or "category=veranstaltung.browse" in href):
            continue
        # Add to the result link list with a "r" indicating that the url is a course url
        current_link_list.append([link.get_attribute("href"),"r"])

    return current_link_list

def get_semester_list():
    """
    Retrieves a list of available semesters for course lookup.

    Returns:
        list: A list of semester names (e.g., ["Winter 2023/24", "Sommer 2023"]).
    """
    # Initialize the driver with the semester url
    driver = start_driver(url= "https://qis.server.uni-frankfurt.de/qisserver/rds?state=change&type=6&moduleParameter=semesterSelect&nextdir=change&next=SearchSelect.vm&subdir=applications&targettype=7&targetstate=change&getglobal=semester#W")

    # Find all <a> elements with class "regular" that contain semester names
    semester_elements = driver.find_elements(By.CSS_SELECTOR, 'a.regular')

    # Extract and filter the semester names
    semesters = [element.text.strip() for element in semester_elements if
                 "Sommer" in element.text or "Winter" in element.text]

    return semesters

def scrape_institutes(driver: WebDriver, url: str = "https://qis.server.uni-frankfurt.de/qisserver/rds?state=wtree&search=lk&trex=step&rootlk20251=1&P.vx=kurz") -> None:
    """
     Scrapes all information about individuals and their affiliated institutes from the personal page of
     the QIS Goethe University Frankfurt

     Parameters:
         driver (WebDriver): Intialized Selenium driver
         url (str): URL of personal site of QIS Goethe University Frankfurt
     """
    # Declare result dataframe and intialize url with the driver
    result_dataframe = pd.DataFrame(columns=["Person","Institut"])
    driver.get(url)

    # Find faculty links
    fachbereich_links = driver.find_elements(By.CLASS_NAME, "ueb")
    fachbereich_url = [link.get_attribute("href") for link in fachbereich_links]
    personal_url = []
    # Now iterate over founded fachbereiche urls
    for fach_url in fachbereich_url:
        # Try to open them with driver
        try:
            driver.get(fach_url)
        except (TimeoutException, ReadTimeoutError):
            pass
        print(fach_url)

        # Now get the links to the persons in each Fachbereich
        personen_links = driver.find_elements(By.CLASS_NAME, "ver")
        # Extract their urls
        personal_url = personal_url + [link.get_attribute("href") for link in personen_links]
    # Now iterate over each of the founded urls
    for person_url in personal_url:
        # Load them in the driver
        try:
            driver.get(person_url)
        except (TimeoutException, ReadTimeoutError):
            pass
        print(person_url)
        # Add the information for each person to the result dataframe
        result_dataframe.loc[len(result_dataframe)] = get_institut_by_person(driver)

    # At the end create Database folder and export the result csv to it
    os.makedirs("Database", exist_ok=True)
    result_dataframe.to_csv("Database/Insitutsliste_Goethe_Uni.csv")

def get_institut_by_person(driver: WebDriver) -> Tuple[str, str]:
    """
    Extracts a person's name and associated institute from their profile QIS page.

    Parameters:
        driver (WebDriver): Selenium WebDriver instance with given profile page loaded.

    Returns:
        Tuple[str, str]: A tuple containing the person's formatted name and their institute.
    """
    # Retrieve name information and save them with < as seperator
    try:
        nachname = driver.find_element(By.XPATH, f"//th[contains(text(), '{"Nachname"}')]/following-sibling::td").text.strip() + " <"
    except:
        nachname = ""
    try:
        vorname = driver.find_element(By.XPATH, f"//th[contains(text(), '{"Vorname"}')]/following-sibling::td").text.strip()
    except:
        vorname = ""
    try:
        title = "< " + driver.find_element(By.XPATH, f"//th[contains(text(), '{"Titel"}')]/following-sibling::td").text.strip()
    except:
        title = ""
    try:
        academic = "< " + driver.find_element(By.XPATH, f"//th[contains(text(), '{"Akad. Grad"}')]/following-sibling::td").text.strip() + "<"
    except:
        academic = ""

    name_format = f"{nachname} {vorname} {title} {academic}"

    # Retrieve institute information
    try:
        institute = driver.find_element(By.XPATH, '//div[contains(@style, "padding-left: 20px")]/a')
        first_institute = institute.text.strip()
    except:
        first_institute = "Bitte manuell einfügen"  # Default value if institute is not found

    return (name_format,first_institute)


def scrape_semester(semester: str) -> None:
    """Scrapes course data for a given semester.
    This function initializes a Selenium WebDriver and retrieves the course catalog for
    the specified semester (root of tree). Then performs the dfs scpraing function on the tree

    Parameters:
        semester (str): The semester to be scraped (e.g., "WS2024").
    """
    driver=start_driver()
    course_cat = get_course_catalog(semester,driver)
    dfs_course_catalog(course_cat,driver,semester)

def scrape_personal() -> None:
    """Scrapes personal-related data from the frankfurt university QIS website.

    This function initializes a Selenium WebDriver and starts the scraping function for personal and their institutes
    """
    driver=start_driver()
    scrape_institutes(driver)


#semesterliste = ["Winter 2024/25","Winter 2023/24","Sommer 2023","Winter 2022/23","Sommer 2022"]
#for semester in semesterliste:
 #   scrape_semester(semester)