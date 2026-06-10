import maya.cmds as cmds

class Mirror(object):
    def __init__(self, clavicule_guide="L_clavicule_start", 
                 clavicule_guide_back="L_clavicule_start_back",
                 foot_joints=None,
                 foot_joints_back=None,
                 rig_name="R_Character"):
        self.clavicule_guide = clavicule_guide
        self.clavicule_guide_back = clavicule_guide_back
        self.foot_joints = foot_joints or []
        self.foot_joints_back = foot_joints_back or []
        self.rig_name = rig_name
        self.r_clavicule_start = None
        self.r_clavicule_start_back = None

    def _mirror_chain(self, guide, foot_joints, ankle_name):
        if not cmds.objExists(guide):
            cmds.warning(f"No existe: {guide}")
            return None

        # foot_joints esperado: [ball, tip, heel]
        # Solo sacamos al mundo los joints raíz (ball y heel), tip va con ball
        ball_jnt = foot_joints[0]  # ball
        tip_jnt  = foot_joints[1]  # tip (hijo de ball, no tocar)
        heel_jnt = foot_joints[2]  # heel

        root_foot_joints = [ball_jnt, heel_jnt]  # solo los que van directo al ankle

        # 1. Saca solo ball y heel al mundo (tip sale con ball)
        for jnt in root_foot_joints:
            if cmds.objExists(jnt):
                cmds.parent(jnt, world=True)

        # 2. Guarda el padre del grupo
        original_parent = cmds.listRelatives(guide, parent=True)

        # 3. Saca al mundo
        if original_parent:
            cmds.parent(guide, world=True)

        # 4. Mirror cadena principal
        mirrored = cmds.mirrorJoint(
            guide,
            mirrorYZ=True,
            mirrorBehavior=True,
            searchReplace=("L_", "R_")
        )
        r_guide = mirrored[0]

        # 5. Reemparenta L al grupo original
        if original_parent:
            cmds.parent(guide, original_parent[0])

        # 6. Reemparenta ball y heel L de vuelta al ankle L (tip ya va con ball)
        for jnt in root_foot_joints:
            if cmds.objExists(jnt):
                cmds.parent(jnt, ankle_name)

        # 7. Crea los joints del pie R espejando X manualmente
        r_ankle_name = ankle_name.replace("L_", "R_")

        # Crea R_ball (sin padre aún)
        cmds.select(clear=True)
        ball_pos = cmds.xform(ball_jnt, q=True, ws=True, t=True)
        r_ball_name = ball_jnt.replace("L_", "R_")
        r_ball = cmds.joint(n=r_ball_name, p=(-ball_pos[0], ball_pos[1], ball_pos[2]))

        # Crea R_tip hijo de R_ball
        tip_pos = cmds.xform(tip_jnt, q=True, ws=True, t=True)
        r_tip_name = tip_jnt.replace("L_", "R_")
        r_tip = cmds.joint(n=r_tip_name, p=(-tip_pos[0], tip_pos[1], tip_pos[2]))  # ya queda hijo de r_ball

        # Emparenta R_ball al R_ankle
        if cmds.objExists(r_ankle_name):
            cmds.parent(r_ball, r_ankle_name)

        # Crea R_heel hijo de R_ankle
        cmds.select(clear=True)
        heel_pos = cmds.xform(heel_jnt, q=True, ws=True, t=True)
        r_heel_name = heel_jnt.replace("L_", "R_")
        r_heel = cmds.joint(n=r_heel_name, p=(-heel_pos[0], heel_pos[1], heel_pos[2]))
        if cmds.objExists(r_ankle_name):
            cmds.parent(r_heel, r_ankle_name)

        # 8. Mete R al mismo grupo
        if original_parent:
            cmds.parent(r_guide, original_parent[0])

        print(f"Mirror OK -> {r_guide}")
        return r_guide
    
    def mirror(self):
        # Mirror pata delantera
        self.r_clavicule_start = self._mirror_chain(
            self.clavicule_guide,
            self.foot_joints,
            "L_ankle"
        )

        # Mirror pata trasera
        self.r_clavicule_start_back = self._mirror_chain(
            self.clavicule_guide_back,
            self.foot_joints_back,
            "L_ankle_back"
        )