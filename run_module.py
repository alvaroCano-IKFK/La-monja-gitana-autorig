import master_module
import importlib
importlib.reload(master_module)
print("Hola")

master_module.run()