import maya.cmds as cmds
import control_library
import guides_module
from nodeCreator_module import NodeCreator


class NoseModule:

    def __init__(self, rig_name="rig", side="L"):

        self.side = side
        self.rig_name = rig_name
        self.prefix = f"{self.side}_{self.rig_name}_"
        self.node_creator = NodeCreator()

        # Noms de les guies (ajusta-ho a la teva convenció real)
        self.nose_root_guide = "nose_root_GUIDE"
        self.nose_tip_guide = "nose_tip_GUIDE"
        self.base_nostril_guide = f"base_nostril_{self.side}_GUIDE"
        self.nostril_guide = f"nostril_{self.side}_GUIDE"

        # Noms dels joints definitius
        self.nose_root_jnt = "nose_root_JNT"
        self.nose_tip_jnt = "nose_tip_JNT"
        self.base_nostril_jnt = f"base_nostril_{self.side}_JNT"
        self.nostril_jnt = f"nostril_{self.side}_JNT"
        self.nostril_jnt_dup = f"nostril_{self.side}_dup_JNT"

        # Controlador del nostril (un sol control per als dos joints)
        self.nostril_ctrl = f"nostril_{self.side}_CTRL"

        self.joints = []
        self.controls = []

    # ------------------------------------------------------------------
    # JOINTS
    # ------------------------------------------------------------------

    def _create_joint_from_guide(self, guide_name, joint_name):
        """Crea un joint a la posicio d'una guia."""
        if not cmds.objExists(guide_name):
            cmds.warning(f"La guia {guide_name} no existeix.")
            return None

        pos = cmds.xform(guide_name, q=True, ws=True, t=True)

        cmds.select(clear=True)
        jnt = cmds.joint(name=joint_name)
        cmds.xform(jnt, ws=True, t=pos)

        return jnt

    def create_nose_joints(self):
        """Crea els joints principals del nas a partir de la posicio de les guies."""
        cmds.select(clear=True)

        self.nose_root_jnt = self._create_joint_from_guide(
            self.nose_root_guide, self.nose_root_jnt
        )
        self.nose_tip_jnt = self._create_joint_from_guide(
            self.nose_tip_guide, self.nose_tip_jnt
        )
        self.base_nostril_jnt = self._create_joint_from_guide(
            self.base_nostril_guide, self.base_nostril_jnt
        )
        self.nostril_jnt = self._create_joint_from_guide(
            self.nostril_guide, self.nostril_jnt
        )

        self.joints = [
            self.nose_root_jnt,
            self.nose_tip_jnt,
            self.base_nostril_jnt,
            self.nostril_jnt,
        ]

        cmds.select(clear=True)
        return self.joints

    def duplicate_nostril_joint(self):
        """
        Duplica el joint del nostril mantenint exactament la mateixa posicio.
        parentOnly=True evita duplicar fills que pengin del joint original.
        """
        dup = cmds.duplicate(
            self.nostril_jnt, name=self.nostril_jnt_dup, parentOnly=True
        )[0]

        # Si el duplicat queda penjat com a fill de l'original, el traiem a world
        parent = cmds.listRelatives(dup, parent=True)
        if parent:
            cmds.parent(dup, world=True)

        self.nostril_jnt_dup = dup
        self.joints.append(dup)

        return dup

    # ------------------------------------------------------------------
    # CONTROLADORS
    # ------------------------------------------------------------------

    def create_controllers(self):
        """
        Crea el controlador del nostril amb control_library, col·locat
        a la posicio del joint de nostril.
        Ajusta els kwargs de create_control() a la teva llibreria real.
        """
        pos = cmds.xform(self.nostril_jnt, q=True, ws=True, t=True)

        nostril_ctrl = control_library.create_control(
            name=self.nostril_ctrl,
            shape="circle",
            size=1.0,
        )

        cmds.xform(nostril_ctrl, ws=True, t=pos)

        self.nostril_ctrl = nostril_ctrl
        self.controls.append(nostril_ctrl)

        return self.controls

    # ------------------------------------------------------------------
    # CONSTRAINTS
    # ------------------------------------------------------------------

    def constraint_joints_to_controllers(self):
        """
        Parent constraint dels dos joints del nostril (original + duplicat)
        cap al mateix controlador de nostril.
        """
        cmds.parentConstraint(
            self.nostril_ctrl, self.nostril_jnt, maintainOffset=True
        )
        cmds.parentConstraint(
            self.nostril_ctrl, self.nostril_jnt_dup, maintainOffset=True
        )

    # ------------------------------------------------------------------
    # BUILD COMPLET
    # ------------------------------------------------------------------

    def build(self):
        """Executa tot el modul en ordre."""
        self.create_nose_joints()
        self.duplicate_nostril_joint()
        self.create_controllers()
        self.constraint_joints_to_controllers()

        return self.joints, self.controls