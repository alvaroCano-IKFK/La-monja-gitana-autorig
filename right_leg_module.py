import maya.cmds as cmds
import math
import re
import controlsLibrary
import groups_module
import rigRoot_module
import limbModule
import leg_module
import nodeCreator_module
from nodeCreator_module import NodeCreator

class LegRightModule(object):
    def __init__(self, thigh_guide="R_hip",
                 knee_guide="R_knee",
                 ankle_guide="R_ankle",
                 ball_guide="R_ball",
                 tip_guide="R_toe_tip",
                 heel_guide="R_heel",
                 rig_name="Leg_R",
                 root_instance=None,
                 left_leg_instance=None):

        self.thigh_guide = thigh_guide
        self.knee_guide  = knee_guide
        self.ankle_guide = ankle_guide
        self.ball_guide  = ball_guide
        self.tip_guide   = tip_guide
        self.heel_guide  = heel_guide

        self.names = ["R_thigh", "R_knee", "R_ankle", "R_ball", "R_toe_tip", "R_heel"]
        self.rig_name = rig_name

        self.styles = {
            "mainIk":      "squareControl",
            "mainFk":      "circleControl",
            "footBall":    "footBallControl",
            "footTip":     "footTipControl",
            "footHeel":    "footHeelControl",
            "footBankIn":  "footBankInControl",
            "footBankOut": "footBankOutControl",
            "footRoot":    "rootControl",
            "switch":      "switchControl",
            "poleVector":  "legPoleVectorControl",
        }

        self.group_maker = groups_module.ControlsGroups()
        self.root_instance = root_instance

        self.left_leg_instance = left_leg_instance
        
        self.left_main_grp = (
            left_leg_instance.main_grp
            if (left_leg_instance and hasattr(left_leg_instance, "main_grp"))
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

    def create_offset_group(self, ctrl, target_proc, orient=False, world_space=True):
        return self.group_maker.create_rig_hierarchy(
            ctrl,
            target_proc,
            match_rotation=orient,
            world_space=world_space)

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
        source_joint = "Leg_L_L_thigh_bind_JNT"

        if not cmds.objExists(source_joint):
            cmds.error(f"No se encuentra el joint de origen: {source_joint}")
            return

        # 1. MIRROR
        self.bind_chain = cmds.mirrorJoint(
            source_joint, mirrorYZ=True, mirrorBehavior=True, searchReplace=("L_", "R_")
        )

        # 2. DUPLICAR PARA IK Y FK
        for suffix in ["ik", "fk"]:
            new_raw = cmds.duplicate(self.bind_chain[0], rc=True)

            all_nodes = cmds.listRelatives(new_raw[0], ad=True, type="joint", fullPath=True) or []
            all_nodes.append(cmds.ls(new_raw[0], l=True)[0])
            all_nodes = list(reversed(all_nodes))

            chain_list = []
            for node in reversed(all_nodes):
                short_name = node.split("|")[-1]
                new_name = short_name.replace("bind", suffix)

                if cmds.objExists(new_name):
                    cmds.delete(new_name)

                actual = cmds.rename(node, new_name)
                chain_list.append(actual)

            setattr(self, f"{suffix}_chain", list(reversed(chain_list)))

    # ------------------------------------------------------------------

    def build(self):
        # 1. ESQUELETOS
        self._create_skeleton_internal()

        # 2. DUPLICAR GRUPO DE CONTROLES DEL LADO L
        if not self.left_main_grp or not cmds.objExists(self.left_main_grp):
            cmds.error("No se encontró el grupo de controladores de la pierna izquierda.")
            return

        new_grp_nodes = cmds.duplicate(self.left_main_grp, rc=True, n=f"{self.rig_name}_legControls_GRP")
        self.main_grp = new_grp_nodes[0]

        # 3. RENOMBRAR: L_ -> R_ y quitar sufijo numerico de Maya
        all_children = cmds.listRelatives(self.main_grp, ad=True, fullPath=True) or []

        for node in all_children:
            if not cmds.objExists(node):
                continue

            short_name = node.split("|")[-1]
            new_name = short_name

            if "Leg_L" in new_name or "_L_" in new_name:
                new_name = new_name.replace("Leg_L", "Leg_R").replace("_L_", "_R_")

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
        ik_root_ctrl      = f"{self.rig_name}_legRoot_CTRL"
        ik_ctrl           = f"{self.rig_name}_legIk_CTRL"
        foot_ball_ctrl    = f"{self.rig_name}_footBall_CTRL"
        foot_tip_ctrl     = f"{self.rig_name}_footTip_CTRL"
        foot_heel_ctrl    = f"{self.rig_name}_footHeel_CTRL"
        foot_bankIn_ctrl  = f"{self.rig_name}_footBankIn_CTRL"
        foot_bankOut_ctrl = f"{self.rig_name}_footBankOut_CTRL"
        pv_ctrl           = f"{self.rig_name}_poleVector_CTRL"
        switch_ctrl       = f"{self.rig_name}_switch_CTRL"
        fk_grp            = f"{self.rig_name}_fk_GRP"
        ik_grp            = f"{self.rig_name}_ik_GRP"

        fk_ctrls = [
            f"{self.rig_name}_{self.names[0]}_CTRL",  # thigh
            f"{self.rig_name}_{self.names[1]}_CTRL",  # knee
            f"{self.rig_name}_{self.names[2]}_CTRL",  # ankle
            f"{self.rig_name}_{self.names[3]}_CTRL",  # ball
        ]

        # Verificar que los controles clave existen
        for ctrl in [ik_root_ctrl, foot_ball_ctrl, foot_tip_ctrl, switch_ctrl] + fk_ctrls:
            if not cmds.objExists(ctrl):
                cmds.error(f"Control no encontrado tras el renombrado: {ctrl}")
                return

        # 5. IK HANDLES
        ik_h, _           = cmds.ikHandle(sj=self.ik_chain[0], ee=self.ik_chain[2],
                                           sol="ikRPsolver", n=f"{self.rig_name}_IKH")
        ik_footTip, _     = cmds.ikHandle(sj=self.ik_chain[3], ee=self.ik_chain[4],
                                           sol="ikSCsolver", n=f"{self.rig_name}_footTip_HDL")
        ik_footBall, _    = cmds.ikHandle(sj=self.ik_chain[2], ee=self.ik_chain[3],
                                           sol="ikSCsolver", n=f"{self.rig_name}_footBall_HDL")

        # --- ORGANIZACIÓN DE GRUPOS (Mover aquí arriba) ---
        # 1. Creamos el grupo de sistema primero
        self.leg_grp = cmds.group(em=True, n=f"{self.rig_name}_leg_GRP")
        
        # 2. Ahora sí podemos emparentar los handles
        cmds.parent(ik_h, ik_footTip, ik_footBall, self.leg_grp)
        #cmds.setAttr(f"{self.leg_grp}.v", 0) # Opcional: ocultar sistema

        # 6. CONECTAR IK SOLVERS A CONTROLES (Tu código sigue igual...)
        cmds.pointConstraint(ik_root_ctrl, self.ik_chain[0], mo=True)
        cmds.parentConstraint(foot_ball_ctrl, ik_h, mo=True)
        cmds.parentConstraint(foot_ball_ctrl, ik_footBall, mo=True)
        cmds.parentConstraint(foot_tip_ctrl, ik_footTip, mo=True)
        
        # 7. POLE VECTOR
        #cmds.xform(pv_off, ws=True, t=pv_pos)
        cmds.poleVectorConstraint(pv_ctrl, ik_h)

        # 8. CONECTAR FK CONTROLS A CADENA FK
        for i, ctrl in enumerate(fk_ctrls):
            cmds.parentConstraint(ctrl, self.fk_chain[i], mo=True)

        # 9. SWITCH VISIBILITY (reconectar, las conexiones del lado L no aplican aqui)
        vis_rev = cmds.createNode("reverse", n=f"{self.rig_name}_VIS_REV")
        cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{vis_rev}.inputX")
        cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{fk_grp}.visibility")
        cmds.connectAttr(f"{vis_rev}.outputX", f"{ik_grp}.visibility")

        # 10. PAIR BLENDS (bind chain sigue a ik/fk segun el switch)
        for i in range(3):
            pbl_creator = NodeCreator(
            side=self.rig_name.split("_")[-1],   
            node_type="pairBlend",
            base_name=self.rig_name,              
            name=self.names[i],                   
            tag="blend",
            parent=None,
            custom_suffix=None                    
            )
            pbl = pbl_creator.create()
            cmds.setAttr(f"{pbl}.rotInterpolation", 1)
            cmds.connectAttr(f"{self.ik_chain[i]}.translate", f"{pbl}.inTranslate1")
            cmds.connectAttr(f"{self.ik_chain[i]}.rotate",    f"{pbl}.inRotate1")
            cmds.connectAttr(f"{self.fk_chain[i]}.translate", f"{pbl}.inTranslate2")
            cmds.connectAttr(f"{self.fk_chain[i]}.rotate",    f"{pbl}.inRotate2")
            cmds.connectAttr(f"{pbl}.outTranslate", f"{self.bind_chain[i]}.translate")
            cmds.connectAttr(f"{pbl}.outRotate",    f"{self.bind_chain[i]}.rotate")
            cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{pbl}.weight")
            
            
        # 11. EMPARENTAMIENTO FINAL AL RIG GLOBAL
        # Definimos rig_grp para que no de error
        rig_grp = f"{self.root_instance.rig_name}_rig_GRP" if self.root_instance else None

        if rig_grp and cmds.objExists(rig_grp):
            # Metemos el grupo de sistema (IKs) en el Rig
            cmds.parent(self.leg_grp, rig_grp)
            
            # Opcional: Si quieres que los joints también se organicen como en la L
            self.leg_joints_grp = cmds.group(em=True, n=f"{self.rig_name}_leg_joints_GRP")
            cmds.parent(self.bind_chain[0], self.ik_chain[0], self.fk_chain[0], self.leg_joints_grp)
            cmds.parent(self.leg_joints_grp, rig_grp)        
        

        print(f"Build {self.rig_name} completo.")