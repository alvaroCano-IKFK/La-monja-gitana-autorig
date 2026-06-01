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

        self.upper_non_roll = None
        self.lower_non_roll = None

    def create_basic_curve(self, start_joint, mid_joint, end_joint):
        self.start_joint = start_joint
        self.mid_joint = mid_joint
        self.end_joint = end_joint

        pos_start_joint = cmds.xform(start_joint, q=True, ws=True, t=True)
        pos_mid_joint = cmds.xform(mid_joint, q=True, ws=True, t=True)
        pos_end_joint = cmds.xform(end_joint, q=True, ws=True, t=True)


        self.base_curve = cmds.curve(degree =1, bezier=2, p=[(pos_start_joint, pos_mid_joint, pos_end_joint)], knot=[0, 1])

        detatch_result = cmds.detachCurve((f"{self.base_curve}.u[0.5]"), ch=True, ko=True)

        self.upper_curve = cmds.rename(detatch_result[0], f"{self.name}UpperSegment_CRV")
        self.lower_curve = cmds.rename(detatch_result[1], f"{self.name}LowerSegment_CRV")

        history = cmds.listHistory(self.upper_curve)
        node_detach = cmds.ls(history, type="detachCurve")[0]
        cmds.setAttr(f"{node_detach}.parameter[0]", 0.5)

        cmds.rename(self.base_curve, f"{self.side}_{self.name}BaseDriver_CRV")


        def probar_modulo_en_escena():
            # 1. Limpieza rápida por si repites la ejecución del script
            objetos_test = ["test_start_JNT", "test_mid_JNT", "test_end_JNT", 
                            "L_armUpperSegment_CRV", "L_armLowerSegment_CRV", "L_armBaseDriver_CRV"]
            for obj in objetos_test:
                if cmds.objExists(obj): cmds.delete(obj)

            # 2. Creamos 3 joints simulando la posición de tu bind_chain (Bíceps largo, antebrazo corto)
            cmds.select(clear=True)
            j1 = cmds.joint(name="test_start_JNT", p=(0, 6, 0))
            cmds.select(clear=True)
            j2 = cmds.joint(name="test_mid_JNT", p=(8, 4, 0))
            cmds.select(clear=True)
            j3 = cmds.joint(name="test_end_JNT", p=(12, 4, 0))
            
            # Los emparentamos para que visualmente parezca un brazo real
            cmds.parent(j2, j1)
            cmds.parent(j3, j2)

            # 3. Instanciamos tu TwistModule y lo ejecutamos pasando los joints de test
            twist = TwistModule(name="arm", side="L")
            twist.create_basic_curve(start_joint=j1, mid_joint=j2, end_joint=j3)

# Lanzamos la prueba automática
probar_modulo_en_escena()

