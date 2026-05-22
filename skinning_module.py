import maya.cmds as cmds
import re
import rigRoot_module

class SkinningModule(object):
    """
    Versión simplificada: Duplica CUALQUIER joint que termine en 'JNT',
    le pone el sufijo 'SKN' y lo conecta al original.
    """

    def __init__(self, rig_name="Character", root_instance=None):
        self.rig_name = rig_name
        self.root_instance = root_instance
        self.skin_joints = []

        # --- FILTROS DE EXCLUSIÓN ---
        # Cualquier joint cuyo nombre CONTENGA alguno de estos strings será ignorado.
        # Añade o quita patrones según tu rig antes de llamar a build().
        # Ejemplos: "_IK_", "_FK_", "_twist_", "_helper_", "_ribbon_"
        self.exclude_patterns = [
            "_ik_",
            "_fk_",
        ]

        # Joints a excluir por NOMBRE EXACTO (útil para casos puntuales).
        # Ejemplo: self.exclude_exact = ["clavicle_L_IK_JNT", "eye_R_JNT"]
        self.exclude_exact = [
            "Character_localChest_JNT", 
            "Character_chestFix_JNT",
            "Character_hipEnd_JNT",
        ]

        # --- RE-PARENTING MANUAL ---
        # Define aquí relaciones padre-hijo personalizadas para los joints ENV.
        # Se aplican DESPUÉS de reconstruir la jerarquía automática,
        # así que sobreescriben cualquier padre que se haya asignado antes.
        #
        # Formato: lista de tuplas  (hijo_ENV,  nuevo_padre_ENV)
        # Usa los nombres ENV (sin _JNT), tal como quedan tras el renombrado.
        #
        # Ejemplos:
        #   ("clavicle_L_ENV",  "spine_05_ENV")   # clavícula izq. -> última vértebra
        #   ("clavicle_R_ENV",  "spine_05_ENV")   # clavícula der. -> última vértebra
        #   ("upperLeg_L_ENV",  "hip_C_ENV")      # pierna izq.   -> cadera
        #   ("upperLeg_R_ENV",  "hip_C_ENV")      # pierna der.   -> cadera
        self.reparent_map = [
            ("Character_body_ENV, Character_spine_0_ENV")
            ("R_Arm_clavicule_ENV","Character_spineFix_ENV"),
            ("L_Arm_clavicule_ENV","Character_spineFix_ENV"),
            ("Character_spineFix_ENV","Character_spine_4_ENV"),
            ("Character_spineFix_ENV","Character_spine_4_ENV"),
            ("Leg_R_R_thigh_ENV","Character_spine_0_ENV"),
            ("Leg_L_L_thigh_ENV","Character_spine_0_ENV"),
            ("Character_neck_01_ENV","Character_spineFix_ENV")
        ]

    def _should_exclude(self, joint_name):
        """Devuelve True si el joint debe ser ignorado en la duplicación."""
        if joint_name in self.exclude_exact:
            return True
        for pattern in self.exclude_patterns:
            if pattern in joint_name:
                return True
        return False

    def build(self):
        # 1. Crear o limpiar el grupo contenedor
        skn_grp_name = f"{self.rig_name}_SKN_GRP"
        if cmds.objExists(skn_grp_name):
            cmds.delete(skn_grp_name)
        
        main_skn_grp = cmds.group(em=True, n=skn_grp_name)

        # 2. Buscar todos los joints que terminen en JNT,
        #    excluyendo los que coincidan con los filtros configurados.
        all_jnts = [
            j for j in cmds.ls(type="joint")
            if j.endswith("JNT") and not self._should_exclude(j)
        ]

        if not all_jnts:
            cmds.warning("No se encontraron joints con el sufijo 'JNT' (o todos fueron excluidos por los filtros).")
            return

        # Log de exclusiones para debug
        excluded = [j for j in cmds.ls(type="joint") if j.endswith("JNT") and self._should_exclude(j)]
        if excluded:
            print(f"INFO: Joints excluidos por filtros ({len(excluded)}): {excluded}")

        # Diccionario para organizar la jerarquía duplicada después
        map_orig_to_skn = {}

        # 3. Primer pase: Duplicar, renombrar y conectar
        for jnt in all_jnts:
            # Creamos el nombre nuevo (ej: spine_01_JNT -> spine_01_SKN_JNT)
            # Si ya tiene 'bind', lo reemplaza; si no, lo inserta antes de JNT
            if "_bind_JNT" in jnt:
                new_name = jnt.replace("_bind_JNT", "_ENV")
            else:
                new_name = jnt.replace("_JNT", "_ENV")

            # Duplicar el joint solo (sin hijos para evitar duplicados extra)
            skn_jnt = cmds.duplicate(jnt, parentOnly=True, name=new_name)[0]
            
            # Limpiar nombre (quitar el '1' que Maya añade al final si existe)
            if skn_jnt.endswith('1'):
                skn_jnt = cmds.rename(skn_jnt, new_name)

            # Conectar (Constraint)
            cmds.parentConstraint(jnt, skn_jnt, mo=False)
            #cmds.scaleConstraint(jnt, skn_jnt, mo=False)

            # Guardar en el mapa y en la lista de resultados
            map_orig_to_skn[jnt] = skn_jnt
            self.skin_joints.append(skn_jnt)

        # 4. Segundo pase: Reconstruir la jerarquía en los SKN
        for orig_jnt, skn_jnt in map_orig_to_skn.items():
            parent_orig = cmds.listRelatives(orig_jnt, parent=True, type="joint")
            
            if parent_orig and parent_orig[0] in map_orig_to_skn:
                # Si el original tiene un padre que también duplicamos, emparentamos los SKN
                cmds.parent(skn_jnt, map_orig_to_skn[parent_orig[0]])
            else:
                # Si no tiene padre joint o el padre no es un JNT, va al grupo principal
                cmds.parent(skn_jnt, main_skn_grp)

        # 5. Re-parenting manual (sobreescribe la jerarquía automática)
        if self.reparent_map:
            for child_env, new_parent_env in self.reparent_map:
                if not cmds.objExists(child_env):
                    cmds.warning(f"REPARENT: No existe el joint hijo '{child_env}'. Revisa el nombre.")
                    continue
                if not cmds.objExists(new_parent_env):
                    cmds.warning(f"REPARENT: No existe el joint padre '{new_parent_env}'. Revisa el nombre.")
                    continue
                #cmds.parent(child_env, new_parent_env)
                print(f"REPARENT: '{child_env}'  ->  '{new_parent_env}'")

        # 6. Organizar el grupo dentro del rig_GRP si existe
        if self.root_instance:
            skel_grp = f"{self.rig_name}_C_skeleton_GRP"
            if cmds.objExists(skel_grp):
                cmds.parent(main_skn_grp, skel_grp)

        print(f"DONE: Se han procesado {len(self.skin_joints)} joints de skinning.")
        if self.reparent_map:
            print(f"INFO: {len(self.reparent_map)} re-parentings aplicados.")