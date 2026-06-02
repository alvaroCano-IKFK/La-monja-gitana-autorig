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
    
    def create_space_tracking_hierarchy(self, space_base_name, target_joint, parent_group=None):
        """
        Crea una estructura de espacio duplicada (_OFF y _TRN) alineada a un joint objetivo.
        
        :param space_base_name: Nombre personalizado base (ej: 'C_headMasterWalkFollowSpace')
        :param target_joint: El joint al que se alinearán los transformadores (ej: el joint de la cabeza)
        :param parent_group: Un grupo opcional donde emparentar el _OFF resultante (ej: 'spaces_GRP')
        :return: Una tupla con los nombres creados (off_group, trn_group)
        """
        # 1. Definir nombres definitivos
        off_name = f"{space_base_name}_OFF"
        trn_name = f"{space_base_name}_TRN"
        
        # Limpieza previa por seguridad
        for node in [trn_name, off_name]:
            if cmds.objExists(node):
                cmds.delete(node)
                
        # 2. Validar que el joint objetivo exista para poder obtener su posición
        if not cmds.objExists(target_joint):
            cmds.error(f"[Groups] El joint objetivo '{target_joint}' no existe en la escena. No se puede alinear.")
            return None
            
        # 3. Crear los grupos vacíos (Transforms nativos)
        off_group = cmds.group(em=True, n=off_name)
        trn_group = cmds.group(em=True, n=trn_name, p=off_group) # Emparentar TRN a OFF automáticamente
        
        # 4. Alinear AMBOS grupos a la posición y orientación exacta del Joint de destino
        # Al alinear el OFF, el TRN se mueve con él, pero aplicamos match al TRN también para asegurar ceros limpios
        cmds.matchTransform(off_group, target_joint, pos=True, rot=True)
        cmds.matchTransform(trn_group, target_joint, pos=True, rot=True)
        
        # 5. Organizar bajo un grupo padre si se especifica (como 'spaces_GRP')
        if parent_group:
            # Si el grupo padre no existe en la escena, lo creamos automáticamente
            if not cmds.objExists(parent_group):
                parent_group = cmds.group(em=True, n=parent_group)
            cmds.parent(off_group, parent_group)
            
        print(f"[Groups] Creada estructura de espacio: {off_group} -> {trn_group} alineada a {target_joint}")
        return off_group, trn_group
        
