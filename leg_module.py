import maya.cmds as cmds
import math
import controlsLibrary 
import guides_module
from groups_module import ControlsGroups
import rigRoot_module
import nodeCreator_module
from nodeCreator_module import NodeCreator


class LegModule(object):
    """Módulo para construir las piernas, con setup IK/FK y switch."""

    def __init__(self, thigh_guide="hip", 
                 knee_guide="knee", 
                 ankle_guide="ankle",
                 ball_guide ="ball", 
                 tip_guide = "toe_tip",
                 heel_guide = "heel",  
                 rig_name="Character",
                 side = "L",
                 root_instance= None):
                     
        self.thigh_guide = thigh_guide
        self.knee_guide = knee_guide
        self.ankle_guide = ankle_guide
        self.ball_guide = ball_guide
        self.tip_guide = tip_guide
        self.heel_guide = heel_guide
        
        self.side = side
        self.prefix = f"{self.side}_{rig_name}"         
        
        self.names = ["thigh", "knee", "ankle","ball","toe_tip","heel"]
        self.rig_name = rig_name
        self.styles = {"mainIk": "squareControl",
                              "mainFk": "circleControl",
                              "footBall": "footBallControl",
                              "footTip": "footTipControl",
                              "footHeel": "footHeelControl",
                              "footBankIn": "footBankInControl",
                              "footBankOut": "footBankOutControl",
                              "footRoot": "rootControl",
                              "switch": "switchControl",
                              "poleVector": "legPoleVectorControl"}
        
        self.group_maker = ControlsGroups()
        self.leg_grp = None
        
        self.root_instance = root_instance 

        self.bind_chain = []
        self.ik_chain = []
        self.fk_chain = []
        self.leg_joints_grp = None

    def create_offset_group(self, ctrl, target_proc, orient=False, world_space=True):
        """Crea un grupo de offset para el control, alineado con el target_proc."""
        return self.group_maker.create_rig_hierarchy(
            ctrl, 
            target_proc, 
            match_rotation=orient, 
            world_space=world_space
    )
    
    def define_poleVector(self, start, mid, end, distance=5):
        """Calcula la posición del pole vector basándose en la posición de los joints."""
        # NO TOCADO: Tu método original exacto
        sh_p = cmds.xform(start, q=True, ws=True, t=True)
        el_p = cmds.xform(mid, q=True, ws=True, t=True)
        wr_p = cmds.xform(end, q=True, ws=True, t=True)

        sw = [wr_p[i] - sh_p[i] for i in range(3)]
        se = [el_p[i] - sh_p[i] for i in range(3)]

        dot = sum(se[i] * sw[i] for i in range(3))
        mag_sq = sum(sw[i] * sw[i] for i in range(3))
        
        if mag_sq < 0.0001: return el_p
        
        proj = [(dot / mag_sq) * sw[i] for i in range(3)]
        perp = [se[i] - proj[i] for i in range(3)]
        
        length = math.sqrt(sum(v * v for v in perp))
        if length < 0.0001:
            perp = [0, 0, 1] 
        else:
            perp = [v / length for v in perp]

        return [el_p[i] + perp[i] * distance for i in range(3)]
    

    def build(self):
        # 1. POSICIONES REALES (Para que los joints bind/ik/fk nazcan en el esqueleto real R)
        pos_th = cmds.xform(self.thigh_guide, q=True, ws=True, t=True)
        pos_kn = cmds.xform(self.knee_guide, q=True, ws=True, t=True)
        pos_an = cmds.xform(self.ankle_guide, q=True, ws=True, t=True)
        pos_ball = cmds.xform(self.ball_guide, q=True, ws=True, t=True)
        pos_tip = cmds.xform(self.tip_guide, q=True, ws=True, t=True)
        pos_heel = cmds.xform(self.heel_guide, q=True, ws=True, t=True)

        # 1b. OBJETIVOS PARA ALINEAR CONTROLES (Si es R, usamos L para que el grupo espejo haga el cálculo)
        if self.side == "R":
            th_ctrl_target = self.thigh_guide.replace("R_", "L_")
            kn_ctrl_target = self.knee_guide.replace("R_", "L_")
            an_ctrl_target = self.ankle_guide.replace("R_", "L_")
            ball_ctrl_target = self.ball_guide.replace("R_", "L_")
            tip_ctrl_target = self.tip_guide.replace("R_", "L_")
            heel_ctrl_target = self.heel_guide.replace("R_", "L_")
        else:
            th_ctrl_target = self.thigh_guide
            kn_ctrl_target = self.knee_guide
            an_ctrl_target = self.ankle_guide
            ball_ctrl_target = self.ball_guide
            tip_ctrl_target = self.tip_guide
            heel_ctrl_target = self.heel_guide

        # 2. BIND CHAIN (Usa posiciones reales)
        cmds.select(clear=True)
        b_th = cmds.joint(n=f"{self.prefix}_{self.names[0]}_bind_JNT", p=pos_th)
        cmds.matchTransform(b_th, self.thigh_guide, rot=True, pos=False)

        cmds.select(clear=True)
        b_kn = cmds.joint(n=f"{self.prefix}_{self.names[1]}_bind_JNT", p=pos_kn)
        cmds.matchTransform(b_kn, self.knee_guide, rot=True, pos=False)
        cmds.select(clear=True)
        b_an = cmds.joint(n=f"{self.prefix}_{self.names[2]}_bind_JNT", p=pos_an)
        cmds.matchTransform(b_an, self.ankle_guide, rot=True, pos=True)
        cmds.select(clear=True)
        b_ba = cmds.joint(n=f"{self.prefix}_{self.names[3]}_bind_JNT", p=pos_ball)
        cmds.matchTransform(b_ba, self.ball_guide, rot=True, pos=False)
        cmds.select(clear=True)
        b_tip = cmds.joint(n=f"{self.prefix}_{self.names[4]}_bind_JNT", p=pos_tip)         
        cmds.matchTransform(b_tip, self.tip_guide, rot=True, pos=False)
        cmds.select(clear=True)        
               
        cmds.parent(b_kn, b_th)
        cmds.parent(b_an, b_kn)
        cmds.parent(b_ba, b_an)
        cmds.parent(b_tip, b_ba)
        
        cmds.makeIdentity(b_th, apply=True, t=0, r=1, s=0, n=0, pn=1)

        self.bind_chain = [b_th, b_kn, b_an, b_ba, b_tip]

        # Duplicate chains
        def duplicate_chain(suffix):
            new_jnts = cmds.duplicate(self.bind_chain[0], rc=True)
            root = cmds.rename(new_jnts[0], f"{self.prefix}_{self.names[0]}_{suffix}_JNT")
            children = cmds.listRelatives(root, ad=True, type="joint")
            children.reverse()
            kn = cmds.rename(children[0], f"{self.prefix}_{self.names[1]}_{suffix}_JNT")
            an = cmds.rename(children[1], f"{self.prefix}_{self.names[2]}_{suffix}_JNT")
            ball = cmds.rename(children[2], f"{self.prefix}_{self.names[3]}_{suffix}_JNT")
            tip = cmds.rename(children[3], f"{self.prefix}_{self.names[4]}_{suffix}_JNT")
            return [root, kn, an, ball, tip]
            
        self.fk_chain = duplicate_chain("fk")
        self.ik_chain = duplicate_chain("ik")
        
        # 3. GRUPOS DE RIG
        self.main_rig_grp = cmds.group(em=True, n=f"{self.prefix}_legControls_GRP")
        self.main_grp = self.main_rig_grp
        self.ik_grp = cmds.group(em=True, n=f"{self.prefix}_ik_GRP", p=self.main_rig_grp)
        self.fk_grp = cmds.group(em=True, n=f"{self.prefix}_fk_GRP", p=self.main_rig_grp)
        self.controls_grp = cmds.group(em=True, n=f"{self.prefix}_CONTROLS_GRP", p=self.main_rig_grp)
        self.leg_grp = cmds.group(em=True, n=f"{self.prefix}_leg_GRP")
        
        # 4. IK SETUP
        pref_rot = 0.1 if self.side == "L" else -0.1
        cmds.setAttr(f"{self.ik_chain[1]}.rotateX", pref_rot) 
        cmds.joint(self.ik_chain[0], edit=True, ch=True, spa=True) 
        cmds.setAttr(f"{self.ik_chain[1]}.rotateX", 0) 

        # ---- 4. IK HANDLES ----
        ik_h, _        = cmds.ikHandle(sj=self.ik_chain[0], ee=self.ik_chain[2],
                                        sol="ikRPsolver", n=f"{self.prefix}_IKH")
        ik_footBall, _ = cmds.ikHandle(sj=self.ik_chain[2], ee=self.ik_chain[3],
                                        sol="ikSCsolver", n=f"{self.prefix}_footBall_HDL")
        ik_footTip, _  = cmds.ikHandle(sj=self.ik_chain[3], ee=self.ik_chain[4],
                                        sol="ikSCsolver", n=f"{self.prefix}_footTip_HDL")
        cmds.select(clear=True)
        
        # IK Controls (Alineados con los targets corregidos)
        ik_root_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footRoot"], 
            final_name=f"{self.prefix}_legRoot_CTRL"
        )
        ik_root_gen = self.create_offset_group(ik_root_ctrl, th_ctrl_target, orient=True)
                
        ik_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["mainIk"], 
            final_name=f"{self.prefix}_legIk_CTRL"
        )
        ik_gen = self.create_offset_group(ik_ctrl, an_ctrl_target, world_space=True)
        
        foot_heel_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footHeel"], 
            final_name=f"{self.prefix}_footHeel_CTRL"
        )
        foot_heel_gen = self.create_offset_group(foot_heel_ctrl, heel_ctrl_target, world_space=True)        
        cmds.xform(foot_heel_gen, r=True, t=(0, -0.3, -2))
        
        foot_ball_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footBall"], 
            final_name=f"{self.prefix}_footBall_CTRL"
        )
        foot_ball_gen = self.create_offset_group(foot_ball_ctrl, ball_ctrl_target, world_space=True)
        
        foot_tip_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footTip"], 
            final_name=f"{self.prefix}_footTip_CTRL"
        )
        foot_tip_gen = self.create_offset_group(foot_tip_ctrl, tip_ctrl_target, world_space=True)
        cmds.xform(foot_tip_gen, r=True, t=(0, -0.3, 2))
        
        foot_bankIn_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footBankIn"], 
            final_name=f"{self.prefix}_footBankIn_CTRL"
        )
        foot_bankIn_gen = self.create_offset_group(foot_bankIn_ctrl, ball_ctrl_target, world_space=True)
        cmds.xform(foot_bankIn_gen, r=True, t=(-3, -0.3, 0))
                
        foot_bankOut_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footBankOut"], 
            final_name=f"{self.prefix}_footBankOut_CTRL"
        )
        foot_bankOut_gen = self.create_offset_group(foot_bankOut_ctrl, ball_ctrl_target, world_space=True)                
        cmds.xform(foot_bankOut_gen, r=True, t=(3, -0.3, 0))
        
        # Switch Control (Alineado con el target relativo)
        switch_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["switch"],
            final_name=f"{self.prefix}_switch_CTRL")
        switch_gen = self.group_maker.create_rig_hierarchy(switch_ctrl, an_ctrl_target)
        cmds.xform(switch_gen, r=True, t=(14, 0, 0)) # Dejamos 14, la escala -1 lo mandará a -14
        
        # NO TOCADO: Tu método original exacto de Pole Vector
        pv_pos = self.define_poleVector(self.ik_chain[0], self.ik_chain[1], self.ik_chain[2])
        pv_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["poleVector"],
            final_name=f"{self.prefix}_poleVector_CTRL")
        
        pv_gen = self.group_maker.create_rig_hierarchy(pv_ctrl, self.ik_chain[1], world_space=False)
        cmds.xform(pv_gen, ws=True, t=pv_pos)
        # Si es el lado R, invertimos su TX local en el grupo para compensar el espejo negativo
        if self.side == "R":
            cur_tx = cmds.getAttr(f"{pv_gen}.translateX")
            cmds.setAttr(f"{pv_gen}.translateX", -cur_tx)

        cmds.parent(ik_root_gen, ik_gen, foot_heel_gen, foot_ball_gen, foot_tip_gen, foot_bankIn_gen, foot_bankOut_gen, pv_gen, self.ik_grp)

        # FK Setup (Alineado con targets corregidos y solucionado el desfase del toe_tip)
        fk_ctrls = []
        fk_gens = []
        fk_targets = [th_ctrl_target, kn_ctrl_target, an_ctrl_target, ball_ctrl_target]
        for i in range(4):
            ctrl_name = f"{self.prefix}_{self.names[i]}_fk_CTRL" # names[i] soluciona el descolocado del control final
            ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["mainFk"], 
                final_name=ctrl_name
            )
            gen = self.group_maker.create_rig_hierarchy(ctrl, fk_targets[i])
            fk_ctrls.append(ctrl)
            fk_gens.append(gen)
            
        for i in range(4):
            if i == 0:
                cmds.parent(fk_gens[i], self.fk_grp)
            else:
                cmds.parent(fk_gens[i], fk_ctrls[i - 1])
            
        # ---- ESTRUCTURA DEL MIRROR (LADO R) ----
        if self.side == "R":
            mirror_behavior_grp = f"{self.root_instance.rig_name}_mirrorBehaviour_GRP"
            if cmds.objExists(mirror_behavior_grp):
                cmds.parent(self.main_rig_grp, mirror_behavior_grp)
                cmds.setAttr(f"{self.main_rig_grp}.scaleX", 1)
                cmds.setAttr(f"{self.main_rig_grp}.scaleY", 1)
                cmds.setAttr(f"{self.main_rig_grp}.scaleZ", 1)
                cmds.setAttr(f"{self.main_rig_grp}.rotateX", 0)
                cmds.setAttr(f"{self.main_rig_grp}.rotateY", 0)
                cmds.setAttr(f"{self.main_rig_grp}.rotateZ", 0)

        # ---- JERARQUIA DEL PIE ----
        cmds.parent(foot_heel_gen,    ik_ctrl)
        cmds.parent(foot_bankIn_gen,  foot_heel_ctrl)
        cmds.parent(foot_bankOut_gen, foot_bankIn_ctrl)
        cmds.parent(foot_tip_gen,     foot_bankOut_ctrl)
        cmds.parent(foot_ball_gen,    foot_tip_ctrl)

        # ---- FK CONSTRAINTS ----
        for i in range(4):
            cmds.parentConstraint(fk_ctrls[i], self.fk_chain[i])

        # ---- CONSTRAINTS IK ----
        cmds.pointConstraint(ik_root_ctrl, self.ik_chain[0], mo=True)
        cmds.parentConstraint(foot_ball_ctrl, ik_h,          mo=True)
        cmds.parentConstraint(foot_ball_ctrl, ik_footBall,   mo=True)
        cmds.parentConstraint(foot_tip_ctrl,  ik_footTip,    mo=True)
        cmds.poleVectorConstraint(pv_ctrl, ik_h)

        # ---- SWITCH atributo + visibilidad ----
        cmds.addAttr(switch_ctrl, ln="IK_FK", at="double", min=0, max=1, k=True)
        vis_rev = cmds.createNode("reverse", n=f"{self.prefix}_VIS_REV")
        cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{vis_rev}.inputX")
        cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{self.fk_grp}.visibility")
        cmds.connectAttr(f"{vis_rev}.outputX",   f"{self.ik_grp}.visibility")

        # ---- PAIR BLENDS ----
        for i in range(5):
            pbl_creator = NodeCreator(
                side=self.side,
                node_type="pairBlend",
                base_name=self.prefix,
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
            cmds.connectAttr(f"{pbl}.outTranslate",           f"{self.bind_chain[i]}.translate")
            cmds.connectAttr(f"{pbl}.outRotate",              f"{self.bind_chain[i]}.rotate")
            cmds.connectAttr(f"{switch_ctrl}.IK_FK",          f"{pbl}.weight")

        # 8. ORGANIZACIÓN FINAL
        rig_grp = f"{self.root_instance.rig_name}_rig_GRP" if self.root_instance else None
        if rig_grp and cmds.objExists(rig_grp):
            cmds.parent(self.leg_grp, rig_grp)
            cmds.parent(ik_h, ik_footBall, ik_footTip, self.leg_grp)
            cmds.parent(self.ik_chain[0], self.fk_chain[0], self.bind_chain[0], self.leg_grp)
            
        cmds.parent(switch_gen, self.main_rig_grp)    
            
        local_ctl = self.root_instance.localCtl if self.root_instance else None
        if local_ctl and cmds.objExists(local_ctl):
            if self.side == "L":
                cmds.parent(self.main_rig_grp, local_ctl)
            

        print(f"Build {self.prefix} leg completo.")