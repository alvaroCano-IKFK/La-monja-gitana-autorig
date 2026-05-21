import maya.cmds as cmds
from functools import partial
import os
import math
import json
import spine_module
import limbs_module
import fingers_module
import neck_module
import chest_module
import hip_module
import leg_module
import foot_module
import groups_module
import rigRoot_module
import mirror_module
import arm_right_module
import right_leg_module
import skinning_module
from sideManager_module import SideManager

########################################################################
# SPINE
########################################################################

class SpineGuides(object):
    def __init__(self, spine_root, spine_chest, spine_position):
        self.spine_root = spine_root
        self.spine_end = spine_chest
        self.spine_position = spine_position
        self.guides_group = None

    def spine_guides(self):
        root_joint = cmds.joint(p=(0, 0, 0), name=self.spine_root)
        if not root_joint:
            print(f"Error creando la joint: {self.spine_root}")
            return

        end_joint = cmds.joint(p=self.spine_position, name=self.spine_end)
        if not end_joint:
            print(f"Error creando la joint: {self.spine_end}")
            return

        cmds.select(root_joint, end_joint, r=True)
        self.guides_group = cmds.group(root_joint, n="spine_guides_GRP")
        if self.guides_group is None:
            print("Error al crear el grupo de guías.")

########################################################################
# NECK
########################################################################

class NeckGuides(object):
    def __init__(self, neck_root, neck_end, root_pos, end_pos):
        self.neck_root = neck_root
        self.neck_end = neck_end
        self.root_pos = root_pos
        self.end_pos = end_pos
        self.guides_group = None

    def neck_guides(self):
        cmds.select(clear=True)
        neck_root = cmds.joint(p=self.root_pos, n=self.neck_root)
        if not neck_root:
            print(f"Error creando la joint: {self.neck_root}")
            return

        neck_end = cmds.joint(p=self.end_pos, n=self.neck_end)
        if not neck_end:
            print(f"Error creando la joint: {self.neck_end}")
            return

        cmds.joint(neck_root, e=True, oj="yzx", sao="zup", ch=True, zso=True)
        self.guides_group = cmds.group(neck_root, n="neck_guides_GRP")
        if self.guides_group is None:
            print("Error al crear el grupo de guías del cuello.")

        cmds.select(clear=True)

########################################################################
# ARM GUIDES
########################################################################

class ArmGuides(object):
    """
    Guías para el brazo.

    Parámetros
    ----------
    side : str
        "L" o "R". Controla prefijos, orientación y mirror de posiciones.
    limb_root_pos, limb_mid_pos, limb_end_pos, clavicule_root_pos : tuple
        Posiciones para el lado L. Si side == "R" se reflejan en X
        automáticamente vía SideManager.
    """

    def __init__(self, side,
                 limb_root_pos, limb_mid_pos, limb_end_pos, clavicule_root_pos):

        self.sm = SideManager(side)

        # Nombres generados automáticamente desde el lado
        self.limb_root     = self.sm.prefix("shoulder")
        self.limb_mid      = self.sm.prefix("elbow")
        self.limb_end      = self.sm.prefix("wrist")
        self.clavicule     = self.sm.prefix("clavicule")

        # Posiciones (se reflejan en X si side == "R")
        self.limb_root_pos     = self.sm.mirror_pos(limb_root_pos)
        self.limb_mid_pos      = self.sm.mirror_pos(limb_mid_pos)
        self.limb_end_pos      = self.sm.mirror_pos(limb_end_pos)
        self.clavicule_pos     = self.sm.mirror_pos(clavicule_root_pos)

        self.guides_group = None
        self.wrist_joint  = None

    def create_chain(self):
        """Crea la cadena de joints y la orienta automáticamente."""
        cmds.select(clear=True)

        hierarchy_root = cmds.joint(n=self.clavicule, p=self.clavicule_pos)
        root = cmds.joint(n=self.limb_root, p=self.limb_root_pos)
        mid  = cmds.joint(n=self.limb_mid,  p=self.limb_mid_pos)
        end  = cmds.joint(n=self.limb_end,  p=self.limb_end_pos)

        cmds.joint(root, edit=True,
                   oj=self.sm.joint_orient,
                   sao=self.sm.secondary_orient,
                   ch=True, zso=True)

        self.guides_group = cmds.group(hierarchy_root,
                                       n=f"{self.sm.side}_arm_guides_GRP")
        self.wrist_joint = self.limb_end

        return self.guides_group

