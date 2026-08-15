import maya.cmds as cmds
import guides_module
import controlsLibrary
from groups_module import ControlsGroups
from nodeCreator_module import NodeCreator
import rigRoot_module

class EyebrowsModule(object):
    """
    Mòdul per construir el rig de les celles de manera modular,
    rebent guies de referència de l'escena (igual que la boca).
    """
    def __init__(self, eyebrow_surface="eyebrow_surface", 
                 brow_mid="C_brow_mid", 
                 brow_end="L_brow_end", 
                 root_instance=None, 
                 rig_name="Character", 
                 side="L"):
        
        self.eyebrow_surface = eyebrow_surface
        self.brow_mid = brow_mid
        self.brow_end = brow_end
        self.root_instance = root_instance
        self.rig_name = rig_name
        self.side = side
        
        # Prefix segons el costat (ex: L_Character o R_Character)
        self.prefix = f"{self.side}_{self.rig_name}"
        self.group_maker = ControlsGroups()
        self.styles = {"mainFk": "circleControl"}

    def build(self):
        """Construeix els controls i connexions de la cella."""
        print(f"Construint mòdul de celles per al costat: {self.side}...")

        # 1. Crear control principal o de referència per a la cella
        ctl_name = f"{self.prefix}_EYEBROW_CTRL"
        
        if not cmds.objExists(ctl_name):
            ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["mainFk"],
                final_name=ctl_name
            )
            
            # Crear jerarquia de rig fent match amb la guia corresponent (per exemple, brow_mid o brow_end)
            target_guide = self.brow_end if self.side in ["L", "R"] else self.brow_mid
            
            ctrl_grp = self.group_maker.create_rig_hierarchy(
                ctrl, target_joint=target_guide, match_rotation=True, world_space=True
            )
            
            # Emparentar al grup principal del rig o de control facial si escau
            controls_grp = f"{self.rig_name}_controls_GRP"
            if cmds.objExists(controls_grp):
                cmds.parent(ctrl_grp, controls_grp)

        print(f"Mòdul de celles ({self.side}) completat correctament.")
        return ctl_name