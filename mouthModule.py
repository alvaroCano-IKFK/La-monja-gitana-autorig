import maya.cmds as cmds    
import guides_module
import controlsLibrary
from groups_module import ControlsGroups
from nodeCreator_module import NodeCreator

class MouthModule(object):
    def __init__(self, boca_surface="boca_surface", lip_mid="C_lip_mid", lip_end="L_lip_end", root_instance=None, rig_name="Character"):
        self.boca_surface = boca_surface
        self.lip_mid = lip_mid
        self.lip_end = lip_end
        self.group_maker = ControlsGroups()
        self.rig_name = rig_name
        self.root_instance = root_instance
        self.styles = {"mainFk": "circleControl"}
        self.prefix = rig_name

    def build(self):
        mid_lip = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["mainFk"],
            final_name=f"{self.prefix}_mid_LIP_CTRL"
        )
        mid_lip_grp = self.group_maker.create_rig_hierarchy(
            mid_lip, self.lip_mid, match_rotation=True, world_space=True
        )

        end_lip = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["mainFk"],
            final_name=f"{self.prefix}_end_LIP_CTRL"
        )
        end_lip_grp = self.group_maker.create_rig_hierarchy(
            end_lip, self.lip_end, match_rotation=True, world_space=True
        )

        local_off, local_trn = self.group_maker.create_space_tracking_hierarchy(
            space_base_name=f"{self.prefix}_mouthLocal",
            target_joint=end_lip_grp,
            parent_group=None
        )

        # --- Limpieza previa por si se rehace el build (evita nodos huérfanos) ---
        stale_nodes = cmds.ls(f"{self.prefix}_C_mouth_Local_*_multMatrix_*") + \
                      cmds.ls(f"{self.prefix}_C_mouth_Local_*_decomposeMatrix_*")
        if stale_nodes:
            cmds.delete(stale_nodes)

        # --- Creación de nodos vía NodeCreator ---
        mult_matrix_node = NodeCreator(
            side=self.prefix,
            node_type="multMatrix",
            base_name="mouth",
            name="Local",
            tag="CTRL",
            parent=None,
            custom_suffix=None
        ).create()

        decompose_matrix_node = NodeCreator(
            side=self.prefix,
            node_type="decomposeMatrix",
            base_name="mouth",
            name="Local",
            tag="CTRL",
            parent=None,
            custom_suffix=None
        ).create()

        # --- Conexiones ---
        cmds.connectAttr(f"{end_lip}.matrix", f"{mult_matrix_node}.matrixIn[0]")
        cmds.connectAttr(f"{mult_matrix_node}.matrixSum", f"{decompose_matrix_node}.inputMatrix")
        cmds.connectAttr(f"{decompose_matrix_node}.outputTranslate", f"{local_trn}.translate")
        cmds.connectAttr(f"{decompose_matrix_node}.outputRotate", f"{local_trn}.rotate")
        cmds.connectAttr(f"{decompose_matrix_node}.outputScale", f"{local_trn}.scale")

        return mid_lip_grp, end_lip_grp, local_off, local_trn