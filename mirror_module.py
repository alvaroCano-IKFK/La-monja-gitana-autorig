import maya.cmds as cmds

class Mirror(object):
    def __init__(self, clavicule_guide="L_clavicule", thigh_guide="L_hip", lip_end="L_lip_end", eyebow_end="L_eyebrow_root_01", rig_name="R_Character"):
        self.clavicule_guide = clavicule_guide
        self.thigh_guide = thigh_guide
        self.lip_end = lip_end
        self.eyebrow_end = eyebow_end
        self.rig_name = rig_name
        
        # Variables para guardar los nombres de los joints creados
        self.r_clavicule = None
        self.r_hip = None
        self.r_lip_end = None
        self.r_eyebrow_end = None

    def mirror(self):
        # mirrorJoint devuelve una lista. El primer elemento [0] es la raíz duplicada.
        if cmds.objExists(self.clavicule_guide):
            res_arm = cmds.mirrorJoint(self.clavicule_guide, myz=True, mb=True, sr=("L", "R"))
            self.r_clavicule = res_arm[0]
        
        if cmds.objExists(self.thigh_guide):
            res_leg = cmds.mirrorJoint(self.thigh_guide, myz=True, mb=True, sr=("L", "R"))
            self.r_hip = res_leg[0]
        
        if cmds.objExists(self.lip_end):
            res_lip = cmds.mirrorJoint(self.lip_end, myz=True, mb=True, sr=("L", "R"))
            self.r_lip_end = res_lip[0] 
        else:
            cmds.warning(f"[Mirror] No se encontró {self.lip_end} en la escena, no se puede mirrorizar la boca.")

        if cmds.objExists(self.eyebrow_end):
            self.r_eyebrows = []
        for i in range(1, 11):
            brow_name = f"L_eyebrow_root_{i:02d}"
            
            if cmds.objExists(brow_name):
                res_brow = cmds.mirrorJoint(brow_name, myz=True, mb=True, sr=("L", "R"))
                if res_brow:
                    self.r_eyebrows.append(res_brow[0])
            else:
                cmds.warning(f"[Mirror] No se encontró {brow_name} en la escena.")
