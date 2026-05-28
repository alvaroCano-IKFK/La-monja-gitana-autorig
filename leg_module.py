import maya.cmds as cmds
import math
import controlsLibrary
import groups_module
import rigRoot_module
import nodeCreator_module
import build_module
from nodeCreator_module import NodeCreator


class LegModule(object):

    def __init__(self, thigh_guide="hip",
                 knee_guide="knee",
                 ankle_guide="ankle",
                 ball_guide="ball",
                 tip_guide="toe_tip",
                 heel_guide="heel",
                 rig_name="Character",
                 root_instance=None,
                 side="L"):

        self.thigh_guide  = thigh_guide
        self.knee_guide   = knee_guide
        self.ankle_guide  = ankle_guide
        self.ball_guide   = ball_guide
        self.tip_guide    = tip_guide
        self.heel_guide   = heel_guide

        self.side   = side
        self.prefix = f"{self.side}_{rig_name}"

        self.names    = ["thigh", "knee", "ankle", "ball", "toe_tip", "heel"]
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
            "poleVector":  "legPoleVectorControl"
        }

        self.group_maker = groups_module.ControlsGroups()

        self.root_instance  = root_instance
        self.bind_chain     = []
        self.ik_chain       = []
        self.fk_chain       = []

        self.main_grp       = None
        self.main_rig_grp   = None
        self.ik_grp         = None
        self.fk_grp         = None
        self.leg_grp        = None
        self.leg_joints_grp = None

    # ------------------------------------------------------------------
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
    def build(self):

        # ---- 1. POSICIONES ----
        pos_th   = cmds.xform(self.thigh_guide, q=True, ws=True, t=True)
        pos_kn   = cmds.xform(self.knee_guide,  q=True, ws=True, t=True)
        pos_an   = cmds.xform(self.ankle_guide, q=True, ws=True, t=True)
        pos_ball = cmds.xform(self.ball_guide,  q=True, ws=True, t=True)
        pos_tip  = cmds.xform(self.tip_guide,   q=True, ws=True, t=True)

        # ----------------------------------------------------------------
        # 2. BIND CHAIN
        # Mismo patrón que limbs_module:
        #   joint en posición → matchTransform(rot) desde la guía → parentar → makeIdentity
        # Esto garantiza que los bind joints hereden la orientación real de las guías
        # en lugar de recalcularla solo por geometría (que no funciona para el lado R).
        # ----------------------------------------------------------------
        cmds.select(clear=True)
        b_th = cmds.joint(n=f"{self.prefix}_{self.names[0]}_bind_JNT", p=pos_th)
        cmds.matchTransform(b_th, self.thigh_guide, rot=True, pos=False)

        cmds.select(clear=True)
        b_kn = cmds.joint(n=f"{self.prefix}_{self.names[1]}_bind_JNT", p=pos_kn)
        cmds.matchTransform(b_kn, self.knee_guide, rot=True, pos=False)

        cmds.select(clear=True)
        b_an = cmds.joint(n=f"{self.prefix}_{self.names[2]}_bind_JNT", p=pos_an)
        cmds.matchTransform(b_an, self.ankle_guide, rot=True, pos=False)

        cmds.select(clear=True)
        b_ba = cmds.joint(n=f"{self.prefix}_{self.names[3]}_bind_JNT", p=pos_ball)
        cmds.matchTransform(b_ba, self.ball_guide, rot=True, pos=False)

        cmds.select(clear=True)
        b_tip = cmds.joint(n=f"{self.prefix}_{self.names[4]}_bind_JNT", p=pos_tip)
        cmds.matchTransform(b_tip, self.tip_guide, rot=True, pos=False)

        cmds.select(clear=True)

        cmds.parent(b_kn,  b_th)
        cmds.parent(b_an,  b_kn)
        cmds.parent(b_ba,  b_an)
        cmds.parent(b_tip, b_ba)

        # makeIdentity hornea la rotación copiada en jointOrient,
        # igual que limbs_module hace con b_cl tras parentar
        cmds.makeIdentity(b_th, apply=True, t=0, r=1, s=0, n=0, pn=1)

        self.bind_chain = [b_th, b_kn, b_an, b_ba, b_tip]

        # ---- DUPLICATE CHAINS ----
        def duplicate_chain(suffix):
            new_jnts = cmds.duplicate(self.bind_chain[0], rc=True)
            root     = cmds.rename(new_jnts[0], f"{self.prefix}_{self.names[0]}_{suffix}_JNT")
            children = cmds.listRelatives(root, ad=True, type="joint")
            children.reverse()
            kn   = cmds.rename(children[0], f"{self.prefix}_{self.names[1]}_{suffix}_JNT")
            an   = cmds.rename(children[1], f"{self.prefix}_{self.names[2]}_{suffix}_JNT")
            ball = cmds.rename(children[2], f"{self.prefix}_{self.names[3]}_{suffix}_JNT")
            tip  = cmds.rename(children[3], f"{self.prefix}_{self.names[4]}_{suffix}_JNT")
            return [root, kn, an, ball, tip]

        self.fk_chain = duplicate_chain("fk")
        self.ik_chain = duplicate_chain("ik")

        # ---- 3. GRUPOS ----
        self.main_rig_grp   = cmds.group(em=True, n=f"{self.prefix}_legControls_GRP")
        self.main_grp       = self.main_rig_grp
        self.ik_grp         = cmds.group(em=True, n=f"{self.prefix}_ik_GRP",  p=self.main_rig_grp)
        self.fk_grp         = cmds.group(em=True, n=f"{self.prefix}_fk_GRP",  p=self.main_rig_grp)
        self.leg_grp        = cmds.group(em=True, n=f"{self.prefix}_leg_GRP")
        self.leg_joints_grp = cmds.group(em=True, n=f"{self.prefix}_legJoints_GRP")


        ik_h, _        = cmds.ikHandle(sj=self.ik_chain[0], ee=self.ik_chain[2],
                                        sol="ikRPsolver", n=f"{self.prefix}_IKH")
        ik_footBall, _ = cmds.ikHandle(sj=self.ik_chain[2], ee=self.ik_chain[3],
                                        sol="ikSCsolver", n=f"{self.prefix}_footBall_HDL")
        ik_footTip, _  = cmds.ikHandle(sj=self.ik_chain[3], ee=self.ik_chain[4],
                                        sol="ikSCsolver", n=f"{self.prefix}_footTip_HDL")

        #cmds.parent(ik_h, ik_footBall, ik_footTip, self.leg_grp)
        cmds.select(clear=True)

        # ---- 5. CONTROLES IK ----
        # Crear → offset cosmético en WS (mientras flotan) → DESPUÉS parentar jerarquía

        ik_root_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footRoot"],
            final_name=f"{self.prefix}_legRoot_CTRL")
        ik_root_gen = self.group_maker.create_rig_hierarchy(ik_root_ctrl, self.ik_chain[0])

        ik_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["mainIk"],
            final_name=f"{self.prefix}_legIk_CTRL")
        ik_ctrl_gen = self.group_maker.create_rig_hierarchy(ik_ctrl, self.ik_chain[2])

        foot_heel_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footHeel"],
            final_name=f"{self.prefix}_footHeel_CTRL")
        foot_heel_gen = self.group_maker.create_rig_hierarchy(foot_heel_ctrl, self.heel_guide)
        

        foot_ball_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footBall"],
            final_name=f"{self.prefix}_footBall_CTRL")
        foot_ball_gen = self.group_maker.create_rig_hierarchy(foot_ball_ctrl, self.ik_chain[3])

        foot_tip_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footTip"],
            final_name=f"{self.prefix}_footTip_CTRL")
        foot_tip_gen = self.group_maker.create_rig_hierarchy(foot_tip_ctrl, self.ik_chain[4])
        

        foot_bankIn_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footBankIn"],
            final_name=f"{self.prefix}_footBankIn_CTRL")
        foot_bankIn_gen = self.group_maker.create_rig_hierarchy(foot_bankIn_ctrl, self.ik_chain[3])
        

        foot_bankOut_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["footBankOut"],
            final_name=f"{self.prefix}_footBankOut_CTRL")
        foot_bankOut_gen = self.group_maker.create_rig_hierarchy(foot_bankOut_ctrl, self.ik_chain[3])

        pv_pos = self.define_poleVector(self.ik_chain[0], self.ik_chain[1], self.ik_chain[2])
        pv_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["poleVector"],
            final_name=f"{self.prefix}_poleVector_CTRL")
        pv_gen = self.group_maker.create_rig_hierarchy(pv_ctrl, self.ik_chain[1], world_space=False)

        # ---- 6. CONTROLES FK ----
        fk_ctrls = []
        fk_gens  = []
        for i in range(4):
            ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["mainFk"],
                final_name=f"{self.prefix}_{self.names[i]}_fk_CTRL")
            gen = self.group_maker.create_rig_hierarchy(ctrl, self.fk_chain[i])
            fk_ctrls.append(ctrl)
            fk_gens.append(gen)

        # ---- 7. SWITCH ----
        switch_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["switch"],
            final_name=f"{self.prefix}_switch_CTRL")
        switch_gen = self.group_maker.create_rig_hierarchy(switch_ctrl, b_an)
        cmds.xform(switch_gen, r=True, t=(10 if self.side == "L" else -10, 0, 0))

        # ---- 8. MIRROR BEHAVIOUR (lado R) ----
        # Después de posicionar todos los _gen en WS, antes de parentar la jerarquía
        if self.side == "R":
            mirror_behavior_grp = f"{self.root_instance.rig_name}_mirrorBehaviour_GRP"
            cmds.parent(self.main_rig_grp, mirror_behavior_grp)
            
            cmds.setAttr(f"{self.main_rig_grp}.scaleX", 1)
            cmds.setAttr(f"{self.main_rig_grp}.scaleY", 1)
            cmds.setAttr(f"{self.main_rig_grp}.scaleZ", 1)
            cmds.setAttr(f"{self.main_rig_grp}.rotateY", 0)
            cmds.setAttr(f"{self.main_rig_grp}.rotateX", 0)
            cmds.setAttr(f"{self.main_rig_grp}.rotateZ",0)

        # ---- 9. PARENTAR a grupos Y POSICIONAR----
        cmds.parent(ik_root_gen, ik_ctrl_gen, pv_gen, self.ik_grp)
        cmds.parent(switch_gen, self.main_rig_grp)
        cmds.matchTransform(ik_root_gen, self.thigh_guide)
        cmds.matchTransform(ik_ctrl_gen, self.ankle_guide)
        cmds.matchTransform(foot_heel_gen, self.heel_guide)
        cmds.matchTransform(foot_ball_gen, self.ball_guide)
        cmds.matchTransform(foot_tip_gen, self.tip_guide)
        cmds.xform(foot_heel_gen, r=True, t=(0, -0.3, -2))
        cmds.xform(foot_tip_gen, r=True, t=(0, -0.3, 2))
        cmds.xform(foot_bankIn_gen, r=True, t=(-3, -0.3, 0))
        cmds.xform(foot_bankOut_gen, r=True, t=(3, -0.3, 0))
        cmds.xform(pv_gen, ws=True, t=pv_pos)




        # Jerarquía del pie: ik_ctrl → heel → bankIn → bankOut → tip → ball
        cmds.parent(foot_heel_gen,    ik_ctrl)
        cmds.parent(foot_bankIn_gen,  foot_heel_ctrl)
        cmds.parent(foot_bankOut_gen, foot_bankIn_ctrl)
        cmds.parent(foot_tip_gen,     foot_bankOut_ctrl)
        cmds.parent(foot_ball_gen,    foot_tip_ctrl)

        # FK jerarquía
        for i in range(4):
            cmds.parentConstraint(fk_ctrls[i], self.fk_chain[i])
            if i == 0:
                cmds.parent(fk_gens[i], self.fk_grp)
            else:
                cmds.parent(fk_gens[i], fk_ctrls[i - 1])

        # ---- 10. CONSTRAINTS ----
        cmds.pointConstraint(ik_root_ctrl, self.ik_chain[0], mo=True)
        cmds.parentConstraint(foot_ball_ctrl, ik_h,          mo=True)
        cmds.parentConstraint(foot_ball_ctrl, ik_footBall,   mo=True)
        cmds.parentConstraint(foot_tip_ctrl,  ik_footTip,    mo=True)
        cmds.poleVectorConstraint(pv_ctrl, ik_h)

        # ---- 11. SWITCH atributo + visibilidad ----
        cmds.addAttr(switch_ctrl, ln="IK_FK", at="double", min=0, max=1, k=True)
        vis_rev = cmds.createNode("reverse", n=f"{self.prefix}_VIS_REV")
        cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{vis_rev}.inputX")
        cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{self.fk_grp}.visibility")
        cmds.connectAttr(f"{vis_rev}.outputX",   f"{self.ik_grp}.visibility")

        # ---- 12. PAIR BLENDS ----
        for i in range(3):
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

        # ---- 13. ORGANIZACIÓN FINAL ----
        cmds.parent(self.bind_chain[0], self.ik_chain[0], self.fk_chain[0],
                    self.leg_joints_grp)

        rig_grp = (f"{self.root_instance.rig_name}_rig_GRP"
                   if self.root_instance else None)

        if rig_grp and cmds.objExists(rig_grp):
            cmds.parent(self.leg_grp,        rig_grp)

        local_ctl = self.root_instance.localCtl if self.root_instance else None


        print(f"Build {self.prefix} leg completo.")
