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
import right_leg_module
import skinning_module
import build_module
import body_module
import limbModule
import twist_module
import spaceSwitching_module
import headSpace_module
import soft_module
import curvature_module
import mouthModule
import mirror_module


def run():
    # Esto obliga a Maya a leer los archivos del disco otra vez
    importlib.reload(spine_module)
    importlib.reload(guides_module)
    importlib.reload(ui_module)
    importlib.reload(limbModule)
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
    importlib.reload(spaceSwitching_module)
    importlib.reload(right_leg_module)
    importlib.reload(skinning_module)
    importlib.reload(build_module)
    importlib.reload(body_module)
    importlib.reload(limbs_module)
    importlib.reload(twist_module)
    importlib.reload(headSpace_module)
    importlib.reload(soft_module)
    importlib.reload(curvature_module)
    importlib.reload(mouthModule)
    importlib.reload(mirror_module)
    
    ui = ui_module.UI()
    ui.main_UI()