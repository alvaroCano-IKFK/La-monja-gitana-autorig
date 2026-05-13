import maya.cmds as cmds

class ControlsGroups(object):
    def create_rig_hierarchy(self, ctrl, target, match_rotation=True, world_space=True):
        """
        Crea la jerarquía de grupos para un control y lo posiciona.
        :param world_space: Si es True, posiciona el grupo raíz en coordenadas globales. 
                            Si es False, el grupo se queda en el origen (0,0,0).
        """
        # 1. Limpieza de nombres
        base_name = ctrl.replace("_CTRL", "")
        suffixes = ["GRP", "SPC", "OFF", "SDK", "ANIM"]
        
        for s in suffixes:
            n = f"{base_name}_{s}"
            if cmds.objExists(n):
                cmds.delete(n)
        
        # 2. Creación de jerarquía (de padre a hijo)
        grp = cmds.group(em=True, n=f"{base_name}_GRP")
        spc = cmds.group(em=True, n=f"{base_name}_SPC", p=grp)
        off = cmds.group(em=True, n=f"{base_name}_OFF", p=spc)
        sdk = cmds.group(em=True, n=f"{base_name}_SDK", p=off)
        anim = cmds.group(em=True, n=f"{base_name}_ANIM", p=sdk)
        
        # 3. Emparentar el control al último grupo
        cmds.parent(ctrl, anim)
        
        # 4. Posicionamiento (Match Transform)
        if cmds.objExists(target) and world_space:
            # Movemos el grupo raíz (GRP) a la posición del target
            cmds.matchTransform(grp, target, pos=True, rot=match_rotation)
            
        return grp