import maya.cmds as cmds
import re
import rigRoot_module


# ----------------------------------------------------------------------
# ESPACIOS DE SKIN
#
# Cada _ENV vive en uno de dos grupos, los dos bajo <rig>_C_skeleton_GRP:
#
#   <rig>_SKN_GRP       espacio "body". Hereda el global scale (el
#                       C_skeleton_GRP lleva scaleConstraint del global_CTL).
#                       Aqui va todo lo que deforma DIRECTAMENTE la malla de
#                       body mechanics: cuerpo, boca, jaw, nariz, socket,
#                       globo ocular...
#
#   <rig>_faceSKN_GRP   espacio "face". inheritsTransform a 0: no escala.
#                       Aqui va lo que SOLO deforma la malla facial. Esa malla
#                       tiene que quedarse en bind, porque la blendShape le
#                       pasa al body todo lo que cambie: si la facial escalase,
#                       la blendShape leeria la escala como una expresion, se
#                       la sumaria al body antes del skin y el skin la volveria
#                       a escalar. Resultado: la malla a s² y los joints a s.
#
# Por defecto todo es "body". Los modulos cuyos joints skinean la facial los
# marcan con mark_skin_space(joints, FACE_SPACE): hoy, ojos y cejas.
# ----------------------------------------------------------------------
SKIN_SPACE_ATTR = "skinSpace"
BODY_SPACE = "body"
FACE_SPACE = "face"


def mark_skin_space(joints, space=FACE_SPACE):
    """
    Marca joints para que el SkinningModule cuelgue su _ENV del grupo de ese
    espacio. Se llama desde el build de cada modulo, sobre sus _JNT de skin.

    Es un atributo string en el propio joint, asi que no hace falta mantener
    ninguna lista de nombres en este archivo: si un modulo cambia como se
    llaman sus joints, la marca va con ellos.
    """
    marked = []
    for jnt in joints or []:
        if not jnt or not cmds.objExists(jnt):
            continue
        if not cmds.attributeQuery(SKIN_SPACE_ATTR, node=jnt, exists=True):
            cmds.addAttr(jnt, ln=SKIN_SPACE_ATTR, dt="string")
        cmds.setAttr(f"{jnt}.{SKIN_SPACE_ATTR}", space, type="string")
        marked.append(jnt)
    return marked


def get_skin_space(node):
    """Espacio de skin de un joint. Sin marca = body."""
    if cmds.attributeQuery(SKIN_SPACE_ATTR, node=node, exists=True):
        return cmds.getAttr(f"{node}.{SKIN_SPACE_ATTR}") or BODY_SPACE
    return BODY_SPACE


