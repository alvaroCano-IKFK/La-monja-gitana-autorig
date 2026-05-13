import maya.cmds as cmds
from functools import partial 
import os
import math
import json
import guides_module
import spine_module
import limbs_module
import reorient_module
import mirror_module


class UI(object):

    def __init__(self,name = "AutoRig_Master"):
        self.name = name
        self.character = guides_module.CharacterGuides()
        self.reorienter = reorient_module.Reorienter()
        self.mirror_guides = mirror_module.Mirror()

    def main_UI(self):
        window_name = self.name
        if cmds.window(window_name, exists=True): cmds.deleteUI(window_name)
        
        win = cmds.window(window_name, title="AutoRig Master", w=300)
        main_layout = cmds.columnLayout(adj=True)
        
        # SECCIÓN DE PARTES
        cmds.frameLayout(l="1. Create Guides", marginHeight=5)
        cmds.rowLayout(nc=2, ad2=True)
        #cmds.button(l="Arm Guides", c=default_arm_guides, h=40)
        cmds.button(l="Guides",c=lambda x: self.character.create_guides(), h=40)
        cmds.setParent("..")
        
        # SECCIÓN DE CONSTRUCCIÓN
        cmds.frameLayout(l="2. Build Rig", marginHeight=5)
        cmds.button(l="BUILD", c=lambda x: self.character.build(), bgc=(0.3, 0.5, 0.3))      
        cmds.frameLayout(l="3. Data Management", collapsable=True, cl=True)
        cmds.columnLayout(adj=True)
        cmds.button(l="Export Guides")
        cmds.separator(h=10)
        cmds.button(l="Import Guides")
        cmds.separator(h=10)
        cmds.button(l="Reorient Arm Guides", c=lambda x: self.reorienter.run_reorient())        
        cmds.separator(h=10)
        cmds.button(l="Mirror", c= lambda x: self.mirror_guides.mirror())

        
        cmds.showWindow(win)
    
if __name__ == "__main__":
    ui_instance = UI()  # Crear una instancia de la clase UI
    ui_instance.main_UI()  # Llamar al método main_UI 