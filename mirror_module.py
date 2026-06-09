import maya.cmds as cmds

class Mirror(object):
    def __init__(self, clavicule_guide="L_clavicule_start", 
                 foot_joints=None, rig_name="R_Character"):
        self.clavicule_guide = clavicule_guide
        # foot_joints: lista de joints L que están bajo L_ankle
        # ej: ["L_ball", "L_toe_tip", "L_heel"]
        self.foot_joints = foot_joints or []
        self.rig_name = rig_name
        self.r_clavicule_start = None

    def mirror(self):
        if not cmds.objExists(self.clavicule_guide):
            cmds.warning(f"No existe: {self.clavicule_guide}")
            return

        # 1. Saca los joints del pie de la jerarquía ANTES del mirror
        for jnt in self.foot_joints:
            if cmds.objExists(jnt):
                cmds.parent(jnt, world=True)

        # 2. Guarda el padre del grupo
        original_parent = cmds.listRelatives(self.clavicule_guide, parent=True)

        # 3. Saca L_clavicule_start al mundo
        if original_parent:
            cmds.parent(self.clavicule_guide, world=True)

        # 4. Mirror — ahora solo mirroriza la cadena L sin el pie
        mirrored = cmds.mirrorJoint(
            self.clavicule_guide,
            mirrorYZ=True,
            mirrorBehavior=True,
            searchReplace=("L_", "R_")
        )
        self.r_clavicule_start = mirrored[0]

        # 5. Reemparenta L al grupo original
        if original_parent:
            cmds.parent(self.clavicule_guide, original_parent[0])

        # 6. Reemparenta los joints del pie L de vuelta a L_ankle
        ankle_l = "L_ankle"
        for jnt in self.foot_joints:
            if cmds.objExists(jnt):
                cmds.parent(jnt, ankle_l)

        # 7. Mete R al mismo grupo
        if original_parent:
            cmds.parent(self.r_clavicule_start, original_parent[0])

        print(f"Mirror OK -> {self.r_clavicule_start}")
        return self.r_clavicule_start