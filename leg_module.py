import maya.cmds as cmds
import math
#import controls_module
import controlsLibrary 
import guides_module
from groups_module import ControlsGroups
import rigRoot_module


class LegModule(object):

    def __init__(self, thigh_guide="L_hip", 
                 knee_guide="L_knee", 
                 ankle_guide="L_ankle",
                 ball_guide ="L_ball", 
                 tip_guide = "L_toe_tip",
                 heel_guide = "L_heel",  
                 rig_name="Leg_L",
                 root_instance= None):
                     
        self.thigh_guide = thigh_guide
        self.knee_guide = knee_guide
        self.ankle_guide = ankle_guide
        self.ball_guide = ball_guide
        self.tip_guide = tip_guide
        self.heel_guide = heel_guide        
        
        self.names = ["L_thigh", "L_knee", "L_ankle","L_ball","L_toe_tip","L_heel"]
        self.rig_name = rig_name
        #self.ctrl_maker = controls_module.Controls(scale=2, color=6)
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
        return self.group_maker.create_rig_hierarchy(
            ctrl, 
            target_proc, 
            match_rotation=orient, 
            world_space=world_space
    )
    def define_poleVector(self, start, mid, end, distance=5):
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
        # 1. POSICIONES
        pos_th = cmds.xform(self.thigh_guide, q=True, ws=True, t=True)
        pos_kn = cmds.xform(self.knee_guide, q=True, ws=True, t=True)
        pos_an = cmds.xform(self.ankle_guide, q=True, ws=True, t=True)
        pos_ball = cmds.xform(self.ball_guide, q=True, ws=True, t=True)
        pos_tip = cmds.xform(self.tip_guide, q=True, ws=True, t=True)
        pos_heel = cmds.xform(self.heel_guide, q=True, ws=True, t=True)

        # 2. BIND CHAIN (Orientación específica para pierna)
        cmds.select(clear=True)
        b_th = cmds.joint(n=f"{self.rig_name}_{self.names[0]}_bind_JNT", p=pos_th)
        cmds.select(clear=True)
        b_kn = cmds.joint(n=f"{self.rig_name}_{self.names[1]}_bind_JNT", p=pos_kn)
        cmds.select(clear=True)
        b_an = cmds.joint(n=f"{self.rig_name}_{self.names[2]}_bind_JNT", p=pos_an)
        cmds.select(clear=True)
        b_ba = cmds.joint(n=f"{self.rig_name}_{self.names[3]}_bind_JNT", p=pos_ball)
        cmds.select(clear=True)
        b_tip = cmds.joint(n=f"{self.rig_name}_{self.names[4]}_bind_JNT", p=pos_tip)         
        cmds.select(clear=True)        
               
        # Limpiamos todo rastro de orientaciones previas

            
        cmds.parent(b_kn, b_th)
        cmds.parent(b_an, b_kn)
        cmds.parent(b_ba, b_an)
        cmds.parent(b_tip, b_ba)
        
        for jnt in [b_th, b_kn, b_an,b_ba,b_tip]:
            cmds.setAttr(f"{jnt}.jointOrient", 0, 0, 0)

        # El lado R tiene posiciones X negativas, necesita sao inverso
        sao = "xup" if self.rig_name.endswith("_R") else "xdown"
        cmds.joint(b_th, edit=True, oj="xyz", sao=sao, ch=True, zso=True)
        
        self.bind_chain = [b_th, b_kn, b_an, b_ba, b_tip]

        # Duplicate chains
        def duplicate_chain(suffix):
            new_jnts = cmds.duplicate(self.bind_chain[0], rc=True)
            root = cmds.rename(new_jnts[0], f"{self.rig_name}_{self.names[0]}_{suffix}_JNT")
            children = cmds.listRelatives(root, ad=True, type="joint")
            children.reverse()
            kn = cmds.rename(children[0], f"{self.rig_name}_{self.names[1]}_{suffix}_JNT")
            an = cmds.rename(children[1], f"{self.rig_name}_{self.names[2]}_{suffix}_JNT")
            ball = cmds.rename(children[2], f"{self.rig_name}_{self.names[3]}_{suffix}_JNT")
            tip = cmds.rename(children[3], f"{self.rig_name}_{self.names[4]}_{suffix}_JNT")
            return [root, kn, an, ball, tip]
            
        self.fk_chain = duplicate_chain("fk")
        self.ik_chain = duplicate_chain("ik")

        # 3. GRUPOS
        self.main_grp = cmds.group(em=True, n=f"{self.rig_name}_legControls_GRP")
        ik_grp = cmds.group(em=True, n=f"{self.rig_name}_ik_GRP", p=self.main_grp)
        fk_grp = cmds.group(em=True, n=f"{self.rig_name}_fk_GRP", p=self.main_grp)
        self.leg_grp =cmds.group(em=True, n=f"{self.rig_name}_leg_GRP") 
        self.leg_joints_grp = cmds.group(em=True, n=f"Leg_joints_GRP")
        
        
        # 4. IK SETUP
        ik_h, ik_eff = cmds.ikHandle(sj=self.ik_chain[0], ee=self.ik_chain[2], 
                                     sol="ikRPsolver", n=f"{self.rig_name}_IKH")
        
        #foot set up
        ik_footTip, ik_footTip_eff = cmds.ikHandle(sj=self.ik_chain[3],ee=self.ik_chain[4],
                      sol="ikSCsolver", n=f"{self.rig_name}_footTip_HDL")
        ik_footBall, ik_footBall_eff = cmds.ikHandle(sj=self.ik_chain[2],ee=self.ik_chain[3],
                      sol="ikSCsolver", n=f"{self.rig_name}_footBall_HDL")        
        
        cmds.parent(ik_h, ik_footTip, ik_footBall, self.leg_grp)
        
        # IK Controls
        ik_root_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footRoot"], 
            final_name=f"{self.rig_name}_legRoot_CTRL"
        )
        ik_root_off = self.create_offset_group(ik_root_ctrl, self.ik_chain[0], orient = True)
                
        
        ik_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["mainIk"], 
            final_name=f"{self.rig_name}_legIk_CTRL"
        )
        ik_off = self.create_offset_group(ik_ctrl, self.ik_chain[2], world_space = True)
        
        foot_heel_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footHeel"], 
            final_name=f"{self.rig_name}_footHeel_CTRL"
        )
        foot_heel_off = self.create_offset_group(foot_heel_ctrl, self.heel_guide,world_space = True)        
        cmds.xform(foot_heel_off, r=True, t=(0,-0.3,-2))
        
        foot_ball_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footBall"], 
            final_name=f"{self.rig_name}_footBall_CTRL"
        )
        foot_ball_off = self.create_offset_group(foot_ball_ctrl, self.ik_chain[3],world_space = True)
        
        foot_tip_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footTip"], 
            final_name=f"{self.rig_name}_footTip_CTRL"
        )
        foot_tip_off = self.create_offset_group(foot_tip_ctrl, self.ik_chain[4],world_space = True)
        cmds.xform(foot_tip_off, r=True, t=(0,-0.3,2))
        
        foot_bankIn_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footBankIn"], 
            final_name=f"{self.rig_name}_footBankIn_CTRL"
        )
        foot_bankIn_off = self.create_offset_group(foot_bankIn_ctrl, self.ik_chain[3],world_space = True)
        cmds.xform(foot_bankIn_off, r=True, t=(-3,-0.3,0))
                
        foot_bankOut_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footBankOut"], 
            final_name=f"{self.rig_name}_footBankOut_CTRL"
        )
        foot_bankOut_off = self.create_offset_group(foot_bankOut_ctrl, self.ik_chain[3],world_space = True)                
        cmds.xform(foot_bankOut_off, r=True, t=(3,-0.3,0))
        
        
        #ORDEN IK_CTLS
        
        cmds.parent(foot_heel_off,ik_ctrl)
        cmds.parent(foot_bankIn_off,foot_heel_ctrl)
        cmds.parent(foot_bankOut_off,foot_bankIn_ctrl)
        cmds.parent(foot_tip_off,foot_bankOut_ctrl)
        cmds.parent(foot_ball_off,foot_tip_ctrl)
        
       
        #SOLVERS ORG
        cmds.pointConstraint(ik_root_ctrl, self.ik_chain[0], mo=True)                        
        cmds.parentConstraint(foot_ball_ctrl, ik_h, mo=True)
        cmds.parentConstraint(foot_ball_ctrl,ik_footBall, mo=True)
        cmds.parentConstraint(foot_tip_ctrl,ik_footTip, mo=True)
        
        
        # --- POLE VECTOR INTEGRATION ---
        pv_pos = self.define_poleVector(self.ik_chain[0], self.ik_chain[1], self.ik_chain[2])
        pv_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["poleVector"], 
            final_name=f"{self.rig_name}_poleVector_CTRL"
        )
        pv_off = self.create_offset_group(pv_ctrl, self.ik_chain[1], world_space = False)
        cmds.xform(pv_off, ws=True, t=pv_pos)
        cmds.poleVectorConstraint(pv_ctrl, ik_h)
        
        cmds.parent(ik_off,ik_root_off,pv_off, ik_grp)
        
       

        # 5. FK SETUP (Idem anterior)
        fk_ctrls = []
        for i in range(4):
            jnt = self.fk_chain[i]
            ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["mainFk"], 
            final_name=f"{self.rig_name}_{self.names[i]}_CTRL"
        )
            off = self.create_offset_group(ctrl, jnt, orient = True)
            cmds.parentConstraint(ctrl, jnt)
            fk_ctrls.append({"ctrl": ctrl, "off": off})
            if i > 0: cmds.parent(off, fk_ctrls[i-1]["ctrl"])
        cmds.parent(fk_ctrls[0]["off"], fk_grp)

        # 6. SWITCH
        switch_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["switch"], 
            final_name=f"{self.rig_name}_switch_CTRL"
        )
        switch_off = self.create_offset_group(switch_ctrl, b_an)
        cmds.xform(switch_off, r=True, t=(10, 0, 0)) 
        cmds.addAttr(switch_ctrl, ln="IK_FK", at="double", min=0, max=1, k=True)
        cmds.parent(switch_off, self.main_grp)
        
        vis_rev = cmds.createNode("reverse", n=f"{self.rig_name}_VIS_REV")
        cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{vis_rev}.inputX")
        cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{fk_grp}.visibility")
        cmds.connectAttr(f"{vis_rev}.outputX", f"{ik_grp}.visibility")

        # 7. PAIR BLENDS
        for i in range(3):
            pbl = cmds.createNode("pairBlend", n=f"{self.bind_chain[i]}_PBL")
            cmds.setAttr(f"{pbl}.rotInterpolation", 1)
            cmds.connectAttr(f"{self.ik_chain[i]}.translate", f"{pbl}.inTranslate1")
            cmds.connectAttr(f"{self.ik_chain[i]}.rotate", f"{pbl}.inRotate1")
            cmds.connectAttr(f"{self.fk_chain[i]}.translate", f"{pbl}.inTranslate2")
            cmds.connectAttr(f"{self.fk_chain[i]}.rotate", f"{pbl}.inRotate2")
            cmds.connectAttr(f"{pbl}.outTranslate", f"{self.bind_chain[i]}.translate")
            cmds.connectAttr(f"{pbl}.outRotate", f"{self.bind_chain[i]}.rotate")
            cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{pbl}.weight")
        
        #cmds.parent(self.bind_chain,self.ik_chain,self.fk_chain,self.leg_joints_grp)

        # 1. Primero metemos las 3 raíces en el grupo específico de joints de la pierna
        cmds.parent(self.bind_chain[0], self.ik_chain[0], self.fk_chain[0], self.leg_joints_grp)
        
        # 2. Luego emparentamos ese grupo al rig principal
        rig_grp = (
            f"{self.root_instance.rig_name}_rig_GRP"
            if self.root_instance else None
        )
        
        if rig_grp and cmds.objExists(rig_grp):
            cmds.parent(self.leg_joints_grp, rig_grp)
            # También es buena idea emparentar los controles y el grupo de sistemas (IK handles)
            cmds.parent(self.main_grp, rig_grp) 
            cmds.parent(self.leg_grp, rig_grp) # Este contiene los IK Handles

        # METER LOS CONTROLADORES DENTRO DEL LOCAL CONTROL            
        local_ctl = self.root_instance.localCtl if self.root_instance else None

        if local_ctl and cmds.objExists(local_ctl):
            cmds.parent(self.main_grp, local_ctl)

