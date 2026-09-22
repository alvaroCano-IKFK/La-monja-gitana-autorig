import maya.cmds as cmds

import controlsLibrary
import module_specs
from groups_module import ControlsGroups


class NoseModule(module_specs.FeaturesMixin):
    """
    Nariz: un control de toda la nariz, uno de la punta y uno por aleta.

    Modulo de centro, como la boca: una sola instancia construye los dos lados.
    Las guias de las aletas solo existen en +X y el lado R se saca espejando la
    X aqui dentro, asi que no hace falta darle a MIRROR para la nariz.

    JERARQUIA DE CONTROLES
        noseRoot_CTRL            mueve la nariz entera
          noseTip_CTRL           la punta
          L/R nostril_CTRL       cada aleta

    Los controles de la punta y las aletas cuelgan del de la raiz, asi que
    mover la raiz se lleva todo. El grupo de controles sigue a head_CTRL si
    existe (igual que el resto de faciales).

    JOINTS
        Cada joint es un pasajero de su control (parentConstraint), en el
        mismo sitio que su guia. Todos terminan en _JNT, asi que skinning_module
        les saca su _ENV sin tocar nada.

        El nostril lleva un joint duplicado (nostrilDup_JNT) en la misma
        posicion y conducido por el mismo control, como en tu version
        original: se mantiene, pero si no lo usas para nada concreto al
        skinear, se puede quitar con la feature "nostril_dup".
    """

    MODULE_TYPE = "nose"

    # Guias. Sin sufijo _JNT a proposito: skinning_module duplica CUALQUIER
    # joint de la escena que acabe en JNT, y las guias acabarian como joints de
    # skin.
    ROOT_GUIDE = "nose_root"
    TIP_GUIDE = "nose_tip"
    BASE_NOSTRIL_GUIDE = "L_nose_nostrilBase"
    NOSTRIL_GUIDE = "L_nose_nostril"

    STYLES = {
        "root": "squareControl",
        "tip": "circleControl",
        "nostril": "circleControl",
    }

    # Tamano de cada control respecto al de la libreria (encima de la escala
    # global del rig). Las shapes de la libreria estan pensadas para brazos y
    # piernas: a tamano 1 una aleta de la nariz tapa media cara.
    SCALES = {
        "root": 0.35,
        "tip": 0.2,
        "nostril": 0.15,
    }

    def __init__(self, rig_name="Character", root_instance=None, features=None,
                 sides=("L", "R")):
        self._init_features(self.MODULE_TYPE, features)

        self.rig_name = rig_name
        self.root_instance = root_instance
        self.sides = tuple(sides)
        self.prefix = f"C_{rig_name}"

        self.group_maker = ControlsGroups()

        self.controls_grp = None
        self.joints_grp = None

        self.root_ctrl = None
        self.tip_ctrl = None
        self.nostril_ctrls = {}

        self.joints = []
        self.controls = []

    # ------------------------------------------------------------------
    # UTILIDADES
    # ------------------------------------------------------------------
    @staticmethod
    def _position(guide):
        return cmds.xform(guide, q=True, ws=True, t=True)

    @staticmethod
    def _mirror_x(position, side):
        """Las guias de las aletas solo existen en +X: el lado R las espeja."""
        x, y, z = position
        return [-abs(x), y, z] if side == "R" else [abs(x), y, z]

    def _make_joint(self, name, position):
        cmds.select(clear=True)
        joint = cmds.joint(p=position, n=name)
        cmds.parent(joint, self.joints_grp)
        self.joints.append(joint)
        return joint

    def _make_control(self, key, name, target, parent):
        """Control de la libreria con su jerarquia de grupos, sobre target."""
        ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.STYLES[key],
            final_name=name,
            scale=self.SCALES[key],
        )
        gen = self.group_maker.create_rig_hierarchy(ctrl, target)
        cmds.parent(gen, parent)
        self.controls.append(ctrl)
        return ctrl

    def missing_guides(self):
        """Guias que faltan en la escena. Vacio = se puede construir."""
        needed = [self.ROOT_GUIDE, self.TIP_GUIDE]
        if self.has("nostrils"):
            needed += [self.BASE_NOSTRIL_GUIDE, self.NOSTRIL_GUIDE]
        return [guide for guide in needed if not cmds.objExists(guide)]

    # ------------------------------------------------------------------
    # BUILD
    # ------------------------------------------------------------------
    def build(self):
        missing = self.missing_guides()
        if missing:
            cmds.warning(f"[Nose] Faltan guias: {', '.join(missing)}. "
                         f"Se salta la nariz.")
            return None

        controls_name = f"{self.prefix}_nose_controls_GRP"
        joints_name = f"{self.prefix}_nose_joints_GRP"
        for group in (controls_name, joints_name):
            if cmds.objExists(group):
                cmds.delete(group)

        self.controls_grp = cmds.group(em=True, n=controls_name)
        self.joints_grp = cmds.group(em=True, n=joints_name)

        # ---- raiz y punta ----
        root_jnt = self._make_joint(f"{self.prefix}_noseRoot_JNT",
                                    self._position(self.ROOT_GUIDE))
        tip_jnt = self._make_joint(f"{self.prefix}_noseTip_JNT",
                                   self._position(self.TIP_GUIDE))

        self.root_ctrl = self._make_control("root", f"{self.prefix}_noseRoot_CTRL",
                                            root_jnt, self.controls_grp)
        self.tip_ctrl = self._make_control("tip", f"{self.prefix}_noseTip_CTRL",
                                           tip_jnt, self.root_ctrl)

        cmds.parentConstraint(self.root_ctrl, root_jnt, mo=True)
        cmds.parentConstraint(self.tip_ctrl, tip_jnt, mo=True)

        # ---- aletas ----
        if self.has("nostrils"):
            for side in self.sides:
                self._build_nostril(side)
        else:
            print("[Nose] Aletas desactivadas en la receta.")

        self._organize()

        print(f"[Nose] Construida. Features: {', '.join(sorted(self.features))}")

        return self.joints, self.controls

    def _build_nostril(self, side):
        prefix = f"{side}_{self.rig_name}"

        base_pos = self._mirror_x(self._position(self.BASE_NOSTRIL_GUIDE), side)
        nostril_pos = self._mirror_x(self._position(self.NOSTRIL_GUIDE), side)

        base_jnt = self._make_joint(f"{prefix}_nostrilBase_JNT", base_pos)
        nostril_jnt = self._make_joint(f"{prefix}_nostril_JNT", nostril_pos)

        ctrl = self._make_control("nostril", f"{prefix}_nostril_CTRL",
                                  nostril_jnt, self.root_ctrl)
        self.nostril_ctrls[side] = ctrl

        # La base sigue a la raiz de la nariz; la aleta, a su control.
        cmds.parentConstraint(self.root_ctrl, base_jnt, mo=True)
        cmds.parentConstraint(ctrl, nostril_jnt, mo=True)

        if self.has("nostril_dup"):
            dup_jnt = self._make_joint(f"{prefix}_nostrilDup_JNT", nostril_pos)
            cmds.parentConstraint(ctrl, dup_jnt, mo=True)

    def _organize(self):
        """
        Primero se emparenta y DESPUES se constrine, como en neck_module: los
        grupos van a su sitio final en el outliner y solo entonces se enganchan
        a la cabeza.
        """
        if self.root_instance is not None:
            local_ctl = getattr(self.root_instance, "localCtl", None)
            if local_ctl and cmds.objExists(local_ctl):
                cmds.parent(self.controls_grp, local_ctl)

            rig_grp = f"{self.root_instance.rig_name}_rig_GRP"
            if cmds.objExists(rig_grp):
                cmds.parent(self.joints_grp, rig_grp)

        head_ctrl = f"{self.rig_name}_head_CTRL"
        if cmds.objExists(head_ctrl):
            cmds.parentConstraint(head_ctrl, self.controls_grp, mo=True)
        else:
            cmds.warning("[Nose] No hay head_CTRL: la nariz no seguira a la "
                         "cabeza. Anade Neck al arbol.")