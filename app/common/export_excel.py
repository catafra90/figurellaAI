import pandas as pd
from mock_data import mock_clients

# Convert list of dicts to DataFrame
df = pd.DataFrame(mock_clients)

# Export to Excel (.xlsx)
df.to_excel("client_list.xlsx", index=False, engine="openpyxl")

print("✅ Client list exported to client_list.xlsx")
