import maya.cmds as cmds
import control_library
import guides_module
from nodeCreator_module import NodeCreator


class NoseModule:

    def __init__(self, rig_name="rig", side="L"):

        self.side = side
        self.rig_name = rig_name
        self.prefix = f"{self.side}_{self.rig_name}_"
        # Prefix de centre: les peces uniques (nose_root, nose_tip,
        # base_nostril) fan servir "C_" en lloc del side, encara que el
        # modul s'instancii un cop per L i un cop per R.
        self.center_prefix = f"C_{self.rig_name}_"
        self.node_creator = NodeCreator()

        # Noms de les guies (ajusta-ho a la teva convenció real)
        self.nose_root_guide = f"{self.center_prefix}noseRoot_GUIDE"
        self.nose_tip_guide = f"{self.center_prefix}noseTip_GUIDE"
        # base_nostril es una peca central unica entre els dos nostrils:
        # porta center_prefix (C_), NO side, perque nomes n'hi ha d'haver
        # un al centre encara que el modul s'instancii per L i per R.
        self.base_nostril_guide = f"{self.center_prefix}nostrilBase_GUIDE"
        self.nostril_guide = f"{self.prefix}nostril_GUIDE"

        # Noms dels joints definitius
        self.nose_root_jnt = f"{self.center_prefix}noseRoot_JNT"
        self.nose_tip_jnt = f"{self.center_prefix}noseTip_JNT"
        self.base_nostril_jnt = f"{self.center_prefix}nostrilBase_JNT"
        self.nostril_jnt = f"{self.prefix}nostril_JNT"
        self.nostril_jnt_dup = f"{self.prefix}nostril_dup_JNT"

        # Controladors: el nostril te el seu (per side), i base_nostril
        # te el seu propi controlador de centre, NO es penja al root.
        self.nostril_ctrl = f"{self.prefix}nostril_CTRL"
        self.base_nostril_ctrl = f"{self.center_prefix}nostrilBase_CTRL"

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

        # base_nostril es unic i de centre: si ja el va crear l'altra
        # instancia del modul (l'altre side), el reutilitzem tal qual.
        if cmds.objExists(self.base_nostril_jnt):
            cmds.warning(
                f"{self.base_nostril_jnt} ja existeix, es reutilitza (joint de centre)."
            )
        else:
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
        Crea el controlador del nostril (per side) i el de base_nostril
        (de centre, nomes un). Ajusta els kwargs de create_control() a la
        teva llibreria real.
        """
        # Controlador del nostril (per side)
        nostril_pos = cmds.xform(self.nostril_jnt, q=True, ws=True, t=True)

        nostril_ctrl = control_library.create_control(
            name=self.nostril_ctrl,
            shape="circle",
            size=1.0,
        )
        cmds.xform(nostril_ctrl, ws=True, t=nostril_pos)

        self.nostril_ctrl = nostril_ctrl
        self.controls.append(nostril_ctrl)

        # Controlador de base_nostril (centre): nomes es crea un cop, si
        # l'altra instancia del modul (l'altre side) ja el va crear, el
        # reutilitzem en lloc de duplicar-lo.
        if cmds.objExists(self.base_nostril_ctrl):
            cmds.warning(
                f"{self.base_nostril_ctrl} ja existeix, es reutilitza (control de centre)."
            )
        else:
            base_nostril_pos = cmds.xform(self.base_nostril_jnt, q=True, ws=True, t=True)

            base_nostril_ctrl = control_library.create_control(
                name=self.base_nostril_ctrl,
                shape="circle",
                size=1.0,
            )
            cmds.xform(base_nostril_ctrl, ws=True, t=base_nostril_pos)

            self.base_nostril_ctrl = base_nostril_ctrl
            self.controls.append(base_nostril_ctrl)

        return self.controls

    # ------------------------------------------------------------------
    # CONSTRAINTS
    # ------------------------------------------------------------------

    def constraint_joints_to_controllers(self):
        """
        Parent constraint dels dos joints del nostril (original + duplicat)
        cap al mateix controlador de nostril, i del joint de base_nostril
        cap al seu propi controlador de centre (no al root).
        """
        cmds.parentConstraint(
            self.nostril_ctrl, self.nostril_jnt, maintainOffset=True
        )
        cmds.parentConstraint(
            self.nostril_ctrl, self.nostril_jnt_dup, maintainOffset=True
        )

        # base_nostril nomes cal constrenyer-lo un cop; si l'altra
        # instancia (l'altre side) ja ho ha fet, no ho tornem a fer.
        existing_constraints = cmds.listRelatives(
            self.base_nostril_jnt, type="parentConstraint"
        ) or []
        if not existing_constraints:
            cmds.parentConstraint(
                self.base_nostril_ctrl, self.base_nostril_jnt, maintainOffset=True
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