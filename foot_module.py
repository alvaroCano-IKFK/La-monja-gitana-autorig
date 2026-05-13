import maya.cmds as cmds
import controls_module

class FootModule(object):

    def __init__(self, ankle_jnt="Leg_L_ankle_bind_JNT", # El joint donde se engancha
                 ball_guide ="ball", 
                 tip_guide = "toe_tip",  
                 rig_name="Leg_L"):
                     
        self.ankle_jnt = ankle_jnt
        self.ball_guide = ball_guide
        self.tip_guide = tip_guide
        self.rig_name = rig_name
        
        self.ctrl_maker = controls_module.Controls(scale=1, color=6)

    def build(self):
        # 1. Verificar que las guías existen para evitar errores
        if not cmds.objExists(self.ball_guide) or not cmds.objExists(self.tip_guide):
            cmds.warning(f"Guías de pie no encontradas: {self.ball_guide}, {self.tip_guide}")
            return

        # 2. Obtener posiciones de las guías
        ball_pos = cmds.xform(self.ball_guide, q=True, ws=True, t=True)
        tip_pos = cmds.xform(self.tip_guide, q=True, ws=True, t=True)

        # 3. Crear los joints de BIND para el pie
        # Seleccionamos el ankle para que el ball sea su hijo directamente
        cmds.select(self.ankle_jnt)
        ball_jnt = cmds.joint(n=f"{self.rig_name}_ball_bind_JNT", p=ball_pos)
        tip_jnt = cmds.joint(n=f"{self.rig_name}_tip_bind_JNT", p=tip_pos)
        
        # 4. Orientar los joints del pie (mirando hacia adelante en X o Z según tu rig)
        cmds.joint(ball_jnt, e=True, oj="xyz", sao="yup", ch=True, zso=True)
        cmds.setAttr(f"{tip_jnt}.jointOrient", 0,0,0)

        print(f"Pie construido y unido a {self.ankle_jnt}")
        return [ball_jnt, tip_jnt]