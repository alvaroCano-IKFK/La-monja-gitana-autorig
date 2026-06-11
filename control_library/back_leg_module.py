import maya.cmds as cmds
import math
import leg_module
import controlsLibrary 
import guides_module
from groups_module import ControlsGroups
import rigRoot_module
import nodeCreator_module
import hip_module
from nodeCreator_module import NodeCreator
import curvature_module
import twist_module
import chest_module

class BackLeg(object): 
    def __init__(self,
                 clavicule_start_guide="L_clavicule_start",
                 clavicule_guide="clavicule", 
                 thigh_guide="hip", 
                 knee_guide="knee", 
                 ankle_guide="ankle",
                 ball_guide ="ball", 
                 tip_guide = "toe_tip",
                 heel_guide = "heel",  
                 rig_name="Character",
                 side = "L",
                 hip_instance= None,
                 root_instance= None):
        

        self.clavicule_start_guide = clavicule_start_guide
        self.clavicule_guide = clavicule_guide             
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
                              "poleVector": "legPoleVectorControl",
                              "clavicule":  "claviculeControl"}
        
        self.group_maker = ControlsGroups()
        self.leg_grp = None
        
        self.root_instance = root_instance 
        self.hip_instance = hip_instance

        self.bind_chain = []
        self.ik_chain = []
        self.fk_chain = []
        self.leg_joints_grp = None

        def load_spring_plugin (self):
            """
            Assegura que el plugin esta carregat
            """
            if not cmds.pluginInfo("ikSpringSolver", q=True, loaded=True):
                try:
                    cmds.loadPlugin("ikSpringSolver")
                except:
                    cmds.error("No ikSpringSolver found")
        
        def create_ik_spring(self):
            self.load_spring_plugin()

            hip_joint= self.ik_chain[0]
            knee_joint= self.ik_chain[1]
            ankle_joint = self.ik_chain[2]

            hip_pos = cmds.xform(self.hip_guide, q=True, ws=True, t=True)
            knee_pos = cmds.xform(self.knee_guide, q=True, ws=True, t=True)
            ankle_pos = cmds.xform(self.ankle_guide, q=True, ws=True, t=True)

            ik_spring_name = f"{self.prefix}_backLeg_HDL"
            ik_spring_hdl = cmds.ikHandle(sj= hip_joint, ee= ankle_joint, sol="ikSpringSolver", name=ik_spring_name)
            ik_hdk = ik_spring_hdl[0]







