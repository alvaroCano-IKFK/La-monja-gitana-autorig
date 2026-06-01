import maya.cmds as cmds
from functools import partial 
import os
import math
import json
import guides_module
import limbs_module
import leg_module

class TwistModule(object):  
    def __init__(self, name, side, parent=None):
        self.name = name
        self.side = side
        self.parent = parent

        self.start_joint = None
        self.mid_joint = None
        self.end_joint = None

        self.base_curve = None
        self.upper_curve = None
        self.lower_curve = None

    def create_basic_curve(self, start_joint, mid_joint, end_joint):
        self.start_joint = start_joint
        self.mid_joint = mid_joint
        self.end_joint = end_joint

        pos_start_joint = cmds.xform(start_joint, q=True, ws=True, t=True)
        pos_mid_joint = cmds.xform(mid_joint, q=True, ws=True, t=True)
        pos_end_joint = cmds.xform(end_joint, q=True, ws=True, t=True)


        self.base_curve = cmds.curve(degree =1, p=[pos_start_joint, pos_mid_joint, pos_end_joint], knot=[0, 1, 2])

        detatch_result = cmds.detachCurve((f"{self.base_curve}.u[0.5]"), ch=True, k=True)

        self.upper_curve = cmds.rename(detatch_result[0], f"{self.side}_{self.name}UpperSegment_CRV")
        self.lower_curve = cmds.rename(detatch_result[1], f"{self.side}_{self.name}LowerSegment_CRV")

        history = cmds.listHistory(self.upper_curve)
        node_detach = cmds.ls(history, type="detachCurve")[0]
        cmds.setAttr(f"{node_detach}.parameter[0]", 0.5)

        cmds.rename(self.base_curve, f"{self.side}_{self.name}BaseDriver_CRV")

        print(f"[Twist {self.name.upper()}] Sistema de curvas creado con éxito para {start_joint}.")

for obj in ["jnt_TEST_A", "jnt_TEST_B", "jnt_TEST_C", "L_armUpperSegment_CRV", "L_armLowerSegment_CRV", "L_armBaseDriver_CRV"]:
if cmds.objExists(obj): cmds.delete(obj)

# 2. Creamos 3 joints en una escena vacía simulando un brazo real flexionado
cmds.select(clear=True)
j_start = cmds.joint(name="jnt_TEST_A", p=(0, 10, 0))
cmds.select(clear=True)
j_mid   = cmds.joint(name="jnt_TEST_B", p=(5, 8, -2)) # Codo metido hacia adentro
cmds.select(clear=True)
j_end   = cmds.joint(name="jnt_TEST_C", p=(10, 8, 0))

cmds.parent(j_mid, j_start)
cmds.parent(j_end, j_mid)

# 3. Instanciamos tu clase TwistModule y ejecutamos la función pasándole estos joints
test_twist = TwistModule(name="arm", side="L")
test_twist.create_basic_curve(j_start, j_mid, j_end)

# Extra para el test: seleccionamos las curvas nuevas para que las veas resaltadas en el viewport
cmds.select([test_twist.upper_curve, test_twist.lower_curve])