########################################################################
# LEG GUIDES
########################################################################

class LegGuides(object):
    """
    Guías para la pierna.

    Parámetros
    ----------
    side : str
        "L" o "R".
    limb_root_pos, limb_mid_pos, limb_end_pos : tuple
        Posiciones para el lado L. Se reflejan en X automáticamente si side == "R".
    """

    def __init__(self, side,
                 limb_root_pos, limb_mid_pos, limb_end_pos):

        self.sm = SideManager(side)

        # Nombres automáticos
        self.limb_root = self.sm.prefix("hip")
        self.limb_mid  = self.sm.prefix("knee")
        self.limb_end  = self.sm.prefix("ankle")

        # Posiciones (mirror en X si side == "R")
        self.limb_root_pos = self.sm.mirror_pos(limb_root_pos)
        self.limb_mid_pos  = self.sm.mirror_pos(limb_mid_pos)
        self.limb_end_pos  = self.sm.mirror_pos(limb_end_pos)

        self.guides_group = None
        self.ankle_joint  = None

    def create_chain(self):
        """Crea la cadena de joints y la orienta automáticamente."""
        cmds.select(clear=True)

        root = cmds.joint(n=self.limb_root, p=self.limb_root_pos)
        cmds.select(clear=True)
        mid  = cmds.joint(n=self.limb_mid,  p=self.limb_mid_pos)
        cmds.select(clear=True)
        end  = cmds.joint(n=self.limb_end,  p=self.limb_end_pos)
        cmds.select(clear=True)

        cmds.parent(mid, root)
        cmds.joint(root, edit=True,
                   oj=self.sm.joint_orient,
                   sao=self.sm.secondary_orient,
                   ch=True, zso=True)
        cmds.parent(end, mid)

        self.guides_group = cmds.group(root,
                                       n=f"{self.sm.side}_leg_guides_GRP")

        cmds.setAttr(f"{end}.jointOrient", 0, 0, 0)
        self.ankle_joint = self.limb_end

        return self.guides_group

########################################################################
# FINGER GUIDES
########################################################################

class FingerGuides(object):

    def __init__(self, parent_joint, name, offsets):
        self.parent_joint = parent_joint
        self.name = name
        self.offsets = offsets
        self.joints = []

    def finger_guides(self):
        wrist_pos = cmds.xform(self.parent_joint, q=True, ws=True, t=True)
        cmds.select(clear=True)

        for i, offset in enumerate(self.offsets):
            pos = (
                wrist_pos[0] + offset[0],
                wrist_pos[1] + offset[1],
                wrist_pos[2] + offset[2],
            )
            jnt_name = f"{self.name}_{i+1:02d}"
            jnt = cmds.joint(n=jnt_name, p=pos)
            self.joints.append(jnt)

        cmds.parent(self.joints[0], self.parent_joint)

########################################################################
# HAND GUIDES
########################################################################

class HandGuides(object):
    """
    Genera las guías de los dedos de la mano.

    El lado se toma directamente de arm_instance.sm.side,
    así que no hace falta pasarlo por separado.
    """

    def __init__(self, arm_instance):
        self.arm     = arm_instance
        self.sm      = arm_instance.sm          # reutilizamos el SideManager del brazo
        self.fingers = []
        self.group   = None

    def hand_guides(self):
        wrist = self.arm.wrist_joint
        s = self.sm.side  # "L" o "R"

        # Offsets en espacio local del wrist — el mirror en X
        # ya lo gestiona ArmGuides al posicionar el wrist,
        # así que estos offsets son iguales para ambos lados.
        finger_data = {
            f"{s}_index":  [(1,0,1),(2,0,1),(3,0,1),(4,0,1),(5,0,1)],
            f"{s}_middle": [(1,0,0),(2,0,0),(3,0,0),(4,0,0),(5,0,0)],
            f"{s}_ring":   [(1,0,-1),(2,0,-1),(3,0,-1),(4,0,-1),(5,0,-1)],
            f"{s}_pinky":  [(1,0,-2),(2,0,-2),(3,0,-2),(4,0,-2),(5,0,-2)],
            f"{s}_thumb":  [(1,-1,2),(2,-1,2),(3,-1,2)],
        }

        for name, offsets in finger_data.items():
            finger = FingerGuides(wrist, name, offsets)
            finger.finger_guides()
            self.fingers.append(finger)

        self.group = cmds.group(wrist, n=f"{s}_hand_guides_GRP")

