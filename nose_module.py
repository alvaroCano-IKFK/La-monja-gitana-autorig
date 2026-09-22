import maya.cmds as cmds
import control_library
import guides_module
from nodeCreator_module import NodeCreator


class NoseModule:

    def __init__(self):
        # Noms de les guies de referència
        self.guide_root = "nose_root_GUIDE"
        self.guide_tip = "nose_tip_GUIDE"
        self.guide_base_nostril_L = "base_nostril_L_GUIDE"
        self.guide_nostril_L = "nostril_L_GUIDE"

        # Noms dels joints definitius
        self.nose_root = "nose_root_JNT"
        self.nose_tip = "nose_tip_JNT"
        self.base_nostril_L = "base_nostril_L_JNT"
        self.nostril_L = "nostril_L_JNT"

    def _get_position(self, node_name):
        if cmds.objExists(node_name):
            return cmds.xform(node_name, q=True, ws=True, translation=True)
        else:
            cmds.warning(f"La guia '{node_name}' no existeix a la escena.")
            return [0, 0, 0]

    def create_nose_joints(self):
        cmds.select(clear=True)

        pos_root = self._get_position(self.guide_root)
        jnt_root = cmds.joint(name=self.nose_root, position=pos_root)

        pos_tip = self._get_position(self.guide_tip)
        jnt_tip = cmds.joint(name=self.nose_tip, position=pos_tip)

        cmds.select(jnt_root)
        pos_base_nostril = self._get_position(self.guide_base_nostril_L)
        jnt_base_nostril = cmds.joint(
            name=self.base_nostril_L, position=pos_base_nostril
        )

        pos_nostril = self._get_position(self.guide_nostril_L)
        jnt_nostril = cmds.joint(name=self.nostril_L, position=pos_nostril)

        cmds.joint(
            jnt_root,
            e=True,
            oj="xyz",
            sao="yup",
            ch=True,
            zso=True,
        )

        # Recomanat: posar l'orientació del joint final a zero
        cmds.joint(jnt_tip, e=True, oj="none")
        cmds.joint(jnt_nostril, e=True, oj="none")

        cmds.select(clear=True)

        return {
            "root": jnt_root,
            "tip": jnt_tip,
            "base_nostril": jnt_base_nostril,
            "nostril": jnt_nostril,
        }