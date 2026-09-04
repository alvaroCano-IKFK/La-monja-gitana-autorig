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
import build_module
import eyes_module


class UI(object):

    def __init__(self,name = "AutoRig_Master"):
        self.name = name
        self.character = guides_module.CharacterGuides()
        self.reorienter = reorient_module.Reorienter()
        self.mirror_guides = mirror_module.Mirror()
        self.builder = build_module.BuildRig()

        # Campos de la seccion de sets de loop, para poder leerlos desde los botones
        self.rig_name_field = None
        self.side_menu = None

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
        cmds.button(l="BUILD", c=lambda x: self.builder.build(), bgc=(0.3, 0.5, 0.3))      
        cmds.frameLayout(l="3. Data Management", collapsable=True, cl=True)
        cmds.columnLayout(adj=True)
        cmds.button(l="Export Guides")
        cmds.separator(h=10)
        cmds.button(l="Import Guides")
        cmds.separator(h=10)
        cmds.button(l="Reorient Arm Guides", c=lambda x: self.reorienter.run_reorient())        
        cmds.separator(h=10)
        cmds.button(l="Mirror", c= lambda x: self.mirror_guides.mirror())

        # SECCION DE SETS DE LOOP DE LOS OJOS
        # Volvemos al layout raiz antes de abrir la seccion, para no colgarla
        # dentro del frameLayout anterior.
        cmds.setParent(main_layout)
        cmds.frameLayout(l="4. Eye Loop Sets", collapsable=True, cl=True, marginHeight=5)
        cmds.columnLayout(adj=True)

        self.rig_name_field = cmds.textFieldGrp(
            l="Rig Name", tx="Character", cw2=(70, 150), adj=2)

        self.side_menu = cmds.optionMenuGrp(l="Side", cw2=(70, 150))
        cmds.menuItem(l="L")
        cmds.menuItem(l="R")

        cmds.separator(h=8)
        cmds.text(l="Selecciona el loop del borde del parpado y guardalo:", al="left")
        cmds.button(l="Save Upper Loop Set",
                    c=lambda x: self._save_loop_set(upper=True))
        cmds.separator(h=4)
        cmds.button(l="Save Lower Loop Set",
                    c=lambda x: self._save_loop_set(upper=False))

        cmds.separator(h=8)
        cmds.button(l="Check Loop Sets", c=lambda x: self._report_loop_sets())

        cmds.setParent("..")
        cmds.setParent("..")

        cmds.showWindow(win)

    # ------------------------------------------------------------------
    # SETS DE LOOP DE LOS OJOS
    # ------------------------------------------------------------------
    def _get_eye_naming(self):
        """
        Lado y nombre de rig que hay puestos en la ventana. Son solo para
        construir el nombre del set: la configuracion del build sigue viviendo
        en build_module, aqui no se guarda nada.
        """
        rig_name = cmds.textFieldGrp(self.rig_name_field, q=True, tx=True) or "Character"
        side = cmds.optionMenuGrp(self.side_menu, q=True, v=True) or "L"

        return side, rig_name.strip()

    def _save_loop_set(self, upper=True):
        """
        Guarda la seleccion como set de loop con el nombre de convencion, para
        no tener que escribirlo a mano y arriesgarse a que el modulo no lo
        encuentre y se caiga al contador sin avisar.
        """
        side, rig_name = self._get_eye_naming()

        return eyes_module.EyesModule.save_loop_set(side, rig_name, upper=upper)

    def _report_loop_sets(self):
        """
        Imprime que sets hay y cuantos joints saldrian, sin construir nada.
        """
        side, rig_name = self._get_eye_naming()

        return eyes_module.EyesModule.report_loop_sets(side, rig_name)
    
if __name__ == "__main__":
    ui_instance = UI()  # Crear una instancia de la clase UI
    ui_instance.main_UI()  # Llamar al método main_UI