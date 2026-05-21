"""
arm_module.py
=============
Módulo unificado de brazo (L y R) para el autorig de Maya 2024.

Uso:
    arm_L = ArmModule(side="L", root_instance=root)
    arm_L.build()

    arm_R = ArmModule(side="R", root_instance=root, mirror_source=arm_L)
    arm_R.build()

Lógica general
--------------
Ambos lados construyen su esqueleto desde sus propias guías (L_* o R_*),
leyendo posición y jointOrient directamente de ellas — sin mirrorJoint.

El comportamiento "mariposa" viene del mirrorBehaviour_GRP (scaleX = -1)
que crea RigRoot. El lado R mete su grupo de controles bajo ese grupo,
lo que produce el movimiento simétrico sin necesidad de constraints extra.

Para los controles el lado R duplica y renombra el grupo del lado L
(forma shapes idénticas en espejo), luego recrea las constraints sobre
su propio esqueleto.
"""

import math
import re

import maya.cmds as cmds

import controlsLibrary
import groups_module
import nodeCreator_module
from nodeCreator_module import NodeCreator


# ---------------------------------------------------------------------------
# Constantes de naming
# ---------------------------------------------------------------------------

_CTRL_STYLES = {
    "mainIk":     "squareControl",
    "root":       "rootControl",
    "mainFk":     "circleControl",
    "switch":     "switchControl02",
    "poleVector": "poleVectorControl",
    "clavicule":  "claviculeControl",
}


# ---------------------------------------------------------------------------
# Helpers de naming
# ---------------------------------------------------------------------------

def _jnt(rig_name, side, part, suffix):
    """Arm_L, L, shoulder, bind  ->  Arm_L_L_shoulder_bind_JNT"""
    return f"{rig_name}_{side}_{part}_{suffix}_JNT"


def _ctrl(rig_name, label):
    """Arm_L, armIk  ->  Arm_L_armIk_CTRL"""
    return f"{rig_name}_{label}_CTRL"


def _grp(rig_name, label):
    return f"{rig_name}_{label}_GRP"


# ---------------------------------------------------------------------------
# ArmModule
# ---------------------------------------------------------------------------

