import ui_module
import guides_module
import spine_module
import importlib
import limbs_module
import controls_module
import fingers_module
import neck_module
import chest_module
import hip_module
import foot_module
import leg_module
import groups_module
import reorient_module
import controlsLibrary
import rigRoot_module
import arm_right_module
import right_leg_module
import skinning_module
import build_module
import body_module

#import clavicule_module

def run():
    # Esto obliga a Maya a leer los archivos del disco otra vez
    importlib.reload(spine_module)
    importlib.reload(guides_module)
    importlib.reload(ui_module)
    importlib.reload(limbs_module)
    importlib.reload(controls_module)   
    importlib.reload(fingers_module)
    importlib.reload(neck_module)
    importlib.reload(chest_module)
    importlib.reload(hip_module)
    importlib.reload(foot_module)
    importlib.reload (leg_module)
    importlib.reload(groups_module)
    importlib.reload(reorient_module)
    importlib.reload(controlsLibrary)
    importlib.reload(rigRoot_module)
    importlib.reload(arm_right_module)
    importlib.reload(right_leg_module)
    importlib.reload(skinning_module)
    importlib.reload(build_module)
    importlib.reload(body_module)
    
    ui = ui_module.UI()
    ui.main_UI()