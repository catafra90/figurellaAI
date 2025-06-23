import pandas as pd
from mock_data import mock_clients

df = pd.DataFrame(mock_clients)
df.to_csv("client_list.csv", index=False)

print("✅ Exported to client_list.csv")