class ArmModule:
    """
    Construye el rig de brazo para el lado indicado (L o R).

    Parámetros
    ----------
    side : "L" | "R"
    root_instance : RigRoot
        Aporta los grupos globales (rig_GRP, localCtl, mirror_grp).
    mirror_source : ArmModule | None
        Solo side="R": instancia del brazo L ya construido.
        Se usa para duplicar el grupo de controles.
    shoulder_guide / elbow_guide / wrist_guide / clavicule_guide : str
        Nombres de los joints guía. Por defecto "L_shoulder", "R_shoulder", etc.
    rig_name : str
        Prefijo del rig. Por defecto "Arm_L" / "Arm_R".
    """

    def __init__(self,
                 side="L",
                 root_instance=None,
                 mirror_source=None,
                 shoulder_guide=None,
                 elbow_guide=None,
                 wrist_guide=None,
                 clavicule_guide=None,
                 rig_name=None):

        self.side = side.upper()
        assert self.side in ("L", "R"), "side debe ser 'L' o 'R'"

        self.root_instance = root_instance
        self.mirror_source = mirror_source

        self.shoulder_guide  = shoulder_guide  or f"{self.side}_shoulder"
        self.elbow_guide     = elbow_guide     or f"{self.side}_elbow"
        self.wrist_guide     = wrist_guide     or f"{self.side}_wrist"
        self.clavicule_guide = clavicule_guide or f"{self.side}_clavicule"

        self.rig_name = rig_name or f"Arm_{self.side}"

        self._grp_maker = groups_module.ControlsGroups()

        self.bind_chain = []
        self.ik_chain   = []
        self.fk_chain   = []
        self.b_cl       = None
        self.main_grp   = None
        self.ik_handle  = None

    # -----------------------------------------------------------------------
    # Punto de entrada
    # -----------------------------------------------------------------------

    def build(self):
        """
        Construye el módulo completo.
        Ambos lados siguen el mismo pipeline; la diferencia está en
        cómo se orienta el esqueleto y dónde acaba el main_grp.
        """
        self._create_skeleton()   # Lee guías propias (L_* o R_*)
        self._create_groups()     # Grupos de organización
        self._build_ik()          # IK handle + controles IK
        self._build_fk()          # Controles FK
        self._build_switch()      # Switch IK/FK + visibilidad
        self._build_blends()      # Pair blends bind ← IK/FK

        if self.side == "R":
            self._mirror_controls_R()  # Duplica shapes del L y las reposiciona

        self._organize()
        print(f"[ArmModule] Build {self.rig_name} completo.")

    # -----------------------------------------------------------------------
    # 1. ESQUELETO  (igual para L y R, orientación desde las guías)
    # -----------------------------------------------------------------------

    def _create_skeleton(self):
        rn   = self.rig_name
        side = self.side

        # --- Posiciones world-space desde las guías ---
        pos_cl = cmds.xform(self.clavicule_guide, q=True, ws=True, t=True)
        pos_sh = cmds.xform(self.shoulder_guide,  q=True, ws=True, t=True)
        pos_el = cmds.xform(self.elbow_guide,      q=True, ws=True, t=True)
        pos_wr = cmds.xform(self.wrist_guide,      q=True, ws=True, t=True)

        # --- Crear joints de la cadena bind ---
        cmds.select(clear=True)
        b_cl = cmds.joint(n=_jnt(rn, side, "clavicule", "bind"), p=pos_cl)
        cmds.select(clear=True)
        b_sh = cmds.joint(n=_jnt(rn, side, "shoulder",  "bind"), p=pos_sh)
        cmds.select(clear=True)
        b_el = cmds.joint(n=_jnt(rn, side, "elbow",     "bind"), p=pos_el)
        cmds.select(clear=True)
        b_wr = cmds.joint(n=_jnt(rn, side, "wrist",     "bind"), p=pos_wr)
        cmds.select(clear=True)

        cmds.parent(b_sh, b_cl)
        cmds.parent(b_el, b_sh)
        cmds.parent(b_wr, b_el)

        # --- Orientación: copiar jointOrient de las guías ---
        # De este modo el lado R queda orientado igual que sus guías
        # (que ya tienen la orientación correcta para ese lado) sin
        # necesidad de mirrorJoint ni recalcular ejes.
        guide_map = {
            b_cl: self.clavicule_guide,
            b_sh: self.shoulder_guide,
            b_el: self.elbow_guide,
            b_wr: self.wrist_guide,
        }
        for jnt, guide in guide_map.items():
            jo = cmds.getAttr(f"{guide}.jointOrient")[0]
            cmds.setAttr(f"{jnt}.jointOrient", jo[0], jo[1], jo[2])

        # El lado L además recalcula automáticamente con orientJoint
        # (las guías L pueden venir sin orientar del módulo de guías)
        if side == "L":
            cmds.joint(b_cl, edit=True, oj="xyz", sao="yup", ch=True, zso=True)
            cmds.setAttr(f"{b_wr}.jointOrient", 0, 0, 0)

        # Para el lado R confiamos en que las guías R_* ya están orientadas
        # correctamente (bien a mano, bien con un paso de orientación previo
        # en el módulo de guías). Si las guías R tienen jointOrient=0 el
        # esqueleto quedará sin orientar; en ese caso puedes forzar la misma
        # lógica que el L descomentando las dos líneas siguientes:
        # else:
        #     cmds.joint(b_cl, edit=True, oj="xyz", sao="yup", ch=True, zso=True)
        #     cmds.setAttr(f"{b_wr}.jointOrient", 0, 0, 0)

        self.b_cl       = b_cl
        self.bind_chain = [b_sh, b_el, b_wr]

        # --- Duplicar para IK y FK ---
        self.ik_chain = self._duplicate_chain(b_sh, "ik")
        self.fk_chain = self._duplicate_chain(b_sh, "fk")

    def _duplicate_chain(self, bind_shoulder, suffix):
        """Duplica shoulder→elbow→wrist con el sufijo indicado."""
        rn   = self.rig_name
        side = self.side

        new_nodes = cmds.duplicate(bind_shoulder, rc=True)
        root = cmds.rename(new_nodes[0], _jnt(rn, side, "shoulder", suffix))
        children = cmds.listRelatives(root, ad=True, type="joint") or []
        children.reverse()
        el = cmds.rename(children[0], _jnt(rn, side, "elbow", suffix))
        wr = cmds.rename(children[1], _jnt(rn, side, "wrist", suffix))
        cmds.setAttr(f"{wr}.jointOrient", 0, 0, 0)
        return [root, el, wr]

    # -----------------------------------------------------------------------
    # 2. GRUPOS DE ORGANIZACIÓN
    # -----------------------------------------------------------------------

    def _create_groups(self):
        rn = self.rig_name
        self.main_rig_grp = cmds.group(em=True, n=_grp(rn, "armControls"))
        self.main_grp     = self.main_rig_grp
        self.ik_grp       = cmds.group(em=True, n=_grp(rn, "ik"),       p=self.main_rig_grp)
        self.fk_grp       = cmds.group(em=True, n=_grp(rn, "fk"),       p=self.main_rig_grp)
        self.controls_grp = cmds.group(em=True, n=_grp(rn, "CONTROLS"), p=self.main_rig_grp)
        self.arm_grp      = cmds.group(em=True, n=_grp(rn, "arm"))

    # -----------------------------------------------------------------------
    # 3. IK SETUP
    # -----------------------------------------------------------------------

    def _build_ik(self):
        rn   = self.rig_name
        side = self.side

        # Preferred angle para que el solver sepa hacia dónde doblar el codo
        cmds.setAttr(f"{self.ik_chain[1]}.rotateY", 0.1)
        cmds.joint(self.ik_chain[0], edit=True, ch=True, spa=True)
        cmds.setAttr(f"{self.ik_chain[1]}.rotateY", 0)

        ik_h, _ = cmds.ikHandle(
            sj=self.ik_chain[0], ee=self.ik_chain[2],
            sol="ikRPsolver", n=f"{rn}_IKH"
        )
        self.ik_handle = ik_h

        # Control clavícula
        clav_ctl = controlsLibrary.create_control_from_lib(
            lib_name=_CTRL_STYLES["clavicule"],
            final_name=_ctrl(rn, "clavicule")
        )
        clav_gen = self._grp_maker.create_rig_hierarchy(clav_ctl, self.clavicule_guide)
        cmds.matchTransform(clav_gen, self.clavicule_guide)
        cmds.parentConstraint(clav_ctl, self.b_cl, mo=True)
        cmds.parent(clav_gen, self.controls_grp)
        self.clavicule_ctl = clav_ctl

        # Control raíz IK
        ik_root_ctl = controlsLibrary.create_control_from_lib(
            lib_name=_CTRL_STYLES["root"],
            final_name=_ctrl(rn, "armRoot")
        )
        ik_root_gen = self._grp_maker.create_rig_hierarchy(ik_root_ctl, self.ik_chain[0])
        cmds.pointConstraint(ik_root_ctl, self.ik_chain[0], mo=True)
        self.ik_root_gen = ik_root_gen

        # Control IK de muñeca
        ik_ctl = controlsLibrary.create_control_from_lib(
            lib_name=_CTRL_STYLES["mainIk"],
            final_name=_ctrl(rn, "armIk")
        )
        ik_ctl_gen = self._grp_maker.create_rig_hierarchy(ik_ctl, self.ik_chain[2])
        cmds.orientConstraint(ik_ctl, self.ik_chain[2], mo=True)
        self.ik_ctl = ik_ctl

        # Pole vector
        pv_ctl = controlsLibrary.create_control_from_lib(
            lib_name=_CTRL_STYLES["poleVector"],
            final_name=_ctrl(rn, "poleVector")
        )
        pv_gen = self._grp_maker.create_rig_hierarchy(pv_ctl, self.ik_chain[1], world_space=False)
        pv_pos = self._compute_pole_vector(self.ik_chain[0], self.ik_chain[1], self.ik_chain[2])
        cmds.xform(pv_gen, ws=True, t=pv_pos)
        cmds.poleVectorConstraint(pv_ctl, ik_h)

        cmds.parent(ik_root_gen, ik_ctl_gen, pv_gen, self.ik_grp)
        cmds.parentConstraint(ik_ctl, ik_h, mo=True)
        cmds.parentConstraint(self.clavicule_ctl, ik_root_gen, mo=True)
        cmds.parent(ik_h, self.arm_grp)

    # -----------------------------------------------------------------------
    # 4. FK SETUP
    # -----------------------------------------------------------------------

    def _build_fk(self):
        rn   = self.rig_name
        side = self.side
        parts = ["shoulder", "elbow", "wrist"]

        fk_ctrls = []
        for i, part in enumerate(parts):
            jnt  = self.fk_chain[i]
            ctrl = controlsLibrary.create_control_from_lib(
                lib_name=_CTRL_STYLES["mainFk"],
                final_name=_ctrl(rn, f"{side}_{part}_fk")
            )
            gen = self._grp_maker.create_rig_hierarchy(ctrl, jnt)
            cmds.parentConstraint(ctrl, jnt)
            fk_ctrls.append(ctrl)

            if i == 0:
                cmds.parent(gen, self.fk_grp)
            else:
                cmds.parent(gen, fk_ctrls[i - 1])

        cmds.parentConstraint(self.clavicule_ctl, self.fk_grp, mo=True)
        self.fk_ctrls = fk_ctrls

    # -----------------------------------------------------------------------
    # 5. SWITCH IK/FK
    # -----------------------------------------------------------------------

    def _build_switch(self):
        rn = self.rig_name

        switch_ctl = controlsLibrary.create_control_from_lib(
            lib_name=_CTRL_STYLES["switch"],
            final_name=_ctrl(rn, "switch")
        )
        switch_gen = self._grp_maker.create_rig_hierarchy(switch_ctl, self.bind_chain[2])
        cmds.xform(switch_gen, r=True, os=True, t=(0, 10, 0))
        cmds.addAttr(switch_ctl, ln="IK_FK", at="double", min=0, max=1, k=True)
        cmds.parent(switch_gen, self.main_rig_grp)
        self.switch_ctl = switch_ctl

        vis_rev = cmds.createNode("reverse", n=f"{rn}_VIS_REV")
        cmds.connectAttr(f"{switch_ctl}.IK_FK", f"{vis_rev}.inputX")
        cmds.connectAttr(f"{switch_ctl}.IK_FK", f"{self.fk_grp}.visibility")
        cmds.connectAttr(f"{vis_rev}.outputX",  f"{self.ik_grp}.visibility")

    # -----------------------------------------------------------------------
    # 6. PAIR BLENDS
    # -----------------------------------------------------------------------

    def _build_blends(self):
        rn    = self.rig_name
        parts = ["shoulder", "elbow", "wrist"]

        for i in range(len(self.bind_chain)):
            pbl = NodeCreator(
                side=self.side,
                node_type="pairBlend",
                base_name=rn,
                name=parts[i],
                tag="blend",
                parent=None,
                custom_suffix=None
            ).create()

            cmds.setAttr(f"{pbl}.rotInterpolation", 1)
            cmds.connectAttr(f"{self.ik_chain[i]}.translate", f"{pbl}.inTranslate1")
            cmds.connectAttr(f"{self.ik_chain[i]}.rotate",    f"{pbl}.inRotate1")
            cmds.connectAttr(f"{self.fk_chain[i]}.translate", f"{pbl}.inTranslate2")
            cmds.connectAttr(f"{self.fk_chain[i]}.rotate",    f"{pbl}.inRotate2")
            cmds.connectAttr(f"{pbl}.outTranslate", f"{self.bind_chain[i]}.translate")
            cmds.connectAttr(f"{pbl}.outRotate",    f"{self.bind_chain[i]}.rotate")
            cmds.connectAttr(f"{self.switch_ctl}.IK_FK", f"{pbl}.weight")

    # -----------------------------------------------------------------------
    # 7. MIRROR DE SHAPES PARA EL LADO R
    #    (solo se llama cuando side == "R")
    # -----------------------------------------------------------------------

    def _mirror_controls_R(self):
        """
        Sustituye las shapes de los controles del lado R por copias de las del
        lado L, renombradas. Esto da formas idénticas en espejo sin tener que
        diseñar controles separados para cada lado.

        El posicionamiento real ya está resuelto por la jerarquía de grupos
        que construyó _build_ik / _build_fk sobre los joints R. Aquí solo
        intercambiamos las shapes.

        Alternativa más sencilla que duplicar el main_grp entero: recorremos
        los controles que ya existen en el lado R y les copiamos las shapes
        del control homólogo del lado L.
        """
        if not self.mirror_source:
            cmds.warning("[ArmModule] mirror_source no definido; shapes del lado R sin cambios.")
            return

        rn_L = self.mirror_source.rig_name  # "Arm_L"
        rn_R = self.rig_name                 # "Arm_R"

        # Mapa de control R → control L equivalente
        # (mismos labels, distinto rig_name)
        labels = [
            "clavicule",
            "armRoot",
            "armIk",
            "poleVector",
            "switch",
            f"{self.side}_shoulder_fk",
            f"{self.side}_elbow_fk",
            f"{self.side}_wrist_fk",
        ]
        # Los FK del lado L usan "L_" en el label
        labels_L = [
            "clavicule",
            "armRoot",
            "armIk",
            "poleVector",
            "switch",
            f"L_shoulder_fk",
            f"L_elbow_fk",
            f"L_wrist_fk",
        ]

        for lbl_R, lbl_L in zip(labels, labels_L):
            ctrl_R = _ctrl(rn_R, lbl_R)
            ctrl_L = _ctrl(rn_L, lbl_L)

            if not cmds.objExists(ctrl_R) or not cmds.objExists(ctrl_L):
                cmds.warning(f"[ArmModule] No se puede copiar shape: {ctrl_L} -> {ctrl_R}")
                continue

            # Eliminar shapes actuales del control R
            old_shapes = cmds.listRelatives(ctrl_R, s=True, fullPath=True) or []
            if old_shapes:
                cmds.delete(old_shapes)

            # Duplicar shapes del control L y moverlas al control R
            shapes_L = cmds.listRelatives(ctrl_L, s=True, fullPath=True) or []
            for shp in shapes_L:
                dup = cmds.duplicate(shp, addShape=False)[0]
                # El duplicate crea un transform temporal; cogemos su shape
                dup_shapes = cmds.listRelatives(dup, s=True, fullPath=True) or []
                for ds in dup_shapes:
                    cmds.parent(ds, ctrl_R, r=True, s=True)
                cmds.delete(dup)

        # Meter el main_grp del lado R bajo mirrorBehaviour_GRP
        mirror_grp = (
            self.root_instance.mirror_grp
            if (self.root_instance and hasattr(self.root_instance, "mirror_grp"))
            else None
        )
        if mirror_grp and cmds.objExists(mirror_grp):
            if cmds.listRelatives(self.main_grp, p=True) != [mirror_grp]:
                cmds.parent(self.main_grp, mirror_grp)

    # -----------------------------------------------------------------------
    # 8. ORGANIZACIÓN FINAL
    # -----------------------------------------------------------------------

    def _organize(self):
        ri = self.root_instance

        rig_grp = f"{ri.rig_name}_rig_GRP" if ri else None
        if rig_grp and cmds.objExists(rig_grp):
            cmds.parent(self.b_cl,    rig_grp)
            cmds.parent(self.arm_grp, rig_grp)

        local_ctl = ri.localCtl if ri else None
        if local_ctl and cmds.objExists(local_ctl):
            # El lado L va directo bajo localCtl
            # El lado R ya está bajo mirror_grp, que a su vez está bajo localCtl
            if self.side == "L":
                cmds.parent(self.main_grp, local_ctl)
            # Para el R, _mirror_controls_R ya lo puso bajo mirror_grp

    # -----------------------------------------------------------------------
    # Utilidades matemáticas
    # -----------------------------------------------------------------------

    @staticmethod
    def _compute_pole_vector(start, mid, end, distance=5):
        sh_p = cmds.xform(start, q=True, ws=True, t=True)
        el_p = cmds.xform(mid,   q=True, ws=True, t=True)
        wr_p = cmds.xform(end,   q=True, ws=True, t=True)

        sw = [wr_p[i] - sh_p[i] for i in range(3)]
        se = [el_p[i] - sh_p[i] for i in range(3)]

        dot    = sum(se[i] * sw[i] for i in range(3))
        mag_sq = sum(sw[i] * sw[i] for i in range(3))
        if mag_sq < 0.0001:
            return el_p

        proj = [(dot / mag_sq) * sw[i] for i in range(3)]
        perp = [se[i] - proj[i] for i in range(3)]

        length = math.sqrt(sum(v * v for v in perp))
        perp   = [0, 0, 1] if length < 0.0001 else [v / length for v in perp]

        return [el_p[i] + perp[i] * distance for i in range(3)]


# ---------------------------------------------------------------------------
# Uso
# ---------------------------------------------------------------------------
#
# import rigRoot_module, guides_module, arm_module
#
# root = rigRoot_module.RigRoot("Character")
# root.build()
#
# guides = guides_module.CharacterGuides()
# guides.create_guides()
# # (aquí también deberías crear/orientar las guías del lado R: R_shoulder, etc.)
#
# arm_L = arm_module.ArmModule(side="L", root_instance=root)
# arm_L.build()
#
# arm_R = arm_module.ArmModule(side="R", root_instance=root, mirror_source=arm_L)
# arm_R.build()