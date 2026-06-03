import maya.cmds as cmds


class HeadSpacesModule(object):
    """
    Módulo para crear el sistema de Space Switching de la cabeza.

    Estructura que construye:
    ─ Spaces (grupo contenedor)
      ├─ C_headMasterWalkFollowSpace_OFF
      │    ├─ C_headMasterWalkFollowSpace_TRN
      │    │    └─ C_headMasterWalkFollowSpace_TRN_orientConstraint1  (← MasterWalk orient)
      │    └─ C_headMasterWalkFollowSpace_OFF_parentConstraint1       (← neck_CTRL parent)
      │
      ├─ C_headNeckFollowSpace_OFF
      │    ├─ C_headNeckFollowSpace_TRN
      │    │    └─ C_headNeckFollowSpace_TRN_parentConstraint1        (← neck_CTRL + localChest parent)
      │    └─ C_headNeckFollowSpace_OFF_parentConstraint1             (← neck_CTRL parent)
      │
      ├─ C_headChestFollowSpace_OFF
      │    ├─ C_headChestFollowSpace_TRN
      │    │    └─ C_headChestFollowSpace_TRN_parentConstraint1       (← localChest + localChest parent) *ver docstring
      │    └─ C_headChestFollowSpace_OFF_parentConstraint1            (← neck_CTRL parent)
      │
      └─ C_headBodyFollowSpace_OFF
           ├─ C_headBodyFollowSpace_TRN
           │    └─ C_headBodyFollowSpace_TRN_parentConstraint1        (← masterWalk + body parent)
           └─ C_headBodyFollowSpace_OFF_parentConstraint1             (← neck_CTRL parent)

    Después conecta los 4 TRN al C_head_SPC_parentConstraint1 mediante nodos Condition.
    Añade en C_head_CTRL:
      - Atributo enum  "Spaces"       (MasterWalk / Neck / Chest / Body)
      - Atributo float "Space_Follow" (0 → 1)
    """

    # ------------------------------------------------------------------
    # Definición de espacios
    # Cada entrada: (key, OFF/TRN alias, targets_OFF, targets_TRN, constraint_type_TRN)
    #
    #   key            : nombre corto usado en el enum y en el naming
    #   targets_OFF    : lista de controles que van al parentConstraint del _OFF
    #   targets_TRN    : lista de controles que van al constraint del _TRN
    #   trn_type       : "orient" | "parent"  — tipo de constraint en el _TRN
    # ------------------------------------------------------------------
    SPACES = [
        {
            "key":          "MasterWalk",
            "targets_OFF":  ["neck_CTRL"],               # parentConstraint en el _OFF
            "targets_TRN":  ["masterWalk_CTRL"],         # orientConstraint en el _TRN
            "trn_type":     "orient",
        },
        {
            "key":          "Neck",
            "targets_OFF":  ["neck_CTRL"],
            "targets_TRN":  ["neck_CTRL", "localChest_CTRL"],
            "trn_type":     "parent",
        },
        {
            "key":          "Chest",
            "targets_OFF":  ["neck_CTRL"],
            "targets_TRN":  ["localChest_CTRL", "localChest_CTRL"],  # doble por si se quiere blending
            "trn_type":     "parent",
        },
        {
            "key":          "Body",
            "targets_OFF":  ["neck_CTRL"],
            "targets_TRN":  ["masterWalk_CTRL", "body_CTRL"],
            "trn_type":     "parent",
        },
    ]

    def __init__(
        self,
        rig_name="Character",
        head_ctrl=None,
        neck_ctrl=None,
        chest_ctrl=None,
        body_ctrl=None,
        master_walk_ctrl=None,
        root_instance=None,
    ):
        """
        Args:
            rig_name          (str): Prefijo del personaje (ej. "Character").
            head_ctrl         (str): Nombre del control de cabeza (ej. "Character_head_CTRL").
            neck_ctrl         (str): Control del cuello.
            chest_ctrl        (str): Control del pecho (localChest / chestFix).
            body_ctrl         (str): Control de cuerpo.
            master_walk_ctrl  (str): Control master/walk global.
            root_instance           : Instancia del RigRoot (para obtener grupos maestros).
        """
        self.rig_name         = rig_name
        self.root_instance    = root_instance

        # Resolvemos nombres por defecto si no se pasan explícitamente
        self.head_ctrl        = head_ctrl        or f"{rig_name}_head_CTRL"
        self.neck_ctrl        = neck_ctrl        or f"{rig_name}_neck_CTRL"
        self.chest_ctrl       = chest_ctrl       or f"{rig_name}_chestFix_CTL"
        self.body_ctrl        = body_ctrl        or f"{rig_name}_body_CTL"
        self.master_walk_ctrl = master_walk_ctrl or f"{rig_name}_global_CTL"

        # Grupo contenedor de todos los spaces
        self.spaces_grp = f"C_headSpaces_GRP"

        # Mapa de alias → control real (se sustituye en _resolve_ctrl)
        self._ctrl_map = {
            "neck_CTRL":        self.neck_ctrl,
            "localChest_CTRL":  self.chest_ctrl,
            "body_CTRL":        self.body_ctrl,
            "masterWalk_CTRL":  self.master_walk_ctrl,
        }

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def build(self):
        """Punto de entrada principal. Construye todo el sistema."""
        print("[HeadSpaces] Iniciando construcción del sistema de espacios de la cabeza...")

        self._validate_required_nodes()
        self._create_spaces_container()

        trn_nodes = []
        for space_def in self.SPACES:
            trn = self._build_space_group(space_def)
            trn_nodes.append(trn)

        self._setup_head_spc_constraint(trn_nodes)
        self._add_head_attributes()
        self._connect_enum_to_constraint(trn_nodes)

        print("[HeadSpaces] Sistema de espacios de la cabeza construido con éxito.")

    # ------------------------------------------------------------------
    # Pasos internos
    # ------------------------------------------------------------------

    def _validate_required_nodes(self):
        """Lanza un error si algún control clave no existe."""
        required = [
            self.head_ctrl,
            self.neck_ctrl,
            self.chest_ctrl,
            self.body_ctrl,
            self.master_walk_ctrl,
        ]
        missing = [n for n in required if not cmds.objExists(n)]
        if missing:
            cmds.error(
                f"[HeadSpaces] Faltan los siguientes nodos en la escena: {missing}\n"
                "Asegúrate de construir el rig completo antes de llamar a HeadSpacesModule."
            )

    def _create_spaces_container(self):
        """Crea (o reutiliza) el grupo contenedor 'C_headSpaces_GRP'."""
        if not cmds.objExists(self.spaces_grp):
            self.spaces_grp = cmds.group(em=True, n=self.spaces_grp)
            print(f"[HeadSpaces] Creado grupo contenedor: {self.spaces_grp}")

        # Intentamos meterlo bajo el grupo de rig maestro si existe
        rig_grp = (
            f"{self.root_instance.rig_name}_rig_GRP"
            if self.root_instance else None
        )
        if rig_grp and cmds.objExists(rig_grp):
            current_parent = cmds.listRelatives(self.spaces_grp, parent=True)
            if not current_parent or current_parent[0] != rig_grp:
                cmds.parent(self.spaces_grp, rig_grp)

    def _build_space_group(self, space_def):
        """
        Construye la pareja OFF + TRN para un espacio dado y añade sus constraints.
        Devuelve el nombre del nodo TRN para usarlo después en el parentConstraint del SPC.
        """
        key = space_def["key"]
        prefix = f"C_head{key}FollowSpace"

        off_name = f"{prefix}_OFF"
        trn_name = f"{prefix}_TRN"

        # Limpieza previa por si ya existían de una build anterior
        for node in [trn_name, off_name]:
            if cmds.objExists(node):
                cmds.delete(node)

        # Creamos los grupos vacíos
        off_grp = cmds.group(em=True, n=off_name)
        trn_grp = cmds.group(em=True, n=trn_name, p=off_grp)

        # Alineamos ambos a la posición/orientación de la cabeza
        cmds.matchTransform(off_grp, self.head_ctrl, pos=True, rot=True)
        cmds.matchTransform(trn_grp, self.head_ctrl, pos=True, rot=True)

        # Emparentamos el OFF al grupo contenedor de espacios
        cmds.parent(off_grp, self.spaces_grp)

        # ── Constraint en el _OFF (siempre parentConstraint al neck_CTRL) ──
        off_targets = [self._resolve_ctrl(t) for t in space_def["targets_OFF"]]
        cmds.parentConstraint(off_targets, off_grp, mo=True,
                              n=f"{off_name}_parentConstraint1")

        # ── Constraint en el _TRN ──
        trn_targets = [self._resolve_ctrl(t) for t in space_def["targets_TRN"]]
        if space_def["trn_type"] == "orient":
            cmds.orientConstraint(trn_targets, trn_grp, mo=True,
                                  n=f"{trn_name}_orientConstraint1")
        else:
            cmds.parentConstraint(trn_targets, trn_grp, mo=True,
                                  n=f"{trn_name}_parentConstraint1")

        print(f"[HeadSpaces]   Espacio '{key}' creado → {off_name} / {trn_name}")
        return trn_grp

    def _setup_head_spc_constraint(self, trn_nodes):
        """
        Aplica un parentConstraint de todos los TRN al grupo _SPC de la cabeza.
        El _SPC es el segundo grupo en la jerarquía creada por groups_module.py:
            C_head_GRP → C_head_SPC → C_head_OFF → C_head_SDK → C_head_ANIM → C_head_CTRL
        """
        # Deducimos el nombre del _SPC a partir del nombre del control de cabeza
        base_name = self.head_ctrl
        for suffix in ["_CTRL", "_CTL"]:
            if base_name.endswith(suffix):
                base_name = base_name.rsplit(suffix, 1)[0]
                break

        self.head_spc = f"{base_name}_SPC"

        if not cmds.objExists(self.head_spc):
            cmds.error(
                f"[HeadSpaces] No se encontró el grupo SPC '{self.head_spc}'. "
                "Asegúrate de que el NeckModule ya construyó el control de la cabeza."
            )

        # Eliminamos un constraint previo si existiera (re-build seguro)
        existing = cmds.listRelatives(self.head_spc, type="parentConstraint") or []
        for old in existing:
            cmds.delete(old)

        constraint_name = f"{self.head_spc}_parentConstraint1"
        self.head_spc_constraint = cmds.parentConstraint(
            trn_nodes, self.head_spc,
            mo=True,
            n=constraint_name
        )[0]

        print(f"[HeadSpaces] parentConstraint creado en {self.head_spc}: {self.head_spc_constraint}")

    def _add_head_attributes(self):
        """
        Añade al control de cabeza:
          - Separador visual 'SPACES' (enum no keyable, channel box visible)
          - 'Spaces'       → enum con las claves MasterWalk / Neck / Chest / Body
          - 'Space_Follow' → float [0, 1] keyable
        """
        ctrl = self.head_ctrl

        # ── Separador visual ──────────────────────────────────────────
        if not cmds.attributeQuery("spacesSep", node=ctrl, exists=True):
            cmds.addAttr(ctrl, ln="spacesSep", nn="SPACES", at="enum",
                         en="------", k=False)
            cmds.setAttr(f"{ctrl}.spacesSep", cb=True, l=True)

        # ── Atributo enum Spaces ──────────────────────────────────────
        enum_str = ":".join(s["key"] for s in self.SPACES)
        if not cmds.attributeQuery("Spaces", node=ctrl, exists=True):
            cmds.addAttr(ctrl, ln="Spaces", at="enum", en=enum_str, k=True)
        else:
            # Si ya existe pero con distintos valores, lo recreamos
            cmds.deleteAttr(f"{ctrl}.Spaces")
            cmds.addAttr(ctrl, ln="Spaces", at="enum", en=enum_str, k=True)

        # ── Atributo float Space_Follow ───────────────────────────────
        if not cmds.attributeQuery("Space_Follow", node=ctrl, exists=True):
            cmds.addAttr(ctrl, ln="Space_Follow", at="float",
                         min=0.0, max=1.0, dv=0.0, k=True)

        print(f"[HeadSpaces] Atributos añadidos a {ctrl}: Spaces, Space_Follow")

    def _connect_enum_to_constraint(self, trn_nodes):
        """
        Conecta el atributo enum 'Spaces' al parentConstraint del _SPC mediante
        nodos Condition (uno por espacio), exactamente como en la imagen del NodeEditor.

        Además conecta Space_Follow a través de un nodo Reverse para hacer
        blend entre el espacio activo (1.0) y el espacio anterior (0.0).
        """
        ctrl        = self.head_ctrl
        constraint  = self.head_spc_constraint

        # Obtenemos los alias de peso del constraint en el mismo orden que trn_nodes
        weight_aliases = cmds.parentConstraint(constraint, q=True, wal=True)

        if len(weight_aliases) != len(self.SPACES):
            cmds.warning(
                f"[HeadSpaces] El número de aliases ({len(weight_aliases)}) no coincide "
                f"con el número de espacios ({len(self.SPACES)}). Revisa los TRN nodes."
            )

        for index, space_def in enumerate(self.SPACES):
            key = space_def["key"]

            # Nombre del nodo condition siguiendo la convención del NodeEditor
            cond_name = f"C_head{key}FollowSpace_COND"

            # Limpiamos si ya existía
            if cmds.objExists(cond_name):
                cmds.delete(cond_name)

            cond = cmds.createNode("condition", n=cond_name)

            # Si Spaces == index  →  peso = 1.0  (este espacio activo)
            # Si Spaces != index  →  peso = 0.0
            cmds.setAttr(f"{cond}.operation",      0)      # Equal
            cmds.setAttr(f"{cond}.secondTerm",     index)
            cmds.setAttr(f"{cond}.colorIfTrueR",   1.0)
            cmds.setAttr(f"{cond}.colorIfFalseR",  0.0)

            cmds.connectAttr(f"{ctrl}.Spaces", f"{cond}.firstTerm")
            cmds.connectAttr(f"{cond}.outColorR", f"{constraint}.{weight_aliases[index]}")

            print(f"[HeadSpaces]   Condition '{cond_name}' → peso[{index}] '{weight_aliases[index]}'")

        print(f"[HeadSpaces] Todos los Condition nodes conectados al constraint del SPC.")

    # ------------------------------------------------------------------
    # Utilidades privadas
    # ------------------------------------------------------------------

    def _resolve_ctrl(self, alias):
        """
        Traduce un alias interno (ej. 'neck_CTRL') al nombre real del control en escena.
        Si el alias no está en el mapa, lo devuelve tal cual (por si se pasa un nombre directo).
        """
        return self._ctrl_map.get(alias, alias)


