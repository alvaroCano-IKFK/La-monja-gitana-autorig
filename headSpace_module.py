import maya.cmds as cmds


class HeadSpacesModule(object):
    """
    Módulo para crear el sistema de Space Switching de la cabeza.

    Jerarquía construida:
    ─ C_headSpaces_GRP
      ├─ C_headMasterWalkFollowSpace_OFF
      │    ├─ C_headMasterWalkFollowSpace_TRN
      │    │    └─ orientConstraint  ← masterWalk_CTRL
      │    └─ parentConstraint       ← neck_CTRL
      ├─ C_headNeckFollowSpace_OFF
      │    ├─ C_headNeckFollowSpace_TRN
      │    │    └─ parentConstraint  ← neck_CTRL + localChest_CTRL
      │    └─ parentConstraint       ← neck_CTRL
      ├─ C_headChestFollowSpace_OFF
      │    ├─ C_headChestFollowSpace_TRN
      │    │    └─ parentConstraint  ← body_CTRL + localChest_CTRL   ← FIX
      │    └─ parentConstraint       ← neck_CTRL
      └─ C_headBodyFollowSpace_OFF
           ├─ C_headBodyFollowSpace_TRN
           │    └─ parentConstraint  ← masterWalk_CTRL + body_CTRL
           └─ parentConstraint       ← neck_CTRL

    Node graph (C_head_CTL):
      - Atributo enum  "Spaces"       (MasterWalk / Neck / Chest / Body)
      - Atributo float "Space_Follow" (0 → 1)
      - Un nodo Reverse: input ← Space_Follow
           outputX → W1 de cada TRN parentConstraint (el peso del segundo target)
           El W0 de cada TRN parentConstraint recibe (1 - Space_Follow) = reverseX
      - Un nodo Condition por espacio → conectado al C_head_SPC_parentConstraint
    """

    # ------------------------------------------------------------------
    # Definición de espacios
    #   key           : clave del enum y del naming
    #   targets_OFF   : targets del parentConstraint en _OFF  (siempre neck)
    #   targets_TRN   : targets del constraint en _TRN
    #   trn_type      : "orient" | "parent"
    # ------------------------------------------------------------------
    SPACES = [
        {
            "key":         "MasterWalk",
            "targets_OFF": ["neck_CTRL"],
            "targets_TRN": ["masterWalk_CTRL"],
            "trn_type":    "orient",
        },
        {
            "key":         "Neck",
            "targets_OFF": ["neck_CTRL"],
            "targets_TRN": ["localChest_CTRL", "neck_CTRL"],
            "trn_type":    "parent",
        },
        {
            "key":         "Chest",
            "targets_OFF": ["neck_CTRL"],
            "targets_TRN": ["body_CTRL", "localChest_CTRL"],   # ← CORRECTED
            "trn_type":    "parent",
        },
        {
            "key":         "Body",
            "targets_OFF": ["neck_CTRL"],
            "targets_TRN": ["masterWalk_CTRL", "body_CTRL"],
            "trn_type":    "parent",
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
            head_ctrl         (str): Control de cabeza (ej. "Character_head_CTRL").
            neck_ctrl         (str): Control del cuello.
            chest_ctrl        (str): Control del pecho (localChest / chestFix).
            body_ctrl         (str): Control de cuerpo.
            master_walk_ctrl  (str): Control master/walk global.
            root_instance           : Instancia del RigRoot para grupos maestros.
        """
        self.rig_name         = rig_name
        self.root_instance    = root_instance

        self.head_ctrl        = head_ctrl        or f"{rig_name}_head_CTRL"
        self.neck_ctrl        = neck_ctrl        or f"{rig_name}_neck_CTRL"
        self.chest_ctrl       = chest_ctrl       or f"{rig_name}_chestFix_CTL"
        self.body_ctrl        = body_ctrl        or f"{rig_name}_body_CTL"
        self.master_walk_ctrl = master_walk_ctrl or f"{rig_name}_global_CTL"

        self.spaces_grp = "C_headSpaces_GRP"

        # Alias interno → nombre real en escena
        self._ctrl_map = {
            "neck_CTRL":       self.neck_ctrl,
            "localChest_CTRL": self.chest_ctrl,
            "body_CTRL":       self.body_ctrl,
            "masterWalk_CTRL": self.master_walk_ctrl,
        }

        # Se rellenan durante build()
        self.head_spc            = None
        self.head_spc_constraint = None
        # Lista de (trn_node, constraint_node, trn_type) para la conexión del Reverse
        self._trn_constraint_data = []

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def build(self):
        print("[HeadSpaces] Iniciando construcción del sistema de espacios de la cabeza...")

        self._validate_required_nodes()
        self._create_spaces_container()

        trn_nodes = []
        for space_def in self.SPACES:
            trn, trn_constraint, trn_type = self._build_space_group(space_def)
            trn_nodes.append(trn)
            self._trn_constraint_data.append((trn, trn_constraint, trn_type))

        self._setup_head_spc_constraint(trn_nodes)
        self._add_head_attributes()
        self._connect_reverse_to_trn_constraints()   # ← NUEVO: wire Space_Follow + reverse
        self._connect_enum_to_spc_constraint()       # ← conecta Condition → SPC

        print("[HeadSpaces] Sistema de espacios de la cabeza construido con éxito.")

    # ------------------------------------------------------------------
    # Pasos internos
    # ------------------------------------------------------------------

    def _validate_required_nodes(self):
        required = [
            self.head_ctrl, self.neck_ctrl, self.chest_ctrl,
            self.body_ctrl, self.master_walk_ctrl,
        ]
        missing = [n for n in required if not cmds.objExists(n)]
        if missing:
            cmds.error(
                f"[HeadSpaces] Faltan nodos en la escena: {missing}\n"
                "Construye el rig completo antes de llamar a HeadSpacesModule."
            )

    def _create_spaces_container(self):
        if not cmds.objExists(self.spaces_grp):
            self.spaces_grp = cmds.group(em=True, n=self.spaces_grp)
            print(f"[HeadSpaces] Creado grupo contenedor: {self.spaces_grp}")

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
        Construye OFF + TRN para un espacio, aplica constraints y devuelve
        (trn_name, trn_constraint_name, trn_type).
        """
        key     = space_def["key"]
        prefix  = f"C_head{key}FollowSpace"
        off_name = f"{prefix}_OFF"
        trn_name = f"{prefix}_TRN"

        # Limpieza por re-build
        for node in [trn_name, off_name]:
            if cmds.objExists(node):
                cmds.delete(node)

        off_grp = cmds.group(em=True, n=off_name)
        trn_grp = cmds.group(em=True, n=trn_name, p=off_grp)

        cmds.matchTransform(off_grp, self.head_ctrl, pos=True, rot=True)
        cmds.matchTransform(trn_grp, self.head_ctrl, pos=True, rot=True)

        cmds.parent(off_grp, self.spaces_grp)

        # ── Constraint en el _OFF (parentConstraint al neck siempre) ──────────
        off_targets = [self._resolve_ctrl(t) for t in space_def["targets_OFF"]]
        cmds.parentConstraint(off_targets, off_grp, mo=True,
                              n=f"{off_name}_parentConstraint1")

        # ── Constraint en el _TRN ─────────────────────────────────────────────
        trn_targets     = [self._resolve_ctrl(t) for t in space_def["targets_TRN"]]
        trn_type        = space_def["trn_type"]
        trn_cns_name    = f"{trn_name}_{trn_type}Constraint1"

        if trn_type == "orient":
            trn_constraint = cmds.orientConstraint(
                trn_targets, trn_grp, mo=True, n=trn_cns_name)[0]
        else:
            trn_constraint = cmds.parentConstraint(
                trn_targets, trn_grp, mo=True, n=trn_cns_name)[0]

        print(f"[HeadSpaces]   '{key}' → {off_name} / {trn_name}  ({trn_type}Constraint, {len(trn_targets)} targets)")
        return trn_grp, trn_constraint, trn_type

    def _setup_head_spc_constraint(self, trn_nodes):
        """
        parentConstraint de todos los TRN al grupo _SPC de la cabeza.
        """
        base_name = self.head_ctrl
        for suffix in ["_CTRL", "_CTL"]:
            if base_name.endswith(suffix):
                base_name = base_name.rsplit(suffix, 1)[0]
                break

        self.head_spc = f"{base_name}_SPC"

        if not cmds.objExists(self.head_spc):
            cmds.error(
                f"[HeadSpaces] No se encontró '{self.head_spc}'. "
                "Asegúrate de que NeckModule construyó el control de la cabeza."
            )

        existing = cmds.listRelatives(self.head_spc, type="parentConstraint") or []
        for old in existing:
            cmds.delete(old)

        self.head_spc_constraint = cmds.parentConstraint(
            trn_nodes, self.head_spc, mo=True,
            n=f"{self.head_spc}_parentConstraint1"
        )[0]

        print(f"[HeadSpaces] parentConstraint en {self.head_spc}: {self.head_spc_constraint}")

    def _add_head_attributes(self):
        ctrl = self.head_ctrl

        # Separador visual
        if not cmds.attributeQuery("spacesSep", node=ctrl, exists=True):
            cmds.addAttr(ctrl, ln="spacesSep", nn="SPACES", at="enum",
                         en="------", k=False)
            cmds.setAttr(f"{ctrl}.spacesSep", cb=True, l=True)

        # Enum Spaces
        enum_str = ":".join(s["key"] for s in self.SPACES)
        if cmds.attributeQuery("Spaces", node=ctrl, exists=True):
            cmds.deleteAttr(f"{ctrl}.Spaces")
        cmds.addAttr(ctrl, ln="Spaces", at="enum", en=enum_str, k=True)

        # Float Space_Follow [0, 1]
        if not cmds.attributeQuery("Space_Follow", node=ctrl, exists=True):
            cmds.addAttr(ctrl, ln="Space_Follow", at="float",
                         min=0.0, max=1.0, dv=0.0, k=True)

        print(f"[HeadSpaces] Atributos añadidos a {ctrl}: Spaces, Space_Follow")

    def _connect_reverse_to_trn_constraints(self):
        """
        Crea el nodo Reverse y conecta Space_Follow para controlar el blend
        de cada constraint de los _TRN que tengan 2 targets.

        Lógica (igual que la imagen):
          Space_Follow  ──►  reverse.inputX
          reverse.outputX ──►  W0 de cada TRN_constraint  (target secundario / blend)
          Space_Follow    ──►  W1 de cada TRN_constraint  (target principal)

        Sólo se aplica a los constraints con exactamente 2 weight aliases.
        El MasterWalk (orientConstraint con 1 target) se salta.
        """
        ctrl = self.head_ctrl

        # Creamos (o reutilizamos) el nodo Reverse
        rev_name = f"C_head_spaceFollow_REV"
        if cmds.objExists(rev_name):
            cmds.delete(rev_name)
        rev = cmds.createNode("reverse", n=rev_name)

        # Space_Follow → reverse.inputX
        cmds.connectAttr(f"{ctrl}.Space_Follow", f"{rev}.inputX")

        print(f"[HeadSpaces] Nodo Reverse '{rev}' creado y conectado a Space_Follow")

        for (trn_node, trn_constraint, trn_type) in self._trn_constraint_data:
            if trn_type == "orient":
                # orientConstraint con 1 solo target — no hay blend que hacer
                continue

            weight_aliases = cmds.parentConstraint(trn_constraint, q=True, wal=True)

            if len(weight_aliases) < 2:
                # Constraint con un solo target — tampoco hay blend
                continue

            # W0 (primer target, "pasado") ← reverse.outputX  (= 1 - Space_Follow)
            cmds.connectAttr(f"{rev}.outputX", f"{trn_constraint}.{weight_aliases[0]}")

            # W1 (segundo target, "activo/destino") ← Space_Follow
            cmds.connectAttr(f"{ctrl}.Space_Follow", f"{trn_constraint}.{weight_aliases[1]}")

            print(f"[HeadSpaces]   Reverse → {trn_constraint}  [{weight_aliases[0]}=reverseX, {weight_aliases[1]}=Space_Follow]")

    def _connect_enum_to_spc_constraint(self):
        """
        Un nodo Condition por espacio conecta el enum 'Spaces' a los pesos
        del C_head_SPC_parentConstraint.
        """
        ctrl       = self.head_ctrl
        constraint = self.head_spc_constraint

        weight_aliases = cmds.parentConstraint(constraint, q=True, wal=True)

        if len(weight_aliases) != len(self.SPACES):
            cmds.warning(
                f"[HeadSpaces] Aliases ({len(weight_aliases)}) ≠ espacios ({len(self.SPACES)}). "
                "Revisa los TRN nodes."
            )

        for index, space_def in enumerate(self.SPACES):
            key       = space_def["key"]
            cond_name = f"C_head{key}FollowSpace_COND"

            if cmds.objExists(cond_name):
                cmds.delete(cond_name)

            cond = cmds.createNode("condition", n=cond_name)

            cmds.setAttr(f"{cond}.operation",     0)    # Equal
            cmds.setAttr(f"{cond}.secondTerm",    index)
            cmds.setAttr(f"{cond}.colorIfTrueR",  1.0)
            cmds.setAttr(f"{cond}.colorIfFalseR", 0.0)

            cmds.connectAttr(f"{ctrl}.Spaces",    f"{cond}.firstTerm")
            cmds.connectAttr(f"{cond}.outColorR", f"{constraint}.{weight_aliases[index]}")

            print(f"[HeadSpaces]   Condition '{cond_name}' → W[{index}] '{weight_aliases[index]}'")

        print(f"[HeadSpaces] Todos los Condition nodes conectados al SPC constraint.")

    # ------------------------------------------------------------------
    # Utilidades privadas
    # ------------------------------------------------------------------

    def _resolve_ctrl(self, alias):
        """Traduce alias interno al nombre real del control en escena."""
        return self._ctrl_map.get(alias, alias)


# =============================================================================
# EJEMPLO DE USO — añadir en build_module.py justo después de self.neck_rig.build()
# =============================================================================
#
# import headSpaces_module
#
# self.head_spaces = headSpaces_module.HeadSpacesModule(
#     rig_name         = "Character",
#     head_ctrl        = "Character_head_CTRL",
#     neck_ctrl        = "Character_neck_CTRL",
#     chest_ctrl       = "Character_chestFix_CTL",
#     body_ctrl        = "Character_body_CTL",
#     master_walk_ctrl = "Character_global_CTL",
#     root_instance    = self.root_rig,
# )
# self.head_spaces.build()