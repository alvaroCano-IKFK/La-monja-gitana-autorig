import maya.cmds as cmds
import math
import re
import controlsLibrary
import groups_module
import rigRoot_module
import limbs_module

class ArmRightModule(object):
    def __init__(self, shoulder_guide="R_shoulder",
                 elbow_guide="R_elbow",
                 wrist_guide="R_wrist",
                 clavicule_guide="R_clavicule",
                 rig_name="Arm_R",
                 root_instance=None,
                 left_arm_instance=None):

        self.shoulder_guide  = shoulder_guide
        self.elbow_guide     = elbow_guide
        self.wrist_guide     = wrist_guide
        self.clavicule_guide = clavicule_guide
        self.names           = ["R_clavicule", "R_shoulder", "R_elbow", "R_wrist"]
        self.rig_name        = rig_name

        self.styles = {
            "mainIk":     "squareControl",
            "root":       "rootControl",
            "mainFk":     "circleControl",
            "switch":     "switchControl02",
            "poleVector": "poleVectorControl",
            "clavicule":  "claviculeControl",
        }

        self.group_maker   = groups_module.ControlsGroups()
        self.root_instance = root_instance

        self.left_main_grp = (
            left_arm_instance.main_grp
            if (left_arm_instance and hasattr(left_arm_instance, "main_grp"))
            else None
        )

        self.mirror_grp = (
            self.root_instance.mirror_grp
            if (self.root_instance and hasattr(self.root_instance, "mirror_grp"))
            else None
        )

        self.bind_chain = []
        self.ik_chain   = []
        self.fk_chain   = []

    ###########################################################################

    def define_poleVector(self, start, mid, end, distance=5):
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

    # ------------------------------------------------------------------

    def _create_skeleton_internal(self):
        # El mirror de la clavícula ya arrastra las tres cadenas completas
        # (bind, ik, fk) porque son hijas de la clavícula en el lado L.
        # NO hay que duplicar nada: solo mirrorear y leer por nombre.
        source_clav = "Arm_L_L_clavicule_bind_JNT"

        if not cmds.objExists(source_clav):
            cmds.error(f"No se encuentra el joint de origen: {source_clav}")
            return

        mirrored  = cmds.mirrorJoint(
            source_clav, mirrorYZ=True, mirrorBehavior=True, searchReplace=("L_", "R_")
        )
        self.b_cl = mirrored[0]  # R_clavicule_bind

        # Apuntar a los joints ya creados por el mirror
        rn = self.rig_name  # "Arm_R"
        self.bind_chain = [
            f"{rn}_R_shoulder_bind_JNT",
            f"{rn}_R_elbow_bind_JNT",
            f"{rn}_R_wrist_bind_JNT",
        ]
        self.ik_chain = [
            f"{rn}_R_shoulder_ik_JNT",
            f"{rn}_R_elbow_ik_JNT",
            f"{rn}_R_wrist_ik_JNT",
        ]
        self.fk_chain = [
            f"{rn}_R_shoulder_fk_JNT",
            f"{rn}_R_elbow_fk_JNT",
            f"{rn}_R_wrist_fk_JNT",
        ]

        for jnt in self.bind_chain + self.ik_chain + self.fk_chain:
            if not cmds.objExists(jnt):
                cmds.error(f"Joint no encontrado tras el mirror: {jnt}")
                return

    # ------------------------------------------------------------------

    def build(self):
        # 1. ESQUELETOS
        self._create_skeleton_internal()

        # 2. DUPLICAR GRUPO DE CONTROLES DEL LADO L
        if not self.left_main_grp or not cmds.objExists(self.left_main_grp):
            cmds.error("No se encontró el grupo de controladores del brazo izquierdo.")
            return

        new_grp_nodes = cmds.duplicate(self.left_main_grp, rc=True, n=f"{self.rig_name}_armControls_GRP")
        self.main_grp = new_grp_nodes[0]

        # 3. RENOMBRAR: Arm_L / _L_  ->  Arm_R / _R_  y quitar sufijo numérico de Maya
        all_children = cmds.listRelatives(self.main_grp, ad=True, fullPath=True) or []

        for node in all_children:
            if not cmds.objExists(node):
                continue

            short_name = node.split("|")[-1]
            new_name   = short_name

            if "Arm_L" in new_name or "_L_" in new_name:
                new_name = new_name.replace("Arm_L", "Arm_R").replace("_L_", "_R_")

            new_name = re.sub(r'(\D)(\d+)$', r'\1', new_name)

            if new_name == short_name:
                continue

            if cmds.objExists(new_name):
                cmds.rename(new_name, f"{new_name}_OLD_TMP")

            cmds.rename(node, new_name)

        cmds.parent(self.main_grp, self.mirror_grp)
        cmds.setAttr(f"{self.main_grp}.scaleZ", 1)
        cmds.setAttr(f"{self.main_grp}.rotateY", 0)

        # 4. REFERENCIAS A CONTROLES YA DUPLICADOS Y RENOMBRADOS
        ik_root_ctrl   = f"{self.rig_name}_armRoot_CTRL"
        ik_ctrl        = f"{self.rig_name}_armIk_CTRL"
        clavicule_ctrl = f"{self.rig_name}_clavicule_CTRL"
        pv_ctrl        = f"{self.rig_name}_poleVector_CTRL"
        switch_ctrl    = f"{self.rig_name}_switch_CTRL"
        fk_grp         = f"{self.rig_name}_fk_GRP"
        ik_grp         = f"{self.rig_name}_ik_GRP"

        # names[0]=R_clavicule (ctrl propio), FK empieza en names[1]=R_shoulder
        fk_ctrls = [
            f"{self.rig_name}_{self.names[1]}_fk_CTRL",  # shoulder
            f"{self.rig_name}_{self.names[2]}_fk_CTRL",  # elbow
            f"{self.rig_name}_{self.names[3]}_fk_CTRL",  # wrist
        ]

        for ctrl in [ik_root_ctrl, ik_ctrl, clavicule_ctrl, pv_ctrl, switch_ctrl] + fk_ctrls:
            if not cmds.objExists(ctrl):
                cmds.error(f"Control no encontrado tras el renombrado: {ctrl}")
                return

        # 5. IK HANDLE
        ik_h, _ = cmds.ikHandle(
            sj=self.ik_chain[0], ee=self.ik_chain[2],
            sol="ikRPsolver", n=f"{self.rig_name}_IKH"
        )

        # 6. CONSTRAINTS
        cmds.pointConstraint(ik_root_ctrl,  self.ik_chain[0], mo=True)
        cmds.parentConstraint(ik_ctrl,      ik_h,             mo=True)
        cmds.orientConstraint(ik_ctrl,      self.ik_chain[2], mo=True)

        ik_root_gen = cmds.listRelatives(ik_root_ctrl, p=True)[0]
        cmds.parentConstraint(clavicule_ctrl, ik_root_gen, mo=True)
        cmds.parentConstraint(clavicule_ctrl, fk_grp,      mo=True)

        # 7. POLE VECTOR
        cmds.poleVectorConstraint(pv_ctrl, ik_h)

        # 8. FK CONTROLS -> FK CHAIN
        for i, ctrl in enumerate(fk_ctrls):
            cmds.parentConstraint(ctrl, self.fk_chain[i], mo=True)

        # 9. SWITCH VISIBILITY
        vis_rev = cmds.createNode("reverse", n=f"{self.rig_name}_VIS_REV")
        cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{vis_rev}.inputX")
        cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{fk_grp}.visibility")
        cmds.connectAttr(f"{vis_rev}.outputX",   f"{ik_grp}.visibility")

        # 10. PAIR BLENDS
        for i in range(len(self.bind_chain)):
            pbl = cmds.createNode("pairBlend", n=f"{self.bind_chain[i]}_PBL")
            cmds.setAttr(f"{pbl}.rotInterpolation", 1)
            cmds.connectAttr(f"{self.ik_chain[i]}.translate", f"{pbl}.inTranslate1")
            cmds.connectAttr(f"{self.ik_chain[i]}.rotate",    f"{pbl}.inRotate1")
            cmds.connectAttr(f"{self.fk_chain[i]}.translate", f"{pbl}.inTranslate2")
            cmds.connectAttr(f"{self.fk_chain[i]}.rotate",    f"{pbl}.inRotate2")
            cmds.connectAttr(f"{pbl}.outTranslate", f"{self.bind_chain[i]}.translate")
            cmds.connectAttr(f"{pbl}.outRotate",    f"{self.bind_chain[i]}.rotate")
            cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{pbl}.weight")

        # 11. ORGANIZACIÓN FINAL
        rig_grp = (
            f"{self.root_instance.rig_name}_rig_GRP"
            if self.root_instance else None
        )
        if rig_grp  and cmds.objExists(rig_grp ):
            #cmds.parent(self.b_cl, rig_grp )
            cmds.parent(ik_h, rig_grp )

        print(f"Build {self.rig_name} completo.")