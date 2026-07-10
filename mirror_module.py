import maya.cmds as cmds

class Mirror(object):
    def __init__(self, clavicule_guide="L_clavicule", thigh_guide="L_hip", rig_name="R_Character"):
        self.clavicule_guide = clavicule_guide
        self.thigh_guide = thigh_guide
        self.rig_name = rig_name
        
        # Variables para guardar los nombres de los joints creados
        self.r_clavicule = None
        self.r_hip = None

    def mirror(self):
        # mirrorJoint devuelve una lista. El primer elemento [0] es la raíz duplicada.
        if cmds.objExists(self.clavicule_guide):
            res_arm = cmds.mirrorJoint(self.clavicule_guide, myz=True, mb=True, sr=("L", "R"))
            self.r_clavicule = res_arm[0]
        
        if cmds.objExists(self.thigh_guide):
            res_leg = cmds.mirrorJoint(self.thigh_guide, myz=True, mb=True, sr=("L", "R"))
            self.r_hip = res_leg[0]
        




