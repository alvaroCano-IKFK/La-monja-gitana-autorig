import maya.cmds as cmds

class Reorienter(object):
    def __init__(self):
        self.arm_guides = ["shoulder", "elbow", "wrist"]
        self.leg_guides = ["hip", "knee", "ankle"]

    def get_short_name(self, obj):
        return obj.split("|")[-1]

    def reorient_chain(self, joint_list):
        """
        Reorienta joints usando el comando delete(joint, ch=True) y 
        limpiando transformaciones, evitando dependencias circulares.
        """
        # 1. Filtrar solo joints que existen
        clean_list = [j for j in joint_list if cmds.objExists(j)]
        if len(clean_list) < 2: return

        for i in range(len(clean_list) - 1):
            curr = clean_list[i]
            child = clean_list[i+1]
            
            # 2. Desparentar temporalmente al hijo para que no herede la rotación
            # y evitar el "Cycle Warning" de Maya
            child_parent = cmds.listRelatives(child, p=True)
            if child_parent:
                cmds.parent(child, w=True)

            # 3. Orientar el eje X hacia el hijo usando el comando nativo de joints
            # Esto es mucho más limpio que un aimConstraint
            cmds.delete(cmds.aimConstraint(child, curr, 
                                          aim=(1,0,0), 
                                          u=(0,1,0), 
                                          wuo=child, 
                                          wut="vector"))
            
            # 4. Transferir la rotación al Joint Orient y limpiar el Rotate
            rot = cmds.getAttr(f"{curr}.r")[0]
            jo = cmds.getAttr(f"{curr}.jo")[0]
            
            # Sumamos la rotación actual al joint orient existente
            cmds.setAttr(f"{curr}.jo", jo[0]+rot[0], jo[1]+rot[1], jo[2]+rot[2])
            cmds.setAttr(f"{curr}.r", 0, 0, 0)

            # 5. Volver a parentar
            cmds.parent(child, curr)

        # El último joint de la cadena siempre debe tener orientación 0
        last_jnt = clean_list[-1]
        cmds.setAttr(f"{last_jnt}.jo", 0, 0, 0)
        cmds.setAttr(f"{last_jnt}.r", 0, 0, 0)

    def run_reorient(self):
        print("Reorientando guías mediante Joint Orient...")
        self.reorient_chain(self.arm_guides)
        #self.reorient_chain(self.leg_guides)
        cmds.select(clear=True)
        print("Reorientación completada sin ciclos.")