########################################################################
# FOOT GUIDES
########################################################################

class FootGuides(object):
    """
    El lado se toma del leg_instance.sm.side automáticamente.
    Los nombres ball/tip/heel se generan con el prefijo de lado;
    también puedes pasarlos manualmente si necesitas nombres personalizados.
    """

    def __init__(self, leg_instance,
                 ball_offset, tip_offset, heel_offset,
                 ball_name=None, tip_name=None, heel_name=None):

        self.leg  = leg_instance
        self.sm   = leg_instance.sm

        s = self.sm.side
        self.ball_name = ball_name or self.sm.prefix("ball")
        self.tip_name  = tip_name  or self.sm.prefix("toe_tip")
        self.heel_name = heel_name or self.sm.prefix("heel")

        self.ball_offset = ball_offset
        self.tip_offset  = tip_offset
        self.heel_offset = heel_offset
        self.joints = []

    def foot_guides(self):
        ankle     = self.leg.ankle_joint
        ankle_pos = cmds.xform(ankle, q=True, ws=True, t=True)

        cmds.select(clear=True)

        heel_pos = (
            ankle_pos[0] + self.heel_offset[0],
            ankle_pos[1] + self.heel_offset[1],
            ankle_pos[2] + self.heel_offset[2],
        )
        heel = cmds.joint(n=self.heel_name, p=heel_pos)
        cmds.select(clear=True)

        ball_pos = (
            ankle_pos[0] + self.ball_offset[0],
            ankle_pos[1] + self.ball_offset[1],
            ankle_pos[2] + self.ball_offset[2],
        )
        ball = cmds.joint(n=self.ball_name, p=ball_pos)

        tip_pos = (
            ankle_pos[0] + self.tip_offset[0],
            ankle_pos[1] + self.tip_offset[1],
            ankle_pos[2] + self.tip_offset[2],
        )
        tip = cmds.joint(n=self.tip_name, p=tip_pos)

        self.joints = [ball, tip, heel]

        cmds.parent(ball, ankle)
        cmds.parent(heel, ankle)

########################################################################
# CHARACTER GUIDES — instanciación completa
########################################################################

class CharacterGuides(object):
    """
    Crea las guías de un lado completo pasando únicamente side="L" o "R".
    Las posiciones de referencia son siempre las del lado L;
    SideManager se encarga del mirror automático.
    """

    def __init__(self):
        self.spine_rig = None

    def create_guides(self, side="L"):
        """
        Parámetros
        ----------
        side : str
            "L" crea el lado izquierdo, "R" crea el lado derecho
            con posiciones en mirror.
        """

        # ---- SPINE & NECK (no tienen lado, solo se crean una vez) ----
        if side == "L":
            spine_instance = SpineGuides("root", "chest", (0, 10, 0))
            spine_instance.spine_guides()

            neck_instance = NeckGuides("neck_root", "neck_end",
                                       (0, 20, 0), (0, 23, 0.5))
            neck_instance.neck_guides()

        # ---- BRAZO ----
        arm_instance = ArmGuides(
            side=side,
            clavicule_root_pos=(0, 12, 0),
            limb_root_pos=(3, 12, 0),
            limb_mid_pos=(13, 12, -0.1),
            limb_end_pos=(23, 12, 0),
        )
        arm_instance.create_chain()

        # ---- PIERNA ----
        leg_instance = LegGuides(
            side=side,
            limb_root_pos=(3, -10, 0),
            limb_mid_pos=(3, -20, 0.2),
            limb_end_pos=(3, -30, 0),
        )
        leg_instance.create_chain()

        # ---- MANO ----
        hand_instance = HandGuides(arm_instance)
        hand_instance.hand_guides()

        # ---- PIE ----
        foot_instance = FootGuides(
            leg_instance,
            ball_offset=(0, -2, 3),
            tip_offset=(0, -2, 6),
            heel_offset=(0, -2, -3),
        )
        foot_instance.foot_guides()

    def create_all_guides(self):
        """Atajo para crear ambos lados de una vez."""
        self.create_guides("L")
        self.create_guides("R")