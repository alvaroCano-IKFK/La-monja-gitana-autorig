import master_module
import importlib
importlib.reload(master_module)
print("Running master module")

master_module.run()