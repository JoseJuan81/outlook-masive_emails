import pandas as pd
from pathlib import Path

contacts_dir = Path("./../contactos/")
all_contacts_files = contacts_dir.iterdir()

all_contacts = []

# Recorro todos los archivos dentro de la carpeta contactos para obtener solo aquellos con extensión .csv
for file in all_contacts_files:
    if file.is_file() and file.suffix == ".csv":
        content = pd.read_csv(file)
        all_contacts.append(content)
    

unified_contacts = pd.concat(all_contacts)
contacts = unified_contacts[["Nombre", "Correo"]]

print("====================")
print(f"Cantidad total de contactos = {len(contacts)}")
print("====================")
