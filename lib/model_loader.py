import os
import torch
import sys
import json

print("Aktueller Arbeitsordner:", os.getcwd())

# Pfad zur JSON-Konfigurationsdatei
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
config_path = os.path.join(project_root, 'aasist', 'config', 'AASIST.conf')
print(config_path)

with open(config_path, 'r') as f:
    config = json.load(f)

model_config = config["model_config"]

# AASIST Pfad ins System einfügen
aasist_path = os.path.join(project_root, 'aasist')
sys.path.append(aasist_path)

from models.AASIST import Model

device = "cuda" if torch.cuda.is_available() else "cpu"

# Modell initialisieren
model = Model(model_config).to(device)

# Pfad zum Modellgewicht
model_path = os.path.join(project_root, 'models', 'weights', 'AASIST.pth')

# Gewichte laden
model.load_state_dict(torch.load(model_path, map_location=device))
model.eval()

print("Modell erfolgreich geladen.")

# Exportiere das Modell, damit andere Dateien es importieren können
def get_model():
    return model

def get_device():
    return device
