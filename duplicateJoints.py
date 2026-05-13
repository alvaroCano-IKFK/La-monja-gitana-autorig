import maya.cmds as cmds


class SkinningModule(object):
    """
    Duplica todos los joints '_bind_JNT' de la escena y crea joints de skinning
    limpios ('_SKN_JNT') sin constraints ni conexiones de rig.

    Flujo:
        1. Recoge todos los joints cuyo nombre termina en '_bind_JNT'.
        2. Los filtra para quedarse solo con las RAÍCES de cada cadena
           (aquellos cuyo padre NO es también un _bind_JNT).
        3. Por cada raíz, duplica la cadena completa y renombra
           _bind_JNT -> _SKN_JNT en todos los descendientes.
        4. Conecta cada _SKN_JNT a su _bind_JNT correspondiente mediante
           un parentConstraint (mo=False), de modo que hereda posición
           y rotación exactas en todo momento.
        5. Organiza todo bajo un grupo dedicado dentro del rig_GRP.

    Uso típico (en el builder principal, DESPUÉS de construir todos los módulos):

        skn = SkinningModule(rig_name="Character", root_instance=root_instance)
        skn.build()
        # skn.skin_joints  →  lista plana con todos los _SKN_JNT creados
    """

    BIND_SUFFIX = "_bind_JNT"
    SKN_SUFFIX  = "_SKN_JNT"

    def __init__(self, rig_name="Character", root_instance=None):
        self.rig_name      = rig_name
        self.root_instance = root_instance

        # Resultados accesibles desde fuera
        self.skin_joints   = []   # lista plana de todos los SKN joints creados
        self.skn_grp       = None # grupo raíz que los contiene

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _all_bind_joints(self):
        """Devuelve todos los joints *_bind_JNT presentes en escena."""
        all_jnts = cmds.ls(type="joint") or []
        return [j for j in all_jnts if j.endswith(self.BIND_SUFFIX)]

    def _is_root_bind(self, jnt):
        """
        True si el joint es raíz de una cadena bind, es decir,
        su padre directo NO es también un _bind_JNT.
        """
        parents = cmds.listRelatives(jnt, parent=True, type="joint") or []
        if not parents:
            return True
        return not parents[0].endswith(self.BIND_SUFFIX)

    def _duplicate_chain(self, root_bind):
        """
        Duplica la cadena completa a partir de root_bind y renombra
        todos los joints de _bind_JNT a _SKN_JNT.
        Devuelve la lista de joints SKN creados (orden raíz → hojas).
        """
        # Duplicar manteniendo jerarquía interna
        duped = cmds.duplicate(root_bind, renameChildren=True)
        root_skn = duped[0]

        # Recolectar todos los nodos duplicados (raíz + descendientes)
        descendants = cmds.listRelatives(root_skn, allDescendants=True, type="joint") or []
        all_nodes   = [root_skn] + descendants

        renamed = []
        for node in all_nodes:
            # El duplicado puede tener sufijo numérico de Maya (e.g. "_bind_JNT1")
            # Primero limpiamos ese sufijo, luego sustituimos el sufijo bind
            clean = node
            # Quitar sufijo numérico añadido por Maya al duplicar
            import re
            clean = re.sub(r"(\D)(\d+)$", r"\1", clean)
            # Sustituir sufijo bind por skn
            new_name = clean.replace(self.BIND_SUFFIX, self.SKN_SUFFIX)

            # Si ya existe un nodo con ese nombre (poco probable pero seguro)
            if cmds.objExists(new_name) and new_name != node:
                cmds.rename(new_name, new_name + "_OLD_TMP")

            final = cmds.rename(node, new_name)
            renamed.append(final)

        return renamed

    def _connect_skn_to_bind(self, skn_jnt, bind_jnt):
        """
        Conecta skn_jnt a bind_jnt con parentConstraint.
        Primero elimina cualquier constraint preexistente en el SKN joint
        para evitar conflictos si se llama a build() más de una vez.
        """
        existing = (
            cmds.listRelatives(skn_jnt, type="parentConstraint") or []
        )
        if existing:
            cmds.delete(existing)

        cmds.parentConstraint(bind_jnt, skn_jnt, mo=False)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def build(self):
        """
        Construye todos los joints de skinning.
        Puede llamarse de nuevo (re-build) sin dejar basura:
        si el grupo ya existe lo elimina antes de reconstruir.
        """
        # Nombre del grupo de skinning
        skn_grp_name = f"{self.rig_name}_SKN_GRP"

        # Re-build limpio
        if cmds.objExists(skn_grp_name):
            cmds.delete(skn_grp_name)

        self.skn_grp    = cmds.group(em=True, n=skn_grp_name)
        self.skin_joints = []

        # Grupo padre global
        rig_grp = (
            f"{self.root_instance.rig_name}_rig_GRP"
            if self.root_instance else None
        )

        # ---- Recoger raíces de cadenas bind ----
        bind_roots = [j for j in self._all_bind_joints() if self._is_root_bind(j)]

        if not bind_roots:
            cmds.warning(
                "SkinningModule: no se encontraron joints '_bind_JNT' en escena. "
                "Asegúrate de construir los módulos de rig antes de llamar a build()."
            )
            return

        print(f"SkinningModule: encontradas {len(bind_roots)} cadenas bind raíz.")

        for root_bind in bind_roots:
            # 1. Duplicar y renombrar cadena
            skn_chain = self._duplicate_chain(root_bind)

            # 2. Mover la raíz SKN al grupo de skinning (romper herencia del duplicado)
            root_skn = skn_chain[0]
            cmds.parent(root_skn, self.skn_grp)

            # 3. Recoger bind joints de la cadena original (mismo orden)
            bind_descendants = (
                cmds.listRelatives(root_bind, allDescendants=True, type="joint") or []
            )
            bind_chain_ordered = [root_bind] + list(reversed(bind_descendants))

            # 4. Conectar cada SKN a su bind correspondiente
            skn_descendants = (
                cmds.listRelatives(root_skn, allDescendants=True, type="joint") or []
            )
            skn_chain_ordered = [root_skn] + list(reversed(skn_descendants))

            for skn_j, bind_j in zip(skn_chain_ordered, bind_chain_ordered):
                self._connect_skn_to_bind(skn_j, bind_j)
                self.skin_joints.append(skn_j)

        # 5. Organización final
        if rig_grp and cmds.objExists(rig_grp):
            cmds.parent(self.skn_grp, rig_grp)

        print(
            f"SkinningModule: {len(self.skin_joints)} joints SKN creados "
            f"bajo '{self.skn_grp}'."
        )
        print("Joints de skinning:")
        for j in self.skin_joints:
            print(f"  {j}")



        print(f"SkinningModule: skinCluster '{skin_cluster[0]}' creado sobre '{mesh}'.")
