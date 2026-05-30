import master_module
import importlib
importlib.reload(master_module)
print("Hola caracola")

master_module.run()