class SkinningModule(object):
    """
    Duplica CUALQUIER joint que termine en 'JNT', le pone el sufijo '_ENV' y lo
    conecta al original con un parentConstraint.

    Cada _ENV va al grupo de su espacio de skin (ver arriba). Ademas crea el
    joint de freeze de la malla facial, que antes se hacia a mano.
    """

    def __init__(self, rig_name="Character", root_instance=None,
                 create_freeze=True, freeze_name="freeze_ENV"):
        self.rig_name = rig_name
        self.root_instance = root_instance
        self.skin_joints = []
        self.face_skin_joints = []

        self.skn_grp = None
        self.face_skn_grp = None

        # Joint de freeze: sujeta toda la parte de la malla facial que no es
        # cara. Va en el espacio "face", en el origen y sin ninguna conexion.
        # El nombre se mantiene en "freeze_ENV" para que los pesos que ya
        # tienes pintados se puedan volver a importar tal cual.
        self.create_freeze = create_freeze
        self.freeze_name = freeze_name
        self.freeze_joint = None

        # --- FILTROS DE EXCLUSIÓN ---
        # Cualquier joint cuyo nombre CONTENGA alguno de estos strings será ignorado.
        # Añade o quita patrones según tu rig antes de llamar a build().
        # Ejemplos: "_IK_", "_FK_", "_twist_", "_helper_", "_ribbon_"
        #
        # OJO: la comparación es sensible a mayúsculas. Si tus joints de limbs
        # se llaman "..._IK_JNT" los dos primeros patrones no filtran nada;
        # míralo en el print de exclusiones que hace build().
        self.exclude_patterns = [
            "_ik_",
            "_fk_",

            # ----------------------------------------------------------
            # BOCA / JAW
            # Todo lo que deforma una CURVA de la cadena, no la malla.
            # Lo único que se skinea de esta zona son los 14
            # lip{Upper,Lower}Bind##_JNT y jawUpper_JNT / jawLower_JNT.
            # ----------------------------------------------------------
            "PreBind",        # todos los prebind (solo alimentan bindPreMatrix)
            "_freeze_",       # ancla central de los skinCluster de las curvas
            "_jawCorner_",    # solo conduce las JawPinchLine

            # QUITADOS con la SimpleMouthModule: "_levator_", "_depresor_" y
            # "Pinch_JNT". En la boca vieja eran joints que deformaban curvas;
            # en la nueva, {side}_<rig>_levator_JNT, _depresor_JNT,
            # _upperPinch_JNT y _lowerPinch_JNT son justo los joints de skin
            # (pasajeros de sus controles). Con estos filtros la boca se
            # construia pero se quedaba sin ningun _ENV en los labios.

            # ----------------------------------------------------------
            # OJOS
            # Lo único que se skinea es eye_mid_JNT (globo) y los
            # eyelid{Upper,Lower}Loop##AimEnd_JNT (uno por loop de párpado).
            # ----------------------------------------------------------
            "Local_JNT",              # setup local de párpados (incluye los Sub)
            "Aim_JNT",                # raíz de la cadena de aim (NO toca AimEnd_JNT)
            "_eye_mid_end_",          # end de la cadena de aim del globo
            "_eye_inner_corner_",
            "_eye_outer_corner_",
            "_eyelid_up_",
            "_eyelid_up02_",
            "_eyelid_up03_",
            "_eyelid_low_",
            "_eyelid_low02_",
            "_eyelid_low03_",
        ]

        # Joints a excluir por NOMBRE EXACTO (útil para casos puntuales).
        # Ejemplo: self.exclude_exact = ["clavicle_L_IK_JNT", "eye_R_JNT"]
        self.exclude_exact = [
            "Character_localChest_JNT",
            "Character_chestFix_JNT",
            "Character_hipEnd_JNT",

            # Conducen lipUpperLine_CRV / lipLowerLine_CRV.
            # Van por nombre exacto y no por patrón porque "lipUpper" también
            # está dentro de lipUpperBind00_JNT, que SÍ hay que skinear.
            "C_Character_lipUpper_JNT",
            "C_Character_lipLower_JNT",

            # El freeze que se hacia a mano. Ahora lo crea este modulo
            # directamente como _ENV; si el viejo sigue en la escena no se
            # duplica, o habria dos freeze_ENV peleandose por el nombre.
            "freeze_JNT",
        ]

        # Exclusión por EXPRESIÓN REGULAR, para lo que un substring no puede
        # distinguir. Caso de uso: los marcadores de loop del párpado terminan
        # en "Loop##_JNT" y los de la cadena de aim en "Loop##AimEnd_JNT", así
        # que hace falta anclar al final del nombre.
        self.exclude_regex = [
            r"Loop\d+_JNT$",   # marcadores de posición de los loops del párpado
        ]

        # --- RE-PARENTING MANUAL ---
        # Define aquí relaciones padre-hijo personalizadas para los joints ENV.
        # Se aplican DESPUÉS de reconstruir la jerarquía automática,
        # así que sobreescriben cualquier padre que se haya asignado antes.
        #
        # Formato: lista de tuplas  (hijo_ENV,  nuevo_padre_ENV)
        # Usa los nombres ENV (sin _JNT), tal como quedan tras el renombrado.
        #
        # Los dos tienen que estar en el MISMO espacio de skin: si no, el hijo
        # heredaria la escala (o la perderia) y se salta con un aviso.
        self.reparent_map = [
            ("Character_spine_0_ENV", "Character_body_ENV"),
            ("R_Arm_clavicule_ENV", "Character_spineFix_ENV"),
            ("L_Arm_clavicule_ENV", "Character_spineFix_ENV"),
            ("Character_spineFix_ENV", "Character_spine_4_ENV"),
            ("R_Leg_thigh_ENV", "Character_spine_0_ENV"),
            ("L_Leg_thigh_ENV", "Character_spine_0_ENV"),
            ("Character_neck_01_ENV", "Character_spineFix_ENV"),
        ]

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------
    def _should_exclude(self, joint_name):
        """Devuelve True si el joint debe ser ignorado en la duplicación."""
        if joint_name in self.exclude_exact:
            return True
        for pattern in self.exclude_patterns:
            if pattern in joint_name:
                return True
        for pattern in getattr(self, "exclude_regex", []):
            if re.search(pattern, joint_name):
                return True
        return False

    @staticmethod
    def _fresh_group(name, inherits_transform=True):
        """Borra el grupo si existe (rebuild) y lo crea vacio."""
        if cmds.objExists(name):
            cmds.delete(name)
        group = cmds.group(em=True, n=name)
        if not inherits_transform:
            cmds.setAttr(f"{group}.inheritsTransform", 0)
        return group

    def _build_freeze_joint(self):
        """
        Joint de freeze de la malla facial, en el origen y en el espacio face.

        No necesita _JNT ni constraint: no se mueve nunca, y por estar en
        faceSKN_GRP tampoco escala. Es justo lo que tiene que hacer la parte de
        la facial que no es cara.
        """
        if cmds.objExists(self.freeze_name):
            cmds.delete(self.freeze_name)

        cmds.select(clear=True)
        freeze = cmds.joint(n=self.freeze_name)
        cmds.select(clear=True)
        freeze = cmds.parent(freeze, self.face_skn_grp, relative=True)[0]

        self.freeze_joint = freeze
        self.face_skin_joints.append(freeze)
        self.skin_joints.append(freeze)

        return freeze

    # ------------------------------------------------------------------
    # BUILD
    # ------------------------------------------------------------------
    def build(self):
        # 1. Grupos contenedores, uno por espacio de skin
        main_skn_grp = self._fresh_group(f"{self.rig_name}_SKN_GRP")
        face_skn_grp = self._fresh_group(f"{self.rig_name}_faceSKN_GRP",
                                         inherits_transform=False)
        self.skn_grp = main_skn_grp
        self.face_skn_grp = face_skn_grp

        roots = {BODY_SPACE: main_skn_grp, FACE_SPACE: face_skn_grp}

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

        map_orig_to_skn = {}
        space_of = {}      # _ENV -> espacio de skin

        # 3. Primer pase: Duplicar, renombrar y conectar
        for jnt in all_jnts:
            if "_bind_JNT" in jnt:
                new_name = jnt.replace("_bind_JNT", "_ENV")
            else:
                new_name = jnt.replace("_JNT", "_ENV")

            # Duplicar el joint solo (sin hijos para evitar duplicados extra)
            skn_jnt = cmds.duplicate(jnt, parentOnly=True, name=new_name)[0]

            # Limpiar nombre (quitar el '1' que Maya añade al final si existe)
            if skn_jnt.endswith('1'):
                skn_jnt = cmds.rename(skn_jnt, new_name)

            # SIEMPRE a 1. cmds.duplicate copia el inheritsTransform del
            # original, y los twist _JNT lo llevan a 0 a proposito: reciben la
            # posicion en mundo de un motionPath (twist_module). Pero el _ENV va
            # con un parentConstraint bajo un grupo que escala, y con el IT a 0
            # ni hereda la escala ni el constraint le calcula bien la posicion:
            # a escala 2 el joint se acerca al origen y a 0.5 se aleja. Eran las
            # membranas de brazos y piernas.
            cmds.setAttr(f"{skn_jnt}.inheritsTransform", 1)

            cmds.parentConstraint(jnt, skn_jnt, mo=False)

            map_orig_to_skn[jnt] = skn_jnt
            space_of[skn_jnt] = get_skin_space(jnt)
            self.skin_joints.append(skn_jnt)
            if space_of[skn_jnt] == FACE_SPACE:
                self.face_skin_joints.append(skn_jnt)

        # 4. Segundo pase: Reconstruir jerarquía buscando el padre en el mapa.
        #    Un _ENV solo cuelga de otro _ENV de su mismo espacio. Si el padre
        #    natural es del otro espacio, va a la raiz del suyo: colgado de un
        #    _ENV body, uno face heredaria la escala que tiene que ignorar.
        for orig_jnt, skn_jnt in map_orig_to_skn.items():
            space = space_of[skn_jnt]
            parent_env = None

            all_parents = cmds.listRelatives(orig_jnt, allParents=True, fullPath=True) or []
            for parent_path in all_parents:
                parent_short = parent_path.split("|")[-1]
                if parent_short not in map_orig_to_skn:
                    continue

                candidate = map_orig_to_skn[parent_short]
                if space_of[candidate] == space:
                    parent_env = candidate
                else:
                    print(f"INFO: '{skn_jnt}' ({space}) no cuelga de '{candidate}' "
                          f"({space_of[candidate]}): va a la raiz de su espacio.")
                break

            cmds.parent(skn_jnt, parent_env or roots[space])

        # 5. Re-parenting manual (sobreescribe la jerarquía automática)
        for child_env, new_parent_env in self.reparent_map:
            if not cmds.objExists(child_env):
                cmds.warning(f"REPARENT: No existe el joint hijo '{child_env}'.")
                continue
            if not cmds.objExists(new_parent_env):
                cmds.warning(f"REPARENT: No existe el joint padre '{new_parent_env}'.")
                continue

            child_space = space_of.get(child_env, BODY_SPACE)
            parent_space = space_of.get(new_parent_env, BODY_SPACE)
            if child_space != parent_space:
                cmds.warning(f"REPARENT: '{child_env}' ({child_space}) y "
                             f"'{new_parent_env}' ({parent_space}) estan en espacios "
                             "de skin distintos. Se omite.")
                continue

            current_parent = cmds.listRelatives(child_env, parent=True)
            current_parent = current_parent[0] if current_parent else None

            if current_parent == new_parent_env:
                print(f"REPARENT: '{child_env}' ya está bajo '{new_parent_env}', se omite.")
                continue

            try:
                cmds.parent(child_env, new_parent_env)
                print(f"REPARENT OK: '{child_env}' -> '{new_parent_env}'")
            except Exception as e:
                cmds.warning(f"REPARENT FAILED: '{child_env}' -> '{new_parent_env}' | {e}")

        # 6. Freeze de la malla facial
        if self.create_freeze:
            self._build_freeze_joint()

        # 7. Los dos grupos al esqueleto. El faceSKN_GRP no hereda nada, asi
        #    que da igual que su padre escale: solo esta ahi para el outliner.
        if self.root_instance:
            skel_grp = f"{self.rig_name}_C_skeleton_GRP"
            if cmds.objExists(skel_grp):
                cmds.parent(main_skn_grp, face_skn_grp, skel_grp)

        body_count = len(self.skin_joints) - len(self.face_skin_joints)
        print(f"DONE: {len(self.skin_joints)} joints de skinning "
              f"({body_count} body, {len(self.face_skin_joints)} face).")