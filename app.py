"""
This module defines the Streamlit-based GUI for the application.
It manages all frontend elements, including select boxes, buttons, and informational text.
Additionally, it interacts with other modules by performing data loading, processing, and exporting on users choice.
"""

from typing import Tuple, Any
import time

import pandas as pd
import streamlit as st

import scraper
import Database
import toOpenOffice
import scraper_request_bf

def reset_filtered_df() -> None:
    """
    Resets the stored filtered DataFrame in the Streamlit session state. This function is typically used when a
    new person is selected, ensuring that previous filter results do not persist across selections.
    """
    st.session_state["filtered_df"] = pd.DataFrame()

def load_data(bool_empty: bool) -> Tuple[pd.DataFrame, list[str], list[str], pd.DataFrame]:
    """
    Loads the current data and returns it.

    Parameters:
        bool_empty (bool): True, when selectbox 3 is selected. If true then combines "Lehrpersonen" und
        "verantwortliche Lehrpersonen" column

    Returns:
            - current_data (pd.Dataframe): The current data loaded from the .csv scraped data directory.
            - unique_names (list[str]): The list of unique lecturer names.
            - unique_semesters (list[str]): The list of unique available semesters.
            - institute_data (pd.DataFrame): Dataframe with the institute Data for each lecturer
    """
    current_data, unique_names, unique_semesters = refresh_data(bool_empty)

    institute_data = Database.read_institue_data()

    return current_data, unique_names, unique_semesters, institute_data


def refresh_data(bool_empty: bool) -> Tuple[pd.DataFrame, list[str], list[str]]:
    """
    Loads and processes the course data from the database.

    Parameters:
        bool_empty (bool): If True, courses with no responsible lecturer are processed for corrections.

    Returns:
        Tuple[Any, Any, Any]: A tuple containing:
            - get_data (pd.DataFrame): The processed combined dataset as pandas dataframe.
            - unique_names (list[str]): A list of unique lecturer names.
            - unique_semesters (list[str]): A list of unique semesters.
    """
    # Load course data from the database
    get_data = Database.read_course_data("Database/")
    print("refreshed")
    # Optionally process empty courses if enabled
    if bool_empty == True:
        get_data = Database.fix_empty_courses(get_data)

    # Format the lecturer columns to ensure consistent data
    get_data = Database.lecturer_format_column(get_data)
    get_data = Database.lecturer_format_column(get_data, column_name="Lehrpersonen")

    # Extract unique lecturer names and semester values
    unique_name = Database.lecturer_names_unique(get_data)
    unique_semesters = Database.get_unique_semester(get_data)

    return get_data, unique_name, unique_semesters


def display_filters(unique_names: list[str], unique_semesters: list[str]) -> Tuple[str, str]:
    """
    Displays selection options for semester and responsible lecturers and return the current selection.

    Parameters:
        unique_names (list[str]): A list of unique lecturer names.
        unique_semesters (list[str]): A list of available semesters.

    Returns:
        Tuple[str, str]: A tuple containing:
            - semester (str): The selected semester.
            - selected_name (str): The selected lecturer's name.
    """
    col1, col2 = st.columns([1, 1])

    # Semester selection dropdown
    with col1:
        semester = st.selectbox("Wähle ein Semester:", unique_semesters,on_change=reset_filtered_df  )

    # Lecturer selection dropdown
    with col2:
        selected_name = st.selectbox(
            "Wähle eine Lehrperson:",
            unique_names,
            index=0,
            key="selected_person",  # Key für Session State
            on_change=reset_filtered_df  # Löscht die Tabelle, wenn sich die Auswahl ändert
        )

    # Store selections in Streamlit session state
    st.session_state["selected_name"] = selected_name
    st.session_state["semester"] = semester

    return semester, selected_name


def display_courses(selected_name: str, semester: str, current_data: pd.DataFrame, data_clean: bool, institute_data: pd.DataFrame) -> None:
    """
    Retrieves and displays the filtered course catalog for the selected lecturer as table in the GUI.
    This function fetches courses from the database, applies optional data cleaning,
    and displays the results in an interactive table. It also supports real-time updates
    when selections change and provides an export option.

    Parameters:
        selected_name (str): The name of the selected lecturer.
        semester (str): The selected semester.
        current_data (pd.Dataframe): The dataset containing all scraped course information.
        data_clean (bool): If True, the data will be cleaned before display.
        institute_data (pd.DataFrame): Dataset containing lecturer institute data

    Returns:
        None
    """

    # Initialize session state variables if they do not exist
    session_vars = ["filtered_df", "raw_filtered_df", "last_clean_state", "last_selected_name"]
    for var in session_vars:
        if var not in st.session_state:
            st.session_state[var] = pd.DataFrame() if "df" in var else None

    # Fetch course data if a lecturer is selected
    if selected_name != "Keine Auswahl":
        raw_df = Database.get_courses_by_person(selected_name, current_data, semester)
        st.session_state["raw_filtered_df"] = raw_df  # Store unprocessed data

        # Apply data cleaning if enabled
        filtered_df = Database.clean_data(raw_df) if data_clean else raw_df

        # Update session state only if data exists
        if not filtered_df.empty:
            st.session_state["filtered_df"] = filtered_df
        else:
            st.warning("Keine Kurse für diese Person gefunden.")
            st.session_state["filtered_df"] = pd.DataFrame()

        # Store current selection state to avoid redundant processing
        st.session_state["last_clean_state"] = data_clean
        st.session_state["last_selected_name"] = selected_name

    # Automatically update filtered data if selection or cleaning option changes
    if "raw_filtered_df" in st.session_state:
        if (st.session_state["last_clean_state"] != data_clean or
                st.session_state["last_selected_name"] != selected_name):
            raw_df = st.session_state["raw_filtered_df"]
            filtered_df = Database.clean_data(raw_df) if data_clean else raw_df

            st.session_state["filtered_df"] = filtered_df
            st.session_state["last_clean_state"] = data_clean
            st.session_state["last_selected_name"] = selected_name

    # Display filtered courses if available
    if not st.session_state["filtered_df"].empty and selected_name != "Keine Auswahl":
        st.write(f"Kurse von **{selected_name}**:")

        # Interactive table for editing and deleting rows
        edited_df = st.data_editor(
            st.session_state["filtered_df"],
            num_rows="dynamic",  # Allow row deletion
            hide_index=True
        )

        # Update session state if the table is modified
        if not edited_df.equals(st.session_state["filtered_df"]):
            st.session_state["filtered_df"] = edited_df

        # Word export button activates word export function with corresponding data
        word_export(selected_name, semester, st.session_state["filtered_df"], data_clean,institute_data)

def word_export(person: str, semester: str, filtered_df: pd.DataFrame,data_clean: bool,institute_data: pd.DataFrame) -> None:
    """
      Exports the filtered course data for the selected lecturer and semester as a Word document.

      Parameters:
          person (str): The name of the selected lecturer.
          semester (str): The selected semester.
          filtered_df (pd.Dataframe): The filtered dataset containing relevant course information for the selections.
          data_clean (bool): True if data clean option is selected.
          institute_data (pd.DataFrame): Dataframe containing lecturers institute data

      Returns:
          None
      """

    # Button to trigger Word export
    if st.button("Daten als Word exportieren"):
        # If data clean option is selected clean data before export
        if data_clean == True:
            filtered_df = Database.clean_data(filtered_df)
        # Call the Word export function and if success, show success messages
        toOpenOffice.fill_word(person,semester,filtered_df,institute_data)
        st.success("Daten wurden exportiert!")
        st.info("Alle Exporte werden im zugehörigen Python-Verzeichnis im 'Word_Exporte' Ordner gespeichert")


def word_export_all(
    selected_names: list[str],
    all_names: list[str],
    semester: str,
    current_data: pd.DataFrame,
    data_clean: bool,
    institute_data: pd.DataFrame
) -> None:
    """
    Exports course data for multiple selected lecturers as Word documents. Also shows live export progress.

    Parameters:
        selected_names (List[str]): A list of selected lecturer names. If "Alle" is selected, all lecturers are processed.
        all_names (List[str]): A list of all available lecturer names, this list will be used if "Alle" is selected.
        semester (str): The selected semester.
        current_data (pd.Dataframe): The dataset containing course information.
        data_clean (bool): If True, courses are processed before export.#
        institute_data(pd.DataFrame): Dataset containing lecturer institute information

    Returns:
        None
    """
    # Button to trigger Word export
    if st.button("Daten als Word Exportieren"):

        # Intialize counter for progress bar
        progress_counter = 0

        # Export for all lecturers if "Alle" is selected
        if selected_names == ["Alle"]:
            # Define progress bar
            st.subheader("Daten werden exportiert...")
            progress_bar = st.progress(0)
            for name in all_names:
                progress_counter += 1
                if data_clean == True:
                    toOpenOffice.fill_word(name, semester, Database.clean_data(Database.get_courses_by_person(name, current_data, semester)),institute_data)
                else:
                    toOpenOffice.fill_word(name, semester, Database.get_courses_by_person(name, current_data, semester),institute_data)

                # refresh progress
                progress_bar.progress(progress_counter/len(all_names))

            # Display success message
            st.success("Daten wurden exportiert!")
            st.info("Alle Exporte werden im zugehörigen Python-Verzeichnis im 'Word_Exporte' Ordner gespeichert")

        # Export if not all lecturers are selected
        elif selected_names:
            # Define progress bar
            st.subheader("Daten werden exportiert...")
            progress_bar = st.progress(0)
            for name in selected_names:
                progress_counter += 1
                if data_clean == True:
                    toOpenOffice.fill_word(name, semester, Database.clean_data(Database.get_courses_by_person(name, current_data, semester)),institute_data)
                else:
                    toOpenOffice.fill_word(name, semester, Database.get_courses_by_person(name, current_data, semester),institute_data)

                # refresh progress
                progress_bar.progress(progress_counter/len(selected_names))


            # Display success message
            st.success("Daten wurden exportiert!")
            st.info("Alle Exporte werden im zugehörigen Python-Verzeichnis im 'Word_Exporte' Ordner gespeichert")

        else:
            st.error("Bitte eine oder mehrere Lehrpersonen auswählen")

def scrape_buttons():
    """
    Creates scraping-related checkboxes and selection options in the sidebar. Scrapes the available semesters from
    the QIS site and let the user choose one of it. If the user presses the Scraping Starten button the scraper will
    start to scrape the all course information of the selected semester.

    Returns:
        None
    """
    with st.sidebar:
        # Checkbox to activate scraping tools
        scraping_aktiviert = st.checkbox("Scraping Tools aktivieren", key="scrape_checkbox", help="Diese Funktion ermöglicht das Scrapen von Daten für ein neues Semester aus dem QIS oder die Aktualisierung bestehender Semester. ACHTUNG: Für die Nutzung werden die Python-Bibliothek selenium, der selenium webdriver für Chrome sowie die entsprechende Google Chrome Webdriver-Erweiterung benötigt.")
        scraping_requests = st.checkbox("Scraping-Tools v2. aktivieren", key="scrape_requests_checkbox", help="Nutzt statt selenium, requests und BeatifulSoup. Hier wird kein Chrome Webbrowser mit Erweiterung benötigt und der Scraping Prozess ist deutlich schneller. ACHTUNG: Bei Nutzung eines VPN oder Proxy-Servers kann es zu Fehler beim Scrapen kommen")

        # Ensure that not both boxes are activated
        if scraping_aktiviert and scraping_requests:
            st.warning("Es kann jeweils nur ein Scraping-Tool ausgewählt werden.")
            both_activated = 1
        else:
            both_activated = 0

        if (scraping_aktiviert or scraping_requests) and both_activated == 0:
            # Creates load button and handles deactivation
            placeholder = st.empty()
            with placeholder:
                st.button("Lade Semester...", disabled=True)

            # Try to load the semester list, if not possible show error. In loading time show load bar
            try:
                if scraping_aktiviert:
                    semester_list = scraper.get_semester_list()
                elif scraping_requests:
                    semester_list = scraper_request_bf.get_semester_list()
                placeholder.empty()  # Deletes the load button
                semester = st.selectbox("Wähle ein Semester:", semester_list, key="scrape_select_semester")
                # Scraping starts, when the button is pressed
                if st.button("Scrapen der Veranstaltungen aus Semester " + semester + " starten"):
                    with st.spinner("Scraping läuft (Vorgang kann bis zu 2 Stunden dauern"
                                    ", für Fortschritt Konsole beachten)..."):
                        if scraping_aktiviert:
                            startzeit = time.perf_counter()
                            scraper.scrape_semester(semester)
                            endzeit = time.perf_counter()
                            print(endzeit - startzeit)
                        elif scraping_requests:
                            startzeit = time.perf_counter()
                            scraper_request_bf.scrape_semester(semester)
                            endzeit = time.perf_counter()
                            print(endzeit - startzeit)
                # If the other button is pressed personal and institute list will be scraped
                if st.button("Scrapen der Personen-/Einrichtungsliste starten"):
                    with st.spinner("Scraping läuft (Vorgang dauert etwa 30 Minuten"
                                    ", für Fortschritt Konsole beachten)..."):
                        if scraping_aktiviert:
                            startzeit = time.perf_counter()
                            scraper.scrape_personal()
                            endzeit = time.perf_counter()
                            print(endzeit - startzeit)
                        elif scraping_requests:
                            startzeit = time.perf_counter()
                            scraper_request_bf.scrape_personal()
                            endzeit = time.perf_counter()
                            print(endzeit - startzeit)
            except Exception as e:
                st.error(f"Fehler beim Scrapen: {e}")
    return

def checkbox_export_multiple() -> bool:
    """Allows multiple lecturers to be selected for Word export."""
    export_mode = st.checkbox("Mehrfachexport-Modus aktivieren?", value=False,
                              help="Aktivieren des Feldes erlaubt es mehrere Lehrpersonen gleichzeitig auszuwählen und die Word Dateien automatisch für jede der Lehrperson erstellen zu lassen. Die anpassbare Tabelle wird dann jedoch nicht mehr angzeigt.")
    return export_mode

def checkbox_data_cleaning() -> bool:
    """Enables automatic data cleaning for courses."""
    data_clean = st.checkbox("Automatische Datenverbesserung aktivieren?", value=False,
                             help="Durch Aktivieren dieses Feldes werden nach Möglichkeit identische Kurse, wie beispielsweise Vorlesungen und die dazugehörigen Klausuren, zusammengefasst. Zudem werden Veranstaltungen ohne Semesterwochenstunden (SWS) sowie doppelte Einträge entfernt.")
    return data_clean

def checkbox_empty_courses() -> bool:
    """Displays courses even if no responsible person is set in QIS."""
    empty_courses = st.checkbox("Kurse anzeigen, auch wenn Person laut QIS nicht verantwortlich?", value=False,
                                help="Standardmäßig wird eine Lehrperson nur dann als verantwortliche Person einer Lehrveranstaltung zugewiesen, wenn sie im QIS als 'verantwortlich' hinterlegt ist. Wird dieses Feld aktiviert, werden bei Veranstaltungen ohne explizit verantwortliche Personen im QIS die übrigen angegebenen Lehrpersonen als verantwortlich gesetzt.")
    return empty_courses

def add_title_logo() -> None:
    """Adds a title and logo to the Streamlit app with adjusted padding."""

    # Reduce top padding for better layout
    st.markdown(
        """
        <style>
        /* Reduziert den oberen Abstand der gesamten Streamlit-App */
        .block-container {
            padding-top: 45px !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # Create layout with title and logo
    col_logo, col_title = st.columns([4, 1])
    with col_logo:
        st.title("QIS-Scraping und Export Tool",help="Dieses Tool ermöglicht das semesterweise Auslesen von Vorlesungsdaten aus dem QIS der Goethe-Universität Frankfurt."
                                                     "Die extrahierten Daten werden als .csv-Dateien im Ordner 'Database' gespeichert und anschließend in das Programm geladen, "
                                                     "wo sie zu einem pandas DataFrame kombiniert werden. Nutzende können für jede Lehrperson eine Datei erstellen, die alle von ihr verantworteten Veranstaltungen enthält. "
                                                     "Dafür stehen verschiedene Optionen zur Verfügung, darunter Mehrfachauswahl, die Auswahl eines bestimmten Semesters und weitere Filtermöglichkeiten.")
    with col_title:
        st.image("GoetheUniLogo.png", width=150)

def run_gui() -> None:
    """
    Main function that controls the entire Streamlit GUI workflow.

    - Sets up the page layout.
    - Displays the title and logo.
    - Handles export modes and course selection.
    - Loads data based on user inputs.
    - Provides scraping and export options.
    """
    # Set up the page layout and logo
    st.set_page_config(
        page_title="QIS-Scraping Tool",
        page_icon="📚",
        layout="wide",
    )
    add_title_logo()

    # Creates the 3 select boxes for the user
    export_mode = checkbox_export_multiple()
    data_clean = checkbox_data_cleaning()
    empty_course_check = checkbox_empty_courses()


    if "data_loaded" not in st.session_state:
        # Intialize the data when no data was loaded before
        current_data, unique_names, unique_semesters, institute_data = load_data(empty_course_check)
        st.session_state.data_loaded = (current_data, unique_names, unique_semesters, institute_data)
        st.session_state.prev_empty_course_check = empty_course_check
    else:
        # If the empty course checkbox changes, reload the data with empty course check = 1
        if empty_course_check != st.session_state.prev_empty_course_check:
            current_data, unique_names, unique_semesters, institute_data = load_data(empty_course_check)
            st.session_state.data_loaded = (current_data, unique_names, unique_semesters, institute_data)
            st.session_state.prev_empty_course_check = empty_course_check
        else:
            # Else use the already loaded data
            current_data, unique_names, unique_semesters, institute_data = st.session_state.data_loaded

    # Data load operation at the start, also loads lists for available semester and lecturers
    unique_names_with_all = ["Alle"] + unique_names[1:]

    # **Export mode enabled: Multi-person export**
    if export_mode:
        # Create two-column layout for export selection
        col1, col2 = st.columns([1, 2])

        with col1:
            semester = st.selectbox("Wähle ein Semester:", unique_semesters[1:])

        with col2:
            selected_names = st.multiselect("Wähle mehrere Personen aus:", unique_names_with_all)

        # Export Word documents for multiple selected persons
        word_export_all(selected_names, unique_names_with_all[1:], semester, current_data,data_clean,institute_data)

        # Add additional scrape buttons in a separate column
        col2_exp = st.columns([1])[0]
        with col2_exp:
            scrape_buttons()

    # **Standard mode: Single-person selection**
    else:
        col1, col2 = st.columns([2, 1])

        with col1:
            semester, selected_name = display_filters(unique_names, unique_semesters)
            display_courses(selected_name, semester, current_data, data_clean,institute_data)

        with col2:
            scrape_buttons()


run_gui()



#NEXT STEPS
#1 Scraping.py nochmal überarbeiten +  GitHub hochladen
#Probleme: mehrere Verantwortliche Personen was tun? #Gar keine Verantwortliche Personen?