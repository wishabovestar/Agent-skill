import sys
HERMES = r"C:/Users/Administrator/AppData/Local/hermes/hermes-agent"
sys.path.insert(0, HERMES)
import ruamel.yaml
print("T21_OK", ruamel.yaml.__file__)
