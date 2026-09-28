import maya.cmds as cmds

import controlsLibrary
import groups_module
import module_specs


class SocketModule(module_specs.FeaturesMixin):
    """
    Socket del ojo: una capa de control por encima del parpado.

    ESTRUCTURA
    ----------
    Cuatro controles principales en los ejes y ocho sub:

        principales   up, low, in, out
        sub directos  upSub, lowSub, inSub, outSub
                      cada uno colgado EN JERARQUIA de su principal
        sub del medio upIn, upOut, lowIn, lowOut
                      cada uno con un parentConstraint al 50% entre los dos
                      principales que tiene al lado

    Por que el del medio va con constraint y no colgado: esta entre DOS
    principales y tiene que hacer caso a los dos. Colgarlo de uno solo lo
    ataria a ese, y al mover el otro se quedaria clavado. Un constraint con
    pesos es lo unico que sabe repartir.

    Y por que los directos van colgados y no con constraint: solo tienen un
    padre, asi que la jerarquia ya hace el trabajo y ademas deja sus canales
    libres para el animador.

    POSICION Y ORIENTACION
    ----------------------
    Salen de las guias, las ocho. Incluidas las diagonales, que tienen guia
    propia en vez de calcularse como punto medio: el borde del parpado es
    curvo y el punto medio de la recta entre 'up' e 'in' cae por dentro del
    ojo.

    LADO R
    ------
    Los controles R se construyen como reflejo del L, no como una copia
    girada. Ver _insert_mirror.
    """

    # sub del medio -> los dos principales entre los que esta
    BETWEEN = {
        "upIn": ("up", "in"),
        "upOut": ("up", "out"),
        "lowIn": ("low", "in"),
        "lowOut": ("low", "out"),
    }

    MAIN_KEYS = ("up", "low", "in", "out")

    # Peso del PRIMER principal de la pareja (el otro se lleva 1 - peso).
    BETWEEN_WEIGHT = 0.5

    def __init__(self, rig_name="Character", side="L", root_instance=None,
                 features=None, guide_prefix=None, control_size=0.35):

        self._init_features("socket", features)

        self.rig_name = rig_name
        self.side = side
        self.root_instance = root_instance
        self.prefix = f"{side}_{rig_name}_socket"

        # Las guias existen con el prefijo del lado: MIRROR crea las R.
        self.guide_prefix = guide_prefix or f"{side}_socket"

        self.control_size = control_size

        # Formas de la libreria, igual que self.styles de limbs_module. Antes
        # aqui habia un "circle" a pelo, que NO existe en la libreria: de ahi
        # los avisos de "No se encontro el control circle".
        self.styles = {
            "main": "circleControl",
            "sub":  "circleControl",
        }

        # Los CVs se giran 90 grados en X porque los controles de la libreria
        # estan dibujados en el plano XZ (tumbados, para el cuerpo) y aqui
        # tienen que mirar al frente, como la cara.
        self.cv_rotation = (90.0, 0.0, 0.0)

        # Los sub se dibujan mas pequenos que su principal para poder
        # pincharlos: comparten sitio, asi que si midieran lo mismo quedarian
        # uno encima de otro.
        self.sub_cv_scale = 0.6

        # Tamano de TODOS los controles de este modulo, sobre los CVs. Los de
        # la libreria estan dibujados para el cuerpo y en la cara salen
        # enormes. Este es el numero que hay que tocar si siguen sin cuadrar.
        self.cv_scale = 0.25
        self.groups = groups_module.ControlsGroups()

        self.controls = {}
        self.joints = {}
        self.control_groups = []

        # control -> nodo por el que se lee desde fuera (ver _insert_mirror)
        self.output_nodes = {}

        self.module_group = None

    # ------------------------------------------------------------------
    # GUIAS
    # ------------------------------------------------------------------
    def guide_name(self, key):
        return f"{self.guide_prefix}_{key}"

    def _required_guides(self):
        keys = list(self.MAIN_KEYS)

        if self.has("between_controls"):
            keys += list(self.BETWEEN)

        return [self.guide_name(key) for key in keys]

    def _missing_guides(self):
        return [guide for guide in self._required_guides()
                if not cmds.objExists(guide)]

    # ------------------------------------------------------------------
    # CONTROLES
    # ------------------------------------------------------------------
    def _make_control(self, name, target, mirrored=False, style="main",
                      cv_scale=None):
        """
        Control con su jerarquia GRP > SPC > OFF > SDK > ANIM, colocado y
        orientado contra una guia.

        Args:
            style: clave de self.styles.
            cv_scale: factor extra sobre los CVs, para los sub.
        """
        if cmds.objExists(name):
            cmds.delete(name)

        control = controlsLibrary.create_control_from_lib(
            lib_name=self.styles.get(style, "circleControl"), final_name=name
        )

        # Giro y tamano van en los CVs, no en el transform: el transform tiene
        # que quedarse con los canales a cero y con su pivote en la guia,
        # porque de el cuelgan el joint y los constraints.
        controlsLibrary.transform_shape(
            control, rotate=self.cv_rotation,
            scale=self.cv_scale * (cv_scale if cv_scale is not None else 1.0)
        )

        group = self.groups.create_rig_hierarchy(
            control, target, match_rotation=True, world_space=True
        )

        self.output_nodes[control] = control
        self.control_groups.append(group)

        if mirrored:
            self._insert_mirror(control, group)

        return control, group

    def _insert_mirror(self, control, group):
        """
        Mete el reflejo en X dentro de la jerarquia de un control R.

            GRP              <- constraints, marco normal
              _mirror_GRP    <- scaleX = -1
                SPC > ... > CTRL
                              _out_TRN  <- scaleX = -1

        Sin esto, los mismos valores en los dos lados NO dan movimientos en
        espejo: las guias R salen de mirrorJoint con mirror behaviour, que es
        una rotacion, y una rotacion no puede representar un reflejo. Con la
        escala negativa el control R es el reflejo exacto del L.

        El reflejo va DEBAJO del GRP porque un parentConstraint no sabe
        escribir un reflejo: si el nodo constreñido viviera en un espacio
        negativo, devolveria orientaciones raras.

        El _out_TRN lo deshace para todo lo que lea este control desde fuera
        (su joint, y los constraints de los sub del medio). Un joint con
        escala negativa invierte las normales del skin.
        """
        base = control[:-len("_CTRL")] if control.endswith("_CTRL") else control
        spc = f"{base}_SPC"

        if not cmds.objExists(spc):
            cmds.warning(f"[Socket] No encuentro '{spc}'; '{control}' se queda "
                         f"sin espejo.")
            return None

        mirror = cmds.group(em=True, n=f"{base}_mirror_GRP", parent=group)
        cmds.setAttr(f"{mirror}.scaleX", -1)

        # relative=True: el SPC conserva sus valores locales. Sin esto
        # cmds.parent compensaria la escala y el reflejo se anularia solo.
        cmds.parent(spc, mirror, relative=True)

        out = cmds.group(em=True, n=f"{base}_out_TRN", parent=control)
        cmds.setAttr(f"{out}.scaleX", -1)
        self.output_nodes[control] = out

        return mirror

    def _out(self, control):
        """Nodo por el que hay que leer un control desde fuera."""
        return self.output_nodes.get(control, control)

    # ------------------------------------------------------------------
    # JOINTS
    # ------------------------------------------------------------------
    def _make_joint(self, name, control):
        """
        Joint en el control, constreñido a el. Los joints cuelgan de los SUB,
        no de los principales: los principales mueven la zona entera a traves
        de sus sub, asi que poner joints tambien en ellos seria deformar dos
        veces la misma cosa.
        """
        if cmds.objExists(name):
            cmds.delete(name)

        driver = self._out(control)

        cmds.select(clear=True)
        joint = cmds.joint(n=name)
        cmds.matchTransform(joint, driver, pos=True, rot=True)

        cmds.parentConstraint(driver, joint, mo=False)
        cmds.scaleConstraint(driver, joint, mo=False)

        cmds.select(clear=True)

        return joint

    # ------------------------------------------------------------------
    # CONSTRUCCION
    # ------------------------------------------------------------------
    def _build_mains(self):
        mirrored = self.side == "R"

        for key in self.MAIN_KEYS:
            guide = self.guide_name(key)

            control, _ = self._make_control(
                f"{self.prefix}_{key}_CTRL", guide, mirrored=mirrored
            )
            self.controls[key] = control

    def _build_direct_subs(self):
        """
        Un sub por principal, colgado de el en jerarquia.

        Se coloca contra la MISMA guia que su principal: comparten sitio y lo
        que cambia es el nivel. El principal mueve la zona, el sub afina.
        """
        if not self.has("sub_controls"):
            return

        mirrored = self.side == "R"

        for key in self.MAIN_KEYS:
            main_ctrl = self.controls.get(key)
            if not main_ctrl:
                continue

            sub_key = f"{key}Sub"
            control, group = self._make_control(
                f"{self.prefix}_{sub_key}_CTRL", self.guide_name(key),
                mirrored=mirrored, style="sub", cv_scale=self.sub_cv_scale
            )

            # Jerarquia de verdad, no constraint: solo tiene un padre.
            cmds.parent(group, self._out(main_ctrl))

            self.controls[sub_key] = control
            self.joints[sub_key] = self._make_joint(
                f"{self.prefix}_{sub_key}_JNT", control
            )

    def _build_between_subs(self):
        """Los cuatro de las diagonales, al 50% entre sus dos principales."""
        if not self.has("between_controls"):
            return

        mirrored = self.side == "R"

        for key, (first, second) in self.BETWEEN.items():
            first_ctrl = self.controls.get(first)
            second_ctrl = self.controls.get(second)

            if not (first_ctrl and second_ctrl):
                cmds.warning(f"[Socket] Faltan principales para '{key}'.")
                continue

            control, group = self._make_control(
                f"{self.prefix}_{key}_CTRL", self.guide_name(key),
                mirrored=mirrored, style="sub", cv_scale=self.sub_cv_scale
            )

            constraint = cmds.parentConstraint(
                self._out(first_ctrl), self._out(second_ctrl), group, mo=True
            )[0]

            aliases = cmds.parentConstraint(constraint, q=True,
                                            weightAliasList=True)
            cmds.setAttr(f"{constraint}.{aliases[0]}", self.BETWEEN_WEIGHT)
            cmds.setAttr(f"{constraint}.{aliases[1]}",
                         1.0 - self.BETWEEN_WEIGHT)

            # Shortest: el interpType por defecto (Average) promedia angulos
            # de Euler, y promediar 179 con -179 da 0 en vez de 180.
            cmds.setAttr(f"{constraint}.interpType", 2)

            self.controls[key] = control
            self.joints[key] = self._make_joint(
                f"{self.prefix}_{key}_JNT", control
            )

            print(f"[Socket] {group}: {first} {self.BETWEEN_WEIGHT:.2f} / "
                  f"{second} {1.0 - self.BETWEEN_WEIGHT:.2f}")

    def organize(self):
        """
        Recoge bajo un grupo del modulo lo que haya quedado suelto en el
        mundo: los GRP de los principales y los joints. Los sub directos no
        entran, que ya cuelgan de su principal.
        """
        group_name = f"{self.prefix}_GRP"
        if cmds.objExists(group_name):
            cmds.delete(group_name)

        roots = []
        for node in list(self.control_groups) + list(self.joints.values()):
            if not node or not cmds.objExists(node):
                continue
            if cmds.listRelatives(node, parent=True):
                continue
            if node not in roots:
                roots.append(node)

        if not roots:
            return None

        self.module_group = cmds.group(roots, n=group_name)

        return self.module_group

    def build(self):
        missing = self._missing_guides()
        if missing:
            cmds.warning(f"[Socket {self.side}] Faltan guias ({', '.join(missing)}). "
                         f"Se salta el socket.")
            return None

        self.controls = {}
        self.joints = {}
        self.control_groups = []
        self.output_nodes = {}

        self._build_mains()
        self._build_direct_subs()
        self._build_between_subs()
        self.organize()

        print(f"[Socket {self.side}] {len(self.controls)} controles, "
              f"{len(self.joints)} joints.")

        return self.module_group