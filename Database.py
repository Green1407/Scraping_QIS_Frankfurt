"""This file creates and handles operations on the course data dataframe.
The data is read from a directory with csv files and consolidated into a single Pandas DataFrame. Then other data
operations are performed e.g. get a list of unique lecturers, delete double courses and redunant data..."""

import os
import ast

import pandas as pd

def read_institue_data() -> pd.DataFrame:
    """
    Reads the personal and institute .csv from the database folder and returns it as dataframe

    Returns:
        institute_df (pd.DataFrame): DataFrame with the information about the institute of each lecturer
    """
    institute_df = pd.read_csv("Database/Insitutsliste_Goethe_Uni.csv", encoding="utf-8")
    institute_df["Person"] = institute_df["Person"].apply(lecturer_format_name)

    return institute_df


def read_course_data(link: str)-> pd.DataFrame:
    """
    Reads and combines all .csv files from the scraping database directory.
    
    Parameters:
    link (str): Path to the scraping database directory containing .csv files.
    
    Returns:
    pd.DataFrame: A concatenated DataFrame of all .csv files found in the directory,
                  or an empty DataFrame if no .csv files are found.
    """
    dataframe = [
        pd.read_csv(os.path.join(link, f), encoding="utf-8", index_col=0).reset_index(drop=True)
        for f in os.listdir(link) if f.endswith(".csv") and "veranstaltung" in f.lower()
    ]
    return pd.concat(dataframe, ignore_index=True, sort=False) if dataframe else pd.DataFrame()
def lecturer_format_column(data: pd.DataFrame, column_name: str = "verantwortliche Lehrpersonen") -> pd.DataFrame:
    """
    Processes the Lehrpersonen column in the loaded DataFrame by converting the list of lecturers (string format)
    into actual lists (list format) and formatting lecturer names.

    Parameters:
    data (pd.DataFrame): The DataFrame of the combined scraped csv data.
    column_name (str, optional): The name of the column containing lecturer information.
                                 Defaults to "verantwortliche Lehrpersonen". Function can also be performed on the
                                 other lecturer column "Lehrpersonen"

    Returns:
    pd.DataFrame: The modified DataFrame with formatted lecturer names and updated "SWS" values.
    """
    # Convert string representations of lists into actual lists
    data[column_name] = data[column_name].apply(ast.literal_eval)

    # Ensure empty entries in the "verantwortliche Lehrpersonen" column are removed
    if column_name == "verantwortliche Lehrpersonen":
        data = data[data[column_name].apply(lambda x: x != [])].copy()

    # Format each lecturer's name in the list
    data[column_name] = data[column_name].apply(lambda row: [lecturer_format_name(entry[0]) for entry in row])

    # Replace "None" values in the "SWS" column with 0 and ensure integer type
    data['SWS'] = data['SWS'].replace("None", 0).fillna(0).astype(int)

    return data

def lecturer_format_name(name: str) -> str:
    """
    Formats a lecturer's name by rearranging name components split by '< '.

    Parameters:
    name (str): The original name string containing '< ' as a separator.

    Returns:
    str: The formatted name with components rearranged. In the original .csv the names are in the wrong order, so
    the single name components need to be rerranged
    """
    # Split the name at occurrences of '< ' to separate different parts
    parts = name.split("< ")

    # Remove any leading or trailing whitespace from each part
    parts = [p.strip() for p in parts]

    # Rearrange the name components based on the number of parts
    if len(parts) > 2:
        # If there are more than two parts, assume the format: "LastName < FirstName < Title"
        result_name = parts[2] + " " + parts[1] + " " + parts[0]
    elif len(parts) > 1:
        # If there are exactly two parts, assume the format: "LastName < FirstName"
        result_name = parts[1] + " " + parts[0]
    else:
        # If only one part exists, return it as is
        result_name = parts[0]
    return result_name

def lecturer_names_unique(data: pd.DataFrame) -> list[str]:
    """
    Extracts a list of unique lecturers from the 'verantwortliche Lehrpersonen' column and adds a default selection option.

    Parameters:
    data (pd.DataFrame): The DataFrame containing the column 'verantwortliche Lehrpersonen'

    Returns:
    List[str]: A sorted list of unique lecturer names with 'Keine Auswahl' as the first entry.
    """
    unique_names = sorted(set(name for sublist in data["verantwortliche Lehrpersonen"] for name in sublist))
    unique_names.insert(0, "Keine Auswahl")
    return unique_names

def fix_empty_courses(data: pd.DataFrame) -> pd.DataFrame:
    """
    Fixes empty entries in the 'verantwortliche Lehrpersonen' column by moving data from the 'Lehrpersonen'
    column if necessary. Functions is only executed if the user selects the corresponding select box in the GUI.

    Parameters:
    data (pd.DataFrame): The DataFrame containing the 'verantwortliche Lehrpersonen' and 'Lehrpersonen'.

    Returns:
    pd.DataFrame: The modified DataFrame with renewed lecturer assignments.
    """
    for index, row in data.iterrows():
        if row["verantwortliche Lehrpersonen"] == "[]":
            data.at[index, "verantwortliche Lehrpersonen"] = row["Lehrpersonen"]
            data.at[index, "Lehrpersonen"] = "[]"
    return data
def get_courses_by_person(person: str, data: pd.DataFrame, semester: str) -> pd.DataFrame:
    """
     Returns all courses in which the selected person is involved in the selected semester.

     Parameters:
     person (str): The name of the lecturer to filter by.
     data (pd.DataFrame): The DataFrame containing course information.
     semester (str): The semester filter; if "Alle Semester", no filtering is applied.

     Returns:
     pd.DataFrame: A filtered DataFrame with relevant course details.
     """
    # Filter courses where the selected person is listed in 'verantwortliche Lehrpersonen'
    filtered_data = data[data["verantwortliche Lehrpersonen"].apply(lambda x: person in x)]

    # Further filter by semester if a specific semester is selected
    if semester != "Alle Semester":
        filtered_data = filtered_data[filtered_data["Semester"] == semester]

    # Return only relevant course information columns
    return filtered_data[["Kursname", "SWS","Semester","Veranstaltungsart","Lehrpersonen"]]

def get_unique_semester(data: pd.DataFrame) -> list[str]:
    """
    Extracts a sorted list of unique semesters from the 'Semester' column and adds a default selection option.

    Parameters:
    data (pd.DataFrame): The DataFrame containing the 'Semester' column.

    Returns:
    List[str]: A sorted list of unique semesters with 'Alle Semester' as the first entry.
    """
    unique_semesters = sorted(set(data["Semester"]))
    unique_semesters.insert(0, "Alle Semester")
    return unique_semesters


def clean_data(data: pd.DataFrame) -> pd.DataFrame:
    """
    Takes the scraped course Data in Dataframe format and performs cleaning operations on the courses.
    Right now it deletes courses with 0 SWS and courses with "Entfällt" in the title.

    Parameters:
    data (pd.DataFrame): The DataFrame containing the scraped course information.

    Returns: the processed dataframe
    """
    cleaned_data = data
    cleaned_data = cleaned_data[cleaned_data['SWS'] != 0]
    cleaned_data = cleaned_data[~cleaned_data['Kursname'].str.contains('entfällt', case=False, na=False)]
    return cleaned_data


