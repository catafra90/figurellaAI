import pandas as pd

def drop_unwanted_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove rows where First Name or Appointment Status indicates 'busy',
    and any stray header rows captured as data.
    """
    mask_busy_name = (
        df['First Name'].astype(str)
          .str.strip().str.lower()
          .str.startswith('busy')
    )
    mask_busy_status = (
        df['Appointment Status'].astype(str)
          .str.strip().str.lower()
          .eq('busy')
    )
    mask_header = (
        (df['First Name'] == 'Name') & (df['Last Name'] == 'Surname')
    ) | (df['Appointment Status'] == 'Appointment Status')

    return df[~(mask_busy_name | mask_busy_status | mask_header)].reset_index(drop=True